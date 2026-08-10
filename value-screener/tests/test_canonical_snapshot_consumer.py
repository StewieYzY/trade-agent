from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

sys_path_root = Path(__file__).resolve().parent.parent


def _consumer_api():
    module = importlib.import_module("data.lib.canonical_snapshot_consumer")
    return module.consume_snapshot, module.SnapshotConsumerError


def _evidence(
    *,
    ticker: str = "600519.SH",
    field: str = "last_price",
    value: float | None = 123.4,
    status: str = "available",
    eligibility: str = "production_eligible",
    reason: str | None = None,
    provider: str = "fixture",
    freshness_status: str = "fresh",
):
    return {
        "provider_family": "baseline",
        "provider": provider,
        "method": "quote",
        "market": "SH",
        "ticker": ticker,
        "field": field,
        "raw_field": "最新价",
        "value": value,
        "unit": "CNY/share",
        "currency": "CNY",
        "as_of": "2026-08-04",
        "report_period": None,
        "status": status,
        "eligibility": eligibility,
        "reason": reason,
        "freshness_status": freshness_status,
        "response_hash": hashlib.sha256(provider.encode()).hexdigest(),
        "retrieved_at": "2026-08-04T09:00:00+00:00",
        "provenance": {
            "provider_family": "baseline",
            "provider": provider,
            "method": "quote",
            "market": "SH",
            "ticker": ticker,
            "raw_field": "最新价",
            "response_hash": hashlib.sha256(provider.encode()).hexdigest(),
            "retrieved_at": "2026-08-04T09:00:00+00:00",
        },
    }


def _write_snapshot(tmp_path: Path, evidence: list[dict], tickers=None) -> Path:
    from data.lib.canonical_snapshot import write_snapshot

    return write_snapshot(
        evidence,
        tickers=tickers or ["600519.SH"],
        plan_version="plan-v1",
        output_root=tmp_path,
        run_id="run-consumer-1",
        as_of="2026-08-04",
    )


def _consume(run_dir: Path, tickers=None, **overrides):
    consume_snapshot, _ = _consumer_api()
    expected_tickers = tickers or ["600519.SH"]
    return consume_snapshot(
        run_dir,
        expected_run_id="run-consumer-1",
        expected_plan_version="plan-v1",
        expected_tickers=expected_tickers,
        **overrides,
    )


def test_complete_snapshot_can_be_consumed(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])

    consumed = _consume(run_dir)

    assert consumed.get("600519.SH", "last_price").value == 123.4


@pytest.mark.parametrize("missing", ["manifest.json", "records.json", "provenance.json"])
def test_missing_required_file_fails_closed(tmp_path, missing):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    (run_dir / missing).unlink()
    _, error = _consumer_api()

    with pytest.raises(error, match=missing):
        _consume(run_dir)


def test_schema_version_mismatch_is_rejected(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = "g1-canonical-snapshot-v999"
    manifest_path.write_text(json.dumps(manifest))
    _, error = _consumer_api()

    with pytest.raises(error, match="schema_version"):
        _consume(run_dir)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("run_id", "other-run", "run_id"),
        ("plan_version", "other-plan", "plan_version"),
        ("ticker_set_hash", "other-hash", "ticker_set_hash"),
    ],
)
def test_run_plan_and_ticker_set_identity_mismatch_is_rejected(
    tmp_path, field, value, expected
):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest[field] = value
    manifest_path.write_text(json.dumps(manifest))
    _, error = _consumer_api()

    with pytest.raises(error, match=expected):
        _consume(run_dir)


def test_expected_snapshot_ticker_set_hash_matches_canonical_snapshot_contract(tmp_path):
    from data.lib.identity import compute_snapshot_ticker_set_hash

    run_dir = _write_snapshot(tmp_path, [_evidence()])

    consumed = _consume(
        run_dir,
        expected_ticker_set_hash=compute_snapshot_ticker_set_hash(["600519.SH"]),
    )

    assert consumed.get("600519.SH", "last_price").value == 123.4


def test_requested_ticker_identity_mismatch_is_rejected(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    _, error = _consumer_api()

    with pytest.raises(error, match="ticker"):
        _consume(run_dir, tickers=["000001.SZ"])


def test_records_ticker_set_mismatch_is_rejected(tmp_path):
    run_dir = _write_snapshot(
        tmp_path,
        [_evidence()],
        tickers=["600519.SH", "000001.SZ"],
    )
    _, error = _consumer_api()

    with pytest.raises(error, match="ticker"):
        _consume(run_dir, tickers=["600519.SH"])


def test_available_field_returns_value_and_metadata(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])

    field = _consume(run_dir).get("600519.SH", "last_price")

    assert field.value == 123.4
    assert field.status == "available"
    assert field.eligibility == "production_eligible"
    assert field.provenance["provider"] == "fixture"
    assert field.as_of == "2026-08-04"
    assert field.freshness == "fresh"


def test_not_qualified_field_is_explicitly_not_available(tmp_path):
    run_dir = _write_snapshot(
        tmp_path,
        [
            _evidence(
                value=None,
                status="available",
                eligibility="not_qualified",
                reason="not promoted",
            )
        ],
    )

    field = _consume(run_dir).get("600519.SH", "last_price")

    assert field.value is None
    assert field.status == "not_evaluated"
    assert field.eligibility == "not_qualified"
    assert field.available is False
    assert field.reason == "not promoted"


