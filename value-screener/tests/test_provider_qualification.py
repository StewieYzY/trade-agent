from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.provider_qualification import (  # noqa: E402
    ProviderAdapter,
    ProbeCase,
    QualificationRunner,
    _bounded_raw,
    _probe_case,
    _redact_error,
    _status_from_error,
    build_probe_plan,
)
from scripts.baseline_provider_adapters import get_provider_adapters  # noqa: E402


def _case(method: str = "quote") -> ProbeCase:
    return ProbeCase(
        ticker="600519.SH",
        market="SH",
        security_type="consumer",
        method=method,
        fields=("last_price", "turnover_rate"),
    )


def test_probe_plan_is_fixed_and_canonical():
    plan = build_probe_plan()

    assert len(plan) == 50
    assert {case.ticker for case in plan} == {
        "600519.SH",
        "600009.SH",
        "000858.SZ",
        "300750.SZ",
        "601318.SH",
    }
    assert all(case.ticker.endswith((".SH", ".SZ")) for case in plan)


def test_available_and_partial_field_evidence_is_traceable():
    def invoke(case: ProbeCase):
        assert case.method == "quote"
        return {
            "last_price": "123.4",
            "_fields": {
                "last_price": {"unit": "CNY/share", "currency": "CNY", "as_of": "2026-08-04"},
                "turnover_rate": {"unit": "%", "as_of": "2026-08-04"},
            },
        }

    adapter = ProviderAdapter("baseline", "fixture", invoke=invoke)
    evidence, result = _probe_case(adapter, _case())

    assert result["status"] == "partial"
    assert evidence[0]["status"] == "available"
    assert evidence[0]["value"] == 123.4
    assert evidence[0]["unit"] == "CNY/share"
    assert evidence[0]["retrieved_at"] == evidence[0]["provenance"]["retrieved_at"]
    assert evidence[1]["status"] == "record_not_found"


@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (PermissionError("403 permission denied"), "permission_denied"),
        (type("RateLimitError", (Exception,), {"status_code": 429})("too many requests"), "rate_limited"),
        (ValueError("unsupported market"), "not_supported_for_market"),
        (KeyError("no record for ticker"), "record_not_found"),
        (KeyError("provider returned empty response"), "source_failed"),
        (TypeError("bad value"), "invalid_value"),
        (RuntimeError("provider unavailable"), "source_failed"),
    ],
)
def test_failure_states_are_explicit(exc, status):
    assert _status_from_error(exc) == status


def test_error_redaction_and_raw_truncation():
    redacted = _redact_error(
        "Authorization: Bearer secret-token api_key=sk-secret https://user:pass@example.com"
    )
    assert "secret-token" not in redacted
    assert "sk-secret" not in redacted
    assert "user:pass@" not in redacted

    raw, digest, truncated = _bounded_raw({"payload": "x" * 250_000})
    assert truncated is True
    assert raw["__truncated__"] is True
    assert len(digest) == 64


def test_unavailable_candidate_probe_is_run_scoped_and_isolated(tmp_path):
    runner = QualificationRunner(
        adapters=[
            ProviderAdapter(
                "candidate",
                "longbridge",
                available=False,
                availability_reason="credentials missing",
            )
        ],
        cases=[_case()],
    )
    result = runner.run(output_root=tmp_path, run_id="qualification-1")
    run_dir = tmp_path / "qualification-1"

    assert result["manifest"]["stop_reason"] == "no_runtime_provider_adapter_available"
    assert all(item["status"] == "not_evaluated" for item in result["evidence"])
    assert (run_dir / "manifest.json").exists()
    assert (run_dir / "evidence.json").exists()
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "watchlist").exists()
    assert json.loads((run_dir / "comparison.json").read_text())["comparison"][0][
        "integration_eligibility"
    ] == "not_qualified_by_this_change"


def test_rate_limit_stops_remaining_cases_for_provider(tmp_path):
    calls = []

    def invoke(case: ProbeCase):
        calls.append(case.method)
        raise type("RateLimitError", (Exception,), {"status_code": 429})("rate limit")

    runner = QualificationRunner(
        adapters=[ProviderAdapter("candidate", "longport", invoke=invoke)],
        cases=[_case("quote"), _case("calc_indexes")],
    )
    result = runner.run(output_root=tmp_path, run_id="rate-limited")

    assert calls == ["quote"]
    assert result["manifest"]["stop_reason"] == "rate_limited:longport:quote:600519.SH"
    assert len(result["evidence"]) == 2


def test_run_id_cannot_escape_output_root(tmp_path):
    runner = QualificationRunner(adapters=[], cases=[_case()])

    with pytest.raises(ValueError, match="run_id"):
        runner.run(output_root=tmp_path, run_id="../escape")


def test_baseline_adapter_exposes_existing_fetcher_contract_without_fabricating_fields():
    adapter = get_provider_adapters()[0]

    evidence, result = _probe_case(adapter, _case("consensus"))

    assert result["status"] == "not_evaluated"
    assert all(item["status"] == "not_evaluated" for item in evidence)
    assert "not exposed" in result["reason"]


def test_baseline_adapter_uses_primary_fetcher_without_hidden_fallback(monkeypatch):
    from data.fetchers.basic import BasicFetcher

    monkeypatch.setattr(
        BasicFetcher,
        "fetch",
        lambda _self, _ticker: {
            "code": "600519",
            "name": "测试公司",
            "price": 123.4,
            "pe": 20.0,
            "pb": 2.0,
            "market_cap": 1000000000,
        },
    )
    adapter = get_provider_adapters()[0]
    evidence, result = _probe_case(adapter, _case("quote"))

    assert result["status"] == "partial"
    assert evidence[0]["status"] == "available"
    assert evidence[0]["value"] == 123.4
    assert evidence[0]["provenance"]["provider"] == "akshare-existing-fetcher-chain"
