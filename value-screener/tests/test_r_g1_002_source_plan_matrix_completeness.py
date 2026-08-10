from __future__ import annotations

import copy
import hashlib
import json
import sys
from datetime import datetime
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
    build_parser,
    promote_provider_snapshot,
)


PLAN_VERSION = "test-plan-v1"
TICKERS = ("600519.SH", "600009.SH")
EVALUATED_AT = datetime.fromisoformat("2026-08-05T00:01:00+00:00")


def _semantic_hash(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _policy(*, methods=None) -> FieldQualificationPolicy:
    return FieldQualificationPolicy.from_mapping(
        version="test-policy-v1",
        tickers=TICKERS,
        methods=methods or {"quote": ("last_price",)},
        allowed_providers=("fixture",),
        freshness_seconds=300,
        probe_plan_version=PLAN_VERSION,
    )


def _evidence(ticker: str, *, field: str = "last_price", value: float = 123.4):
    response_hash = f"{ticker}-{field}-response"
    return {
        "provider_family": "baseline",
        "provider": "fixture",
        "method": "quote",
        "market": "SH",
        "ticker": ticker,
        "security_type": "consumer",
        "field": field,
        "raw_field": field,
        "value": value,
        "unit": "CNY/share",
        "currency": "CNY",
        "as_of": "2026-08-04",
        "report_period": None,
        "status": "available",
        "reason": None,
        "response_hash": response_hash,
        "retrieved_at": "2026-08-05T00:00:00+00:00",
        "provenance": {
            "provider_family": "baseline",
            "provider": "fixture",
            "method": "quote",
            "market": "SH",
            "ticker": ticker,
            "raw_field": field,
            "response_hash": response_hash,
            "retrieved_at": "2026-08-05T00:00:00+00:00",
        },
    }


def _write_source_run(
    tmp_path: Path,
    evidence: list[dict],
    *,
    plan_cases=None,
    run_id: str = "source-run",
    plan_run_id: str | None = None,
    evidence_run_id: str | None = None,
    include_plan: bool = True,
    include_hashes: bool = True,
) -> Path:
    source = tmp_path / "qualification" / run_id
    source.mkdir(parents=True)
    cases = plan_cases or [
        {
            "ticker": ticker,
            "market": "SH",
            "security_type": "consumer",
            "method": "quote",
            "fields": ["last_price"],
        }
        for ticker in TICKERS
    ]
    plan = {
        "run_id": plan_run_id or run_id,
        "version": PLAN_VERSION,
        "plan_hash": _semantic_hash({"version": PLAN_VERSION, "cases": cases}),
        "cases": cases,
    }
    manifest = {
        "schema_version": "a-share-provider-qualification-v1",
        "run_id": run_id,
        "plan_version": PLAN_VERSION,
        "plan_hash": plan["plan_hash"],
        "ticker_set_hash": _semantic_hash(sorted(TICKERS)),
        "completion_status": "completed",
        "evidence_count": len(evidence),
        "field_status_counts": {"available": len(evidence)},
        "artifact_status": {"plan": "written", "evidence": "written"},
        "artifacts": {"plan": "plan.json", "evidence": "evidence.json"},
    }
    if include_plan:
        _write_json(source / "plan.json", plan)
    evidence_payload = {
        "run_id": evidence_run_id or run_id,
        "evidence": evidence,
    }
    _write_json(source / "evidence.json", evidence_payload)
    if include_hashes:
        manifest["artifact_hashes"] = {
            "plan": hashlib.sha256((source / "plan.json").read_bytes()).hexdigest()
            if include_plan
            else None,
            "evidence": hashlib.sha256((source / "evidence.json").read_bytes()).hexdigest(),
        }
        manifest_for_hash = copy.deepcopy(manifest)
        manifest_for_hash.pop("artifact_hashes")
        manifest["manifest_hash"] = _semantic_hash(manifest_for_hash)
    _write_json(source / "manifest.json", manifest)
    return source


def test_missing_plan_json_is_rejected(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])
    (source / "plan.json").unlink()

    with pytest.raises(QualificationSourceError, match="plan"):
        load_qualification_run(source)


def test_truncated_plan_json_is_rejected(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])
    (source / "plan.json").write_text('{"run_id":', encoding="utf-8")

    with pytest.raises(QualificationSourceError, match="plan"):
        load_qualification_run(source)


@pytest.mark.parametrize("artifact", ["plan", "evidence", "manifest"])
def test_artifact_hash_mismatch_is_rejected(tmp_path, artifact):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])
    path = source / f"{artifact}.json"
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(QualificationSourceError, match="hash"):
        load_qualification_run(source)


