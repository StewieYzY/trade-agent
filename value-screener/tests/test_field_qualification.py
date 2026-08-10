from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.field_qualification import (  # noqa: E402
    FieldQualificationPolicy,
    QualificationSourceError,
    evaluate_qualification_run,
    load_qualification_run,
)
from scripts.promote_provider_snapshot import (  # noqa: E402
    promote_provider_snapshot,
)


EVALUATED_AT = datetime(2026, 8, 5, 0, 1, tzinfo=timezone.utc)


def _policy(*, allowed_providers: tuple[str, ...] = ("fixture",)):
    return FieldQualificationPolicy.from_mapping(
        version="test-policy-v1",
        tickers=("600519.SH", "600009.SH"),
        methods={"quote": ("last_price",)},
        allowed_providers=allowed_providers,
        freshness_seconds=300,
    )


def _evidence(
    ticker: str,
    *,
    value: float = 123.4,
    provider: str = "fixture",
    status: str = "available",
    retrieved_at: str = "2026-08-05T00:00:00+00:00",
    freshness_status: str | None = None,
    include_provenance: bool = True,
    field: str = "last_price",
):
    item = {
        "provider_family": "baseline",
        "provider": provider,
        "method": "quote",
        "market": "SH",
        "ticker": ticker,
        "security_type": "consumer",
        "field": field,
        "raw_field": field,
        "value": value if status == "available" else None,
        "unit": "CNY/share",
        "currency": "CNY",
        "as_of": "2026-08-04",
        "report_period": None,
        "status": status,
        "reason": None if status == "available" else f"{status} from provider",
        "response_hash": f"{ticker}-{provider}-hash",
        "retrieved_at": retrieved_at,
        "provenance": {
            "provider_family": "baseline",
            "provider": provider,
            "method": "quote",
            "market": "SH",
            "ticker": ticker,
            "raw_field": field,
            "response_hash": f"{ticker}-{provider}-hash",
            "retrieved_at": retrieved_at,
        },
    }
    if not include_provenance:
        item["provenance"] = {}
    if freshness_status is not None:
        item["freshness_status"] = freshness_status
    return item


