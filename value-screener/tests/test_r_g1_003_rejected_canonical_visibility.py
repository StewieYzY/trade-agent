from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.canonical_snapshot import (  # noqa: E402
    _source_set_hash,
    read_snapshot,
)
from data.lib.field_qualification import FieldQualificationPolicy  # noqa: E402
from scripts.promote_provider_snapshot import (  # noqa: E402
    promote_provider_snapshot,
)


EVALUATED_AT = datetime(2026, 8, 5, 0, 1, tzinfo=timezone.utc)


def _policy():
    return FieldQualificationPolicy.from_mapping(
        version="r-g1-003-test-v1",
        tickers=("600519.SH", "600009.SH"),
        methods={"quote": ("last_price", "turnover_rate")},
        allowed_providers=("fixture",),
        freshness_seconds=300,
    )


def _evidence(
    ticker: str,
    *,
    field: str = "last_price",
    value: float | None = 123.4,
    status: str = "available",
    reason: str | None = None,
):
    retrieved_at = "2026-08-05T00:00:00+00:00"
    response_hash = f"{ticker}-{field}-hash"
    return {
        "provider_family": "baseline",
        "provider": "fixture",
        "method": "quote",
        "market": "SH",
        "ticker": ticker,
        "security_type": "consumer",
        "field": field,
        "raw_field": field,
        "value": value if status == "available" else None,
        "unit": "CNY/share" if field == "last_price" else "%",
        "currency": "CNY",
        "as_of": "2026-08-04",
        "report_period": None,
        "status": status,
        "reason": reason or (None if status == "available" else f"{status} reason"),
        "response_hash": response_hash,
        "retrieved_at": retrieved_at,
        "provenance": {
            "provider_family": "baseline",
            "provider": "fixture",
            "method": "quote",
            "market": "SH",
            "ticker": ticker,
            "raw_field": field,
            "response_hash": response_hash,
            "retrieved_at": retrieved_at,
            "source_locator": f"fixture://{ticker}/{field}",
        },
    }