@pytest.mark.parametrize("mismatch", ["run", "ticker", "field"])
def test_source_identity_mismatch_is_rejected(tmp_path, mismatch):
    evidence = [_evidence(ticker) for ticker in TICKERS]
    if mismatch == "run":
        source = _write_source_run(
            tmp_path, evidence, evidence_run_id="different-run"
        )
    elif mismatch == "ticker":
        evidence[0]["ticker"] = "000858.SZ"
        source = _write_source_run(tmp_path, evidence)
    else:
        evidence[0]["field"] = "pb"
        evidence[0]["raw_field"] = "pb"
        source = _write_source_run(tmp_path, evidence)

    with pytest.raises(QualificationSourceError, match="identity|plan|run_id"):
        load_qualification_run(source)


def test_evidence_content_tampering_is_rejected(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])
    payload = json.loads((source / "evidence.json").read_text(encoding="utf-8"))
    payload["evidence"][0]["value"] = 999.9
    _write_json(source / "evidence.json", payload)

    with pytest.raises(QualificationSourceError, match="hash"):
        load_qualification_run(source)


def test_manifest_plan_hash_cross_identity_is_rejected(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["plan_hash"] = "not-the-plan-hash"
    manifest_for_hash = copy.deepcopy(manifest)
    manifest_for_hash.pop("artifact_hashes")
    manifest_for_hash.pop("manifest_hash")
    manifest["manifest_hash"] = _semantic_hash(manifest_for_hash)
    _write_json(source / "manifest.json", manifest)

    with pytest.raises(QualificationSourceError, match="manifest/plan hash"):
        load_qualification_run(source)


def test_completed_source_requires_every_planned_identity_in_evidence(tmp_path):
    plan_cases = [
        {
            "ticker": "600519.SH",
            "market": "SH",
            "security_type": "consumer",
            "method": "quote",
            "fields": ["last_price", "turnover_rate"],
        },
        {
            "ticker": "600009.SH",
            "market": "SH",
            "security_type": "transport",
            "method": "quote",
            "fields": ["last_price"],
        },
    ]
    source = _write_source_run(
        tmp_path,
        [_evidence("600519.SH"), _evidence("600009.SH")],
        plan_cases=plan_cases,
    )

    with pytest.raises(QualificationSourceError, match="missing frozen plan identity"):
        load_qualification_run(source)


def test_completed_source_requires_explicit_written_artifact_status(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["artifact_status"].pop("plan")
    _write_json(source / "manifest.json", manifest)

    with pytest.raises(QualificationSourceError, match="artifacts are not written"):
        load_qualification_run(source)


def test_completed_source_requires_evidence_run_identity(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])
    payload = json.loads((source / "evidence.json").read_text(encoding="utf-8"))
    payload.pop("run_id")
    _write_json(source / "evidence.json", payload)

    with pytest.raises(QualificationSourceError, match="hash"):
        load_qualification_run(source)


def test_missing_required_field_group_is_rejected(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])

    decision = evaluate_qualification_run(
        source,
        policy=_policy(methods={"quote": ("last_price", "turnover_rate")}),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "blocked"
    assert "missing_field_group" in {
        reason
        for item in decision["decisions"]
        for reason in item["reason_codes"]
    }


def test_partial_field_matrix_cannot_be_qualified(tmp_path):
    source = _write_source_run(
        tmp_path,
        [_evidence(ticker) for ticker in TICKERS],
    )

    decision = evaluate_qualification_run(
        source,
        policy=_policy(methods={"quote": ("last_price", "turnover_rate")}),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "blocked"
    assert decision["promoted_evidence"] == []


def test_cli_requires_and_binds_explicit_probe_plan_version():
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "source",
                "output",
                "--provider",
                "fixture",
                "--method-field",
                "quote:last_price",
                "--probe-plan-version",
                "wrong-plan",
            ]
        )


def test_complete_legal_source_run_qualifies(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])

    decision = evaluate_qualification_run(
        source,
        policy=_policy(),
        evaluated_at=EVALUATED_AT,
    )

    assert decision["status"] == "qualified"
    assert decision["promoted_evidence"]


def test_promotion_preserves_source_bytes_byte_for_byte(tmp_path):
    source = _write_source_run(tmp_path, [_evidence(ticker) for ticker in TICKERS])
    before = {
        path.name: path.read_bytes()
        for path in source.iterdir()
        if path.is_file()
    }

    promote_provider_snapshot(
        source,
        output_root=tmp_path / "promotions",
        policy=_policy(),
        run_id="promotion-1",
        evaluated_at=EVALUATED_AT,
    )

    after = {
        path.name: path.read_bytes()
        for path in source.iterdir()
        if path.is_file()
    }
    assert after == before
