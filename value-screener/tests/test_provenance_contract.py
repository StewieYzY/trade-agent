from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.provenance import (  # noqa: E402
    ProvenanceContractError,
    build_sidecar,
    detect_conflicts,
    serialize_sidecar,
    sidecar_for_qualification_evidence,
    validate_field_evidence,
)


def _evidence(**overrides):
    item = {
        "provider_family": "baseline",
        "provider": "fixture",
        "method": "quote",
        "market": "SH",
        "ticker": "600519.SH",
        "field": "last_price",
        "raw_field": "最新价",
        "value": 123.4,
        "unit": "CNY/share",
        "currency": "CNY",
        "as_of": "2026-08-04",
        "report_period": None,
        "status": "available",
        "eligibility": "not_qualified",
        "response_hash": "a" * 64,
        "retrieved_at": "2026-08-04T09:00:00+00:00",
        "provenance": {
            "provider_family": "baseline",
            "provider": "fixture",
            "method": "quote",
            "market": "SH",
            "ticker": "600519.SH",
            "raw_field": "最新价",
            "response_hash": "a" * 64,
            "retrieved_at": "2026-08-04T09:00:00+00:00",
        },
    }
    item.update(overrides)
    return item


def test_available_field_is_valid_but_not_production_eligible():
    result = validate_field_evidence(_evidence())

    assert result["status"] == "available"
    assert result["eligibility"] == "not_qualified"


def test_missing_unit_or_time_basis_downgrades_numeric_field():
    missing_unit = validate_field_evidence(_evidence(unit=None, currency=None))
    missing_time = validate_field_evidence(
        _evidence(field="pe_ttm", as_of=None, report_period=None)
    )
    missing_quote_time = validate_field_evidence(
        _evidence(field="last_price", as_of=None)
    )

    assert missing_unit["status"] == "not_evaluated"
    assert "unit" in missing_unit["reason"]
    assert missing_time["status"] == "not_evaluated"
    assert "time basis" in missing_time["reason"]
    assert missing_quote_time["status"] == "not_evaluated"
    assert "time basis" in missing_quote_time["reason"]


def test_available_none_is_downgraded_even_for_non_numeric_field():
    result = validate_field_evidence(
        _evidence(field="name", value=None, as_of="2026-08-04")
    )

    assert result["status"] == "not_evaluated"
    assert "no value" in result["reason"]


def test_missing_provenance_and_production_promotion_fail_closed():
    missing = validate_field_evidence(
        _evidence(
            response_hash=None,
            provenance={**_evidence()["provenance"], "response_hash": None},
        )
    )
    assert missing["status"] == "not_evaluated"
    assert "response_hash" in missing["reason"]

    with pytest.raises(ProvenanceContractError, match="production eligibility"):
        validate_field_evidence(_evidence(eligibility="production_eligible"))


@pytest.mark.parametrize(
    "identity_key",
    [
        "provider_family",
        "provider",
        "method",
        "market",
        "ticker",
        "raw_field",
        "response_hash",
        "retrieved_at",
    ],
)
def test_top_level_and_provenance_identity_mismatch_fails_closed(identity_key):
    evidence = _evidence()
    evidence["provenance"] = {
        **evidence["provenance"],
        identity_key: f"mismatched-{identity_key}",
    }

    result = validate_field_evidence(evidence)

    assert result["status"] == "not_evaluated"
    assert result["eligibility"] == "not_qualified"
    assert f"provenance mismatch: {identity_key}" in result["reason"]


def test_rejected_status_preserves_original_status_when_identity_mismatches():
    evidence = _evidence(
        status="source_failed",
        value=None,
        reason="provider unavailable",
    )
    evidence["provenance"] = {
        **evidence["provenance"],
        "response_hash": "mismatched-response-hash",
    }

    result = validate_field_evidence(evidence)

    assert result["status"] == "source_failed"
    assert result["eligibility"] == "not_qualified"
    assert "provider unavailable" in result["reason"]
    assert "provenance mismatch: response_hash" in result["reason"]


def test_sensitive_reason_is_redacted_and_sidecar_is_json_safe():
    result = validate_field_evidence(
        _evidence(
            status="source_failed",
            value=None,
            reason="Authorization: Bearer sk-secret https://user:pass@example.com",
        )
    )
    assert "sk-secret" not in result["reason"]
    assert "user:pass@" not in result["reason"]
    json.loads(serialize_sidecar(build_sidecar([result])))


def test_conflicts_preserve_all_sources_and_detect_stale_value():
    second = _evidence(
        provider="candidate",
        value=130.0,
        response_hash="b" * 64,
        retrieved_at="2026-08-04T09:30:00+00:00",
        provenance={
            **_evidence()["provenance"],
            "provider": "candidate",
            "response_hash": "b" * 64,
            "retrieved_at": "2026-08-04T09:30:00+00:00",
        },
    )
    conflicts = detect_conflicts(
        [_evidence(), second],
        now=datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc),
        freshness_seconds=1_000,
    )

    assert any(item["kind"] == "value" for item in conflicts)
    assert all("providers" in item for item in conflicts)

    stale = _evidence(
        provider="stale",
        response_hash="c" * 64,
        retrieved_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        provenance={
            **_evidence()["provenance"],
            "provider": "stale",
            "response_hash": "c" * 64,
            "retrieved_at": (datetime.now(timezone.utc) - timedelta(days=3)).isoformat(),
        },
    )
    freshness_conflicts = detect_conflicts(
        [_evidence(), stale],
        now=datetime(2026, 8, 4, 10, 0, tzinfo=timezone.utc),
        freshness_seconds=5_000,
    )
    assert any(item["kind"] == "freshness" for item in freshness_conflicts)


def test_qualification_evidence_converts_to_sidecar_without_legacy_payload_change():
    payload = {"evidence": [_evidence()], "legacy_value": {"pe": 20}}
    sidecar = sidecar_for_qualification_evidence(payload)

    assert sidecar["field_count"] == 1
    assert payload["legacy_value"] == {"pe": 20}
