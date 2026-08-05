from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.provider_batch_adapter import (  # noqa: E402
    BatchAdapter,
    ProviderSpec,
)
from data.lib.canonical_snapshot import SnapshotError


def _record(
    ticker: str,
    value: float,
    *,
    unit: str = "CNY/share",
    retrieved_at: str | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "last_price": value,
        "_fields": {
            "last_price": {
                "unit": unit,
                "currency": "CNY",
                "as_of": "2026-08-05",
                **({"retrieved_at": retrieved_at} if retrieved_at else {}),
            }
        },
    }


def test_batch_provider_is_called_once_and_maps_each_ticker():
    calls = []

    def fetch(request):
        calls.append(request)
        return {
            "600519.SH": _record("600519.SH", 123.4),
            "000858.SZ": _record("000858.SZ", 88.8),
        }

    adapter = BatchAdapter(
        [
            ProviderSpec(
                provider_family="fixture",
                provider="baseline",
                fetch_batch=fetch,
                eligibility="production_eligible",
            )
        ]
    )
    result = adapter.run(
        tickers=["600519", "000858.SZ"],
        method="quote",
        fields=["last_price"],
        run_id="batch-one",
    )

    assert len(calls) == 1
    assert calls[0].tickers == ("000858.SZ", "600519.SH")
    assert result["manifest"]["provider_method_calls"] == {
        "baseline:quote": 1
    }
    summary = result["manifest"]["providers"][0]
    assert summary["batch_size"] == 2
    assert summary["call_count"] == 1
    assert summary["run_id"] == "batch-one"
    assert summary["request_id"].startswith("batch-one:baseline:quote:")
    assert len(summary["response_hash"]) == 64
    assert summary["status_summary"] == {"available": 2}
    assert result["snapshot"]["records"]["600519.SH"]["last_price"] == 123.4
    assert result["snapshot"]["records"]["000858.SZ"]["last_price"] == 88.8


def test_omitted_ticker_gets_record_not_found_without_blocking_other_ticker():
    def fetch(_request):
        return {"600519.SH": _record("600519.SH", 123.4)}

    adapter = BatchAdapter(
        [
            ProviderSpec(
                provider_family="fixture",
                provider="baseline",
                fetch_batch=fetch,
                eligibility="production_eligible",
            )
        ]
    )
    result = adapter.run(
        tickers=["600519.SH", "000858.SZ"],
        method="quote",
        fields=["last_price"],
        run_id="missing-one",
    )

    missing = [
        item
        for item in result["evidence"]
        if item["ticker"] == "000858.SZ"
    ]
    assert missing[0]["status"] == "record_not_found"
    assert result["snapshot"]["records"]["600519.SH"]["last_price"] == 123.4
    assert result["snapshot"]["records"]["000858.SZ"]["last_price"] is None


def test_one_provider_failure_does_not_cancel_other_provider():
    def broken(_request):
        raise TimeoutError("provider timeout")

    def healthy(_request):
        return {"600519.SH": _record("600519.SH", 123.4)}

    adapter = BatchAdapter(
        [
            ProviderSpec("candidate", "broken", broken),
            ProviderSpec(
                "baseline",
                "healthy",
                healthy,
                eligibility="production_eligible",
            ),
        ]
    )
    result = adapter.run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price"],
        run_id="provider-isolation",
    )

    broken_status = [
        item["status"]
        for item in result["evidence"]
        if item["provider"] == "broken"
    ]
    assert broken_status == ["source_failed"]
    assert result["snapshot"]["records"]["600519.SH"]["last_price"] == 123.4


def test_unavailable_provider_is_not_silently_replaced():
    adapter = BatchAdapter(
        [
            ProviderSpec(
                "candidate",
                "longport",
                None,
                available=False,
            )
        ]
    )
    result = adapter.run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price"],
        run_id="unavailable",
    )

    assert result["manifest"]["provider_method_calls"] == {}
    assert result["manifest"]["providers"][0]["call_count"] == 0
    assert result["manifest"]["providers"][0]["status_summary"] == {
        "not_evaluated": 1
    }
    assert result["evidence"][0]["status"] == "not_evaluated"
    assert result["snapshot"]["records"]["600519.SH"]["last_price"] is None


def test_field_failure_isolated_and_preserved_in_sidecar():
    def fetch(_request):
        return {
            "600519.SH": {
                "ticker": "600519.SH",
                "last_price": 123.4,
                "turnover_rate": None,
                "_fields": {
                    "last_price": {
                        "unit": "CNY/share",
                        "currency": "CNY",
                        "as_of": "2026-08-05",
                    },
                    "turnover_rate": {
                        "status": "source_failed",
                        "raw_field": "turnoverRate",
                    },
                },
            }
        }

    result = BatchAdapter(
        [
            ProviderSpec(
                "fixture",
                "partial",
                fetch,
                eligibility="production_eligible",
            )
        ]
    ).run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price", "turnover_rate"],
        run_id="field-isolation",
    )

    assert result["snapshot"]["records"]["600519.SH"]["last_price"] == 123.4
    assert result["snapshot"]["records"]["600519.SH"]["turnover_rate"] is None
    assert result["manifest"]["status_summary"] == {
        "available": 1,
        "source_failed": 1,
    }