@pytest.mark.parametrize(
    "status",
    ["record_not_found", "source_failed", "invalid_value", "not_evaluated"],
)
def test_rejected_field_is_explicit_null_with_status_reason_and_provenance(
    tmp_path, status
):
    run_dir = _write_snapshot(
        tmp_path,
        [
            _evidence(
                status=status,
                value=None,
                eligibility="not_qualified",
                reason=f"reason-{status}",
            )
        ],
    )

    field = _consume(run_dir).get("600519.SH", "last_price")

    assert field.value is None
    assert field.status == status
    assert field.reason == f"reason-{status}"
    assert field.provenance["provider"] == "fixture"


@pytest.mark.parametrize("status", ["stale", "degraded"])
def test_stale_and_degraded_fields_are_not_available(tmp_path, status):
    run_dir = _write_snapshot(
        tmp_path,
        [
            _evidence(
                status="available" if status == "stale" else "source_failed",
                value=None,
                eligibility="not_qualified",
                reason=f"reason-{status}",
                freshness_status=status,
            )
        ],
    )
    if status == "degraded":
        provenance_path = run_dir / "provenance.json"
        payload = json.loads(provenance_path.read_text())
        payload["fields"][0]["status"] = "degraded"
        provenance_path.write_text(json.dumps(payload))

    field = _consume(run_dir).get("600519.SH", "last_price")

    assert field.value is None
    assert field.status == ("not_evaluated" if status == "stale" else "degraded")
    assert field.freshness == status


def test_missing_freshness_is_explicitly_unavailable(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    provenance_path = run_dir / "provenance.json"
    payload = json.loads(provenance_path.read_text())
    payload["fields"][0].pop("freshness_status")
    provenance_path.write_text(json.dumps(payload))

    field = _consume(run_dir).get("600519.SH", "last_price")

    assert field.value is None
    assert field.available is False
    assert field.freshness is None


def test_mixed_qualified_and_rejected_fields_are_independent(tmp_path):
    run_dir = _write_snapshot(
        tmp_path,
        [
            _evidence(field="last_price", value=123.4),
            _evidence(
                field="pe_ttm",
                value=None,
                status="source_failed",
                eligibility="not_qualified",
                reason="provider down",
            ),
        ],
    )

    consumed = _consume(run_dir)

    assert consumed.get("600519.SH", "last_price").value == 123.4
    assert consumed.get("600519.SH", "pe_ttm").value is None
    assert consumed.get("600519.SH", "pe_ttm").status == "source_failed"


def test_records_and_provenance_field_identity_mismatch_is_rejected(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    provenance_path = run_dir / "provenance.json"
    payload = json.loads(provenance_path.read_text())
    payload["fields"][0]["field"] = "pe_ttm"
    provenance_path.write_text(json.dumps(payload))
    _, error = _consumer_api()

    with pytest.raises(error, match="field"):
        _consume(run_dir)


def test_record_without_provenance_is_rejected(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    records_path = run_dir / "records.json"
    records = json.loads(records_path.read_text())
    records["600519.SH"]["pe_ttm"] = None
    records_path.write_text(json.dumps(records))
    _, error = _consumer_api()

    with pytest.raises(error, match="field"):
        _consume(run_dir)


def test_records_value_mismatch_with_provenance_fails_closed(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    records_path = run_dir / "records.json"
    records = json.loads(records_path.read_text())
    records["600519.SH"]["last_price"] = 999.9
    records_path.write_text(json.dumps(records))
    _, error = _consumer_api()

    with pytest.raises(error, match="value"):
        _consume(run_dir)


def test_consumer_is_read_only_and_does_not_need_decision_json(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    before = {
        path.name: path.read_bytes()
        for path in run_dir.iterdir()
        if path.is_file()
    }

    consumed = _consume(run_dir)

    assert consumed.get("600519.SH", "last_price").status == "available"
    after = {path.name: path.read_bytes() for path in run_dir.iterdir() if path.is_file()}
    assert after == before
    assert not (run_dir / "decision.json").exists()


def test_consumer_view_is_deeply_read_only(tmp_path):
    run_dir = _write_snapshot(tmp_path, [_evidence()])
    consumed = _consume(run_dir)
    field = consumed.get("600519.SH", "last_price")

    with pytest.raises(TypeError):
        field.provenance["provenance"]["provider"] = "mutated"
    with pytest.raises(TypeError):
        consumed.manifest["status_summary"]["available"] = 999


def test_consumer_has_no_provider_llm_or_production_path_side_effects(
    tmp_path, monkeypatch
):
    from council import llm
    from data.cache import manager
    from data.lib import batch_fetcher, provider_batch_adapter

    def forbidden(*args, **kwargs):
        raise AssertionError("consumer must not execute external or production paths")

    monkeypatch.setattr(provider_batch_adapter.BatchAdapter, "run", forbidden)
    monkeypatch.setattr(batch_fetcher.BatchFetcher, "fetch_all", forbidden)
    monkeypatch.setattr(llm, "call_llm", forbidden)
    monkeypatch.setattr(manager.CacheManager, "get", forbidden)
    monkeypatch.setattr(manager.CacheManager, "set", forbidden)

    run_dir = _write_snapshot(tmp_path, [_evidence()])
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    _consume(run_dir)

    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert after == before