def _write_source_run(tmp_path: Path, evidence: list[dict]) -> Path:
    source = tmp_path / "qualification" / "source-run"
    source.mkdir(parents=True)
    cases_by_identity: dict[tuple[str, str], dict] = {}
    for item in evidence:
        key = (item["ticker"], item["method"])
        case = cases_by_identity.setdefault(
            key,
            {
                "ticker": item["ticker"],
                "market": item["market"],
                "security_type": item["security_type"],
                "method": item["method"],
                "fields": [],
            },
        )
        if item["field"] not in case["fields"]:
            case["fields"].append(item["field"])
    cases = list(cases_by_identity.values())
    plan = {
        "run_id": "source-run",
        "version": "r-g1-003-plan-v1",
        "plan_hash": hashlib.sha256(
            json.dumps(
                {"version": "r-g1-003-plan-v1", "cases": cases},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "cases": cases,
    }
    evidence_payload = {"run_id": "source-run", "evidence": evidence}
    manifest = {
        "run_id": "source-run",
        "plan_version": plan["version"],
        "plan_hash": plan["plan_hash"],
        "ticker_set_hash": hashlib.sha256(
            json.dumps(
                sorted({item["ticker"] for item in evidence}),
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "completion_status": "completed",
        "evidence_count": len(evidence),
        "field_status_counts": {},
        "artifact_status": {"plan": "written", "evidence": "written"},
        "artifacts": {"plan": "plan.json", "evidence": "evidence.json"},
    }
    (source / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (source / "evidence.json").write_text(
        json.dumps(evidence_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest["artifact_hashes"] = {
        "plan": hashlib.sha256((source / "plan.json").read_bytes()).hexdigest(),
        "evidence": hashlib.sha256((source / "evidence.json").read_bytes()).hexdigest(),
    }
    manifest_for_hash = copy.deepcopy(manifest)
    manifest_for_hash.pop("artifact_hashes")
    manifest["manifest_hash"] = hashlib.sha256(
        json.dumps(
            manifest_for_hash,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    (source / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return source


def _promote(tmp_path: Path, evidence: list[dict], run_id: str = "promotion-1"):
    source = _write_source_run(tmp_path, evidence)
    return promote_provider_snapshot(
        source,
        output_root=tmp_path / "promotions",
        policy=_policy(),
        run_id=run_id,
        evaluated_at=EVALUATED_AT,
    )


def test_mixed_qualified_and_source_failed_fields_remain_visible(tmp_path):
    result = _promote(
        tmp_path,
        [
            _evidence("600519.SH", field="last_price"),
            _evidence("600009.SH", field="last_price", value=88.0),
            _evidence("600519.SH", field="turnover_rate", status="source_failed"),
            _evidence("600009.SH", field="turnover_rate", status="source_failed"),
        ],
    )

    snapshot = read_snapshot(result["snapshot_output"])
    assert snapshot["records"]["600519.SH"]["last_price"] == 123.4
    assert snapshot["records"]["600519.SH"]["turnover_rate"] is None
    assert snapshot["records"]["600009.SH"]["turnover_rate"] is None


def test_rejected_field_is_present_in_canonical_provenance_sidecar(tmp_path):
    result = _promote(
        tmp_path,
        [
            _evidence("600519.SH", field="last_price"),
            _evidence("600009.SH", field="last_price"),
            _evidence("600519.SH", field="turnover_rate", status="source_failed"),
            _evidence("600009.SH", field="turnover_rate", status="source_failed"),
        ],
    )

    snapshot = read_snapshot(result["snapshot_output"])
    rejected = [
        item
        for item in snapshot["provenance"]["fields"]
        if item["field"] == "turnover_rate"
    ]
    assert len(rejected) == 2
    assert all(item["eligibility"] == "not_qualified" for item in rejected)
    assert all(item["status"] == "source_failed" for item in rejected)
    assert all(item["reason"] == "source_failed reason" for item in rejected)
    assert all(item["provenance"]["source_locator"].startswith("fixture://") for item in rejected)


def test_group_rejection_reason_is_visible_for_available_item_in_rejected_group(tmp_path):
    result = _promote(
        tmp_path,
        [
            _evidence("600519.SH", field="last_price"),
            _evidence("600009.SH", field="last_price"),
            _evidence("600519.SH", field="turnover_rate", value=2.1),
            _evidence("600009.SH", field="turnover_rate", status="source_failed"),
        ],
    )

    snapshot = read_snapshot(result["snapshot_output"])
    available_but_rejected = next(
        item
        for item in snapshot["provenance"]["fields"]
        if item["field"] == "turnover_rate" and item["ticker"] == "600519.SH"
    )
    assert available_but_rejected["eligibility"] == "not_qualified"
    assert available_but_rejected["reason"].startswith("qualification rejected:")
    assert "non_available_status" in available_but_rejected["qualification_reason_codes"]
    assert snapshot["records"]["600519.SH"]["turnover_rate"] is None


@pytest.mark.parametrize("status", ["record_not_found", "invalid_value", "not_evaluated"])
def test_rejection_statuses_are_not_silently_available(tmp_path, status):
    result = _promote(
        tmp_path,
        [
            _evidence("600519.SH", field="last_price"),
            _evidence("600009.SH", field="last_price"),
            _evidence("600519.SH", field="turnover_rate", status=status),
            _evidence("600009.SH", field="turnover_rate", status=status),
        ],
    )

    snapshot = read_snapshot(result["snapshot_output"])
    rejected = [
        item
        for item in snapshot["provenance"]["fields"]
        if item["field"] == "turnover_rate"
    ]
    assert all(item["status"] == status for item in rejected)
    assert all(item["canonical_consumable"] is False for item in rejected)
    assert snapshot["records"]["600519.SH"]["turnover_rate"] is None


def test_all_rejected_fields_still_write_explicit_not_qualified_snapshot(tmp_path):
    result = _promote(
        tmp_path,
        [
            _evidence("600519.SH", status="source_failed"),
            _evidence("600009.SH", status="source_failed"),
            _evidence("600519.SH", field="turnover_rate", status="not_evaluated"),
            _evidence("600009.SH", field="turnover_rate", status="not_evaluated"),
        ],
    )

    assert result["status"] == "blocked"
    assert result["snapshot_output"]
    snapshot = read_snapshot(result["snapshot_output"])
    assert snapshot["records"]["600519.SH"] == {
        "last_price": None,
        "turnover_rate": None,
    }
    assert all(
        item["eligibility"] == "not_qualified"
        for item in snapshot["provenance"]["fields"]
    )


def test_reader_does_not_need_decision_json_for_field_status(tmp_path):
    result = _promote(
        tmp_path,
        [
            _evidence("600519.SH"),
            _evidence("600009.SH"),
            _evidence("600519.SH", field="turnover_rate", status="source_failed"),
            _evidence("600009.SH", field="turnover_rate", status="source_failed"),
        ],
    )
    decision_path = Path(result["snapshot_output"]) / "decision.json"
    decision_path.unlink()

    snapshot = read_snapshot(result["snapshot_output"])
    assert any(
        item["field"] == "turnover_rate"
        and item["eligibility"] == "not_qualified"
        and item["reason"] == "source_failed reason"
        for item in snapshot["provenance"]["fields"]
    )


def test_mixed_promotion_does_not_overwrite_source_evidence(tmp_path):
    evidence = [
        _evidence("600519.SH"),
        _evidence("600009.SH"),
        _evidence("600519.SH", field="turnover_rate", status="source_failed"),
        _evidence("600009.SH", field="turnover_rate", status="source_failed"),
    ]
    source = _write_source_run(tmp_path, evidence)
    before = {path.name: path.read_bytes() for path in source.iterdir()}

    promote_provider_snapshot(
        source,
        output_root=tmp_path / "promotions",
        policy=_policy(),
        run_id="promotion-1",
        evaluated_at=EVALUATED_AT,
    )

    assert {path.name: path.read_bytes() for path in source.iterdir()} == before


def test_snapshot_identity_and_provenance_bind_to_source_run(tmp_path):
    evidence = [
        _evidence("600519.SH"),
        _evidence("600009.SH"),
        _evidence("600519.SH", field="turnover_rate", status="source_failed"),
        _evidence("600009.SH", field="turnover_rate", status="source_failed"),
    ]
    source = _write_source_run(tmp_path, evidence)
    result = promote_provider_snapshot(
        source,
        output_root=tmp_path / "promotions",
        policy=_policy(),
        run_id="promotion-1",
        evaluated_at=EVALUATED_AT,
    )

    snapshot = read_snapshot(result["snapshot_output"])
    decision = result["decision"]
    assert snapshot["manifest"]["run_id"] == "promotion-1"
    assert snapshot["manifest"]["source_evidence_hash"] == decision["source_evidence_hash"]
    expected_ticker_hash = hashlib.sha256(
        json.dumps(
            ["600009.SH", "600519.SH"],
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    assert snapshot["manifest"]["ticker_set_hash"] == expected_ticker_hash
    assert snapshot["provenance"]["run_id"] == "promotion-1"
    source_identity = {
        (item["ticker"], item["field"], item["response_hash"])
        for item in evidence
    }
    snapshot_identity = {
        (item["ticker"], item["field"], item["response_hash"])
        for item in snapshot["provenance"]["fields"]
    }
    assert snapshot_identity == source_identity
    assert snapshot["manifest"]["source_set_hash"] == _source_set_hash(
        snapshot["provenance"]["fields"],
        freshness_seconds=_policy().freshness_seconds,
        freshness_evaluated_at=EVALUATED_AT.isoformat(),
    )