def test_omitted_field_is_not_misclassified_as_missing_record():
    def fetch(_request):
        return {"600519.SH": _record("600519.SH", 123.4)}

    result = BatchAdapter(
        [
            ProviderSpec(
                "fixture",
                "partial",
                fetch,
                eligibility="production_eligible",
            )
        ]
    ).run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price", "turnover_rate"],
        run_id="field-omitted",
    )

    omitted = [
        item
        for item in result["evidence"]
        if item["field"] == "turnover_rate"
    ][0]
    assert omitted["status"] == "not_evaluated"
    assert omitted["reason"] == "provider record omitted field"
    assert result["snapshot"]["records"]["600519.SH"]["last_price"] == 123.4


def test_shadow_provider_never_populates_production_value():
    def fetch(_request):
        return {"600519.SH": _record("600519.SH", 999.0)}

    adapter = BatchAdapter(
        [
            ProviderSpec(
                "candidate",
                "longbridge",
                fetch,
                shadow=True,
                eligibility="production_eligible",
            )
        ]
    )
    result = adapter.run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price"],
        run_id="shadow-only",
    )

    assert result["evidence"][0]["eligibility"] == "shadow_only"
    assert result["snapshot"]["records"]["600519.SH"]["last_price"] is None


def test_shadow_conflict_does_not_poison_production_provider():
    def production(_request):
        return {"600519.SH": _record("600519.SH", 123.4)}

    def shadow(_request):
        return {"600519.SH": _record("600519.SH", 999.0)}

    result = BatchAdapter(
        [
            ProviderSpec(
                "baseline",
                "production",
                production,
                eligibility="production_eligible",
            ),
            ProviderSpec("candidate", "longbridge", shadow, shadow=True),
        ]
    ).run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price"],
        run_id="shadow-isolated",
    )

    assert result["snapshot"]["records"]["600519.SH"]["last_price"] == 123.4
    assert result["snapshot"]["conflict_count"] == 0


def test_time_basis_mismatch_fails_closed():
    def record(as_of: str) -> dict:
        return {
            "ticker": "600519.SH",
            "last_price": 123.4,
            "_fields": {
                "last_price": {
                    "unit": "CNY/share",
                    "currency": "CNY",
                    "as_of": as_of,
                }
            },
        }

    result = BatchAdapter(
        [
            ProviderSpec(
                "baseline",
                "morning",
                lambda _request: {"600519.SH": record("2026-08-05")},
                eligibility="production_eligible",
            ),
            ProviderSpec(
                "baseline",
                "prior-close",
                lambda _request: {"600519.SH": record("2026-08-04")},
                eligibility="production_eligible",
            ),
        ]
    ).run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price"],
        run_id="time-conflict",
    )

    assert result["snapshot"]["records"]["600519.SH"]["last_price"] is None
    assert any(
        conflict["kind"] == "time_basis"
        for conflict in result["snapshot"]["conflicts"]
    )


def test_stale_evidence_is_not_a_production_override():
    old = (datetime.now(timezone.utc).replace(year=2020)).isoformat()

    def fetch(_request):
        return {"600519.SH": _record("600519.SH", 123.4, retrieved_at=old)}

    result = BatchAdapter(
        [
            ProviderSpec(
                "baseline",
                "stale",
                fetch,
                eligibility="production_eligible",
            )
        ]
    ).run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price"],
        run_id="stale",
        freshness_seconds=60,
    )

    assert result["snapshot"]["records"]["600519.SH"]["last_price"] is None
    assert result["snapshot"]["provenance"][0]["eligibility"] == "not_qualified"
    assert "freshness window" in result["snapshot"]["provenance"][0]["reason"]


def test_conflicting_production_providers_fail_closed():
    def left(_request):
        return {"600519.SH": _record("600519.SH", 123.4)}

    def right(_request):
        return {"600519.SH": _record("600519.SH", 130.0)}

    adapter = BatchAdapter(
        [
            ProviderSpec("baseline", "left", left, eligibility="production_eligible"),
            ProviderSpec("baseline", "right", right, eligibility="production_eligible"),
        ]
    )
    result = adapter.run(
        tickers=["600519.SH"],
        method="quote",
        fields=["last_price"],
        run_id="conflict",
    )

    assert result["snapshot"]["records"]["600519.SH"]["last_price"] is None
    assert result["snapshot"]["conflict_count"] >= 1


def test_invalid_ticker_is_rejected_before_provider_call():
    calls = []

    def fetch(_request):
        calls.append(True)
        return {}

    adapter = BatchAdapter([ProviderSpec("fixture", "provider", fetch)])

    with pytest.raises(ValueError, match="invalid ticker"):
        adapter.run(
            tickers=["not-a-ticker"],
            method="quote",
            fields=["last_price"],
            run_id="invalid",
        )
    assert calls == []