def _write_source_run(
    tmp_path: Path,
    evidence: list[dict],
    *,
    completion_status: str = "completed",
    evidence_count: int | None = None,
) -> Path:
    source = tmp_path / "qualification" / "source-run"
    source.mkdir(parents=True)
    count = len(evidence) if evidence_count is None else evidence_count
    cases_by_identity: dict[tuple[str, str], dict] = {}
    for item in evidence:
        key = (item["ticker"], item["method"])
        case = cases_by_identity.setdefault(
            key,
            {
                "ticker": item["ticker"],
                "market": item.get("market"),
                "security_type": item.get("security_type"),
                "method": item["method"],
                "fields": [],
            },
        )
        if item["field"] not in case["fields"]:
            case["fields"].append(item["field"])
    cases = list(cases_by_identity.values())
    plan = {
        "run_id": "source-run",
        "version": "test-plan-v1",
        "plan_hash": hashlib.sha256(
            json.dumps(
                {"version": "test-plan-v1", "cases": cases},
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "cases": cases,
    }
    (source / "manifest.json").write_text(
        json.dumps({}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (source / "plan.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (source / "evidence.json").write_text(
        json.dumps(
            {"run_id": "source-run", "evidence": evidence},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest = {
        "run_id": "source-run",
        "plan_version": "test-plan-v1",
        "plan_hash": plan["plan_hash"],
        "ticker_set_hash": hashlib.sha256(
            json.dumps(
                sorted({item["ticker"] for item in evidence}),
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        "completion_status": completion_status,
        "evidence_count": count,
        "field_status_counts": {"available": len(evidence)},
        "artifact_status": {"plan": "written", "evidence": "written"},
        "artifacts": {"plan": "plan.json", "evidence": "evidence.json"},
    }
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


def test_complete_group_is_promoted_without_mutating_source(tmp_path):
    evidence = [_evidence("600519.SH"), _evidence("600009.SH", value=88.0)]
    source = _write_source_run(tmp_path, evidence)
    original = copy.deepcopy(evidence)

    decision = evaluate_qualification_run(
        source,
        policy=_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "qualified"
    assert decision["promoted_evidence"][0]["eligibility"] == "production_eligible"
    assert decision["decisions"][0]["decision"] == "qualified"
    assert evidence == original


def test_missing_ticker_rejects_whole_group(tmp_path):
    source = _write_source_run(tmp_path, [_evidence("600519.SH")])

    decision = evaluate_qualification_run(
        source,
        policy=_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "blocked"
    assert decision["promoted_evidence"] == []
    assert decision["decisions"][0]["reason_codes"] == ["missing_ticker_coverage"]


@pytest.mark.parametrize("status", ["record_not_found", "source_failed", "invalid_value", "not_evaluated"])
def test_failure_status_rejects_group(status, tmp_path):
    source = _write_source_run(
        tmp_path,
        [_evidence("600519.SH"), _evidence("600009.SH", status=status)],
    )

    decision = evaluate_qualification_run(
        source,
        policy=_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "blocked"
    assert decision["promoted_evidence"] == []
    assert "non_available_status" in decision["decisions"][0]["reason_codes"]


def test_missing_provenance_and_explicit_unknown_freshness_reject_group(tmp_path):
    source = _write_source_run(
        tmp_path,
        [
            _evidence("600519.SH", include_provenance=False),
            _evidence("600009.SH", freshness_status="unknown"),
        ],
    )

    decision = evaluate_qualification_run(
        source,
        policy=_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "blocked"
    assert decision["promoted_evidence"] == []
    assert {
        "invalid_evidence",
        "unknown_freshness",
    }.intersection(decision["decisions"][0]["reason_codes"])


def test_unexpected_field_is_rejected_without_poisoning_in_policy_group(tmp_path):
    evidence = [
        _evidence("600519.SH"),
        _evidence("600009.SH", value=88.0),
        _evidence("600519.SH", field="pb"),
    ]
    source = _write_source_run(tmp_path, evidence)

    decision = evaluate_qualification_run(
        source,
        policy=_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "qualified"
    assert len(decision["promoted_evidence"]) == 2
    assert decision["unexpected_evidence"][0]["reason"] == "outside_policy_matrix"


def test_candidate_provider_is_not_promoted_without_explicit_allowance(tmp_path):
    source = _write_source_run(
        tmp_path,
        [
            _evidence("600519.SH", provider="longbridge"),
            _evidence("600009.SH", provider="longbridge"),
        ],
    )

    decision = evaluate_qualification_run(
        source,
        policy=_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "blocked"
    assert decision["promoted_evidence"] == []
    assert decision["decisions"][0]["reason_codes"] == ["provider_not_allowed"]


def test_source_run_must_be_complete_and_counted(tmp_path):
    incomplete = _write_source_run(
        tmp_path / "incomplete",
        [_evidence("600519.SH"), _evidence("600009.SH")],
        completion_status="incomplete",
    )
    with pytest.raises(QualificationSourceError, match="completed"):
        load_qualification_run(incomplete)

    mismatch = _write_source_run(
        tmp_path / "mismatch",
        [_evidence("600519.SH"), _evidence("600009.SH")],
        evidence_count=1,
    )
    with pytest.raises(QualificationSourceError, match="count"):
        load_qualification_run(mismatch)


def test_conflicting_units_reject_group(tmp_path):
    second = _evidence("600009.SH", value=88.0)
    second["unit"] = "%"
    source = _write_source_run(
        tmp_path,
        [_evidence("600519.SH"), second],
    )

    decision = evaluate_qualification_run(
        source,
        policy=_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "blocked"
    assert decision["promoted_evidence"] == []
    assert "metadata_conflict" in decision["decisions"][0]["reason_codes"]


def test_promotion_writes_decision_and_canonical_snapshot_without_mutating_source(
    tmp_path,
):
    evidence = [_evidence("600519.SH"), _evidence("600009.SH", value=88.0)]
    source = _write_source_run(tmp_path / "source", evidence)
    source_before = {
        path.name: path.read_bytes()
        for path in source.iterdir()
        if path.is_file()
    }

    result = promote_provider_snapshot(
        source,
        output_root=tmp_path / "promotions",
        policy=_policy(),
        run_id="promotion-1",
        evaluated_at=EVALUATED_AT,
    )

    run_dir = tmp_path / "promotions" / "promotion-1"
    assert result["status"] == "qualified"
    assert (run_dir / "decision.json").exists()
    assert (run_dir / "records.json").exists()
    assert json.loads((run_dir / "records.json").read_text())["600519.SH"][
        "last_price"
    ] == 123.4
    assert {
        path.name: path.read_bytes()
        for path in source.iterdir()
        if path.is_file()
    } == source_before


def test_blocked_promotion_writes_decision_but_no_canonical_records(tmp_path):
    source = _write_source_run(tmp_path / "source", [_evidence("600519.SH")])

    result = promote_provider_snapshot(
        source,
        output_root=tmp_path / "promotions",
        policy=_policy(),
        run_id="blocked-promotion",
        evaluated_at=EVALUATED_AT,
    )

    run_dir = tmp_path / "promotions" / "blocked-promotion"
    assert result["status"] == "blocked"
    assert (run_dir / "decision.json").exists()
    assert not (run_dir / "records.json").exists()


def test_promotion_rejects_duplicate_run_and_protected_output_root(tmp_path):
    source = _write_source_run(
        tmp_path / "source",
        [_evidence("600519.SH"), _evidence("600009.SH")],
    )
    output_root = tmp_path / "promotions"
    promote_provider_snapshot(
        source,
        output_root=output_root,
        policy=_policy(),
        run_id="duplicate",
        evaluated_at=EVALUATED_AT,
    )
    with pytest.raises(ValueError, match="already exists"):
        promote_provider_snapshot(
            source,
            output_root=output_root,
            policy=_policy(),
            run_id="duplicate",
            evaluated_at=EVALUATED_AT,
        )

    protected_root = Path(__file__).resolve().parents[1] / "data" / "cache"
    with pytest.raises(ValueError, match="protected"):
        promote_provider_snapshot(
            source,
            output_root=protected_root,
            policy=_policy(),
            run_id="protected",
            evaluated_at=EVALUATED_AT,
        )
