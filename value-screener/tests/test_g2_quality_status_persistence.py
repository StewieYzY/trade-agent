"""G2 4.2：质量状态持久化、恢复与 fail-closed 行为。"""
from __future__ import annotations

import json

import pytest

from data.lib.quality_status import (
    QualityStatusError,
    RunQualityRecord,
    read_quality_record,
    replace_quality_record,
    write_quality_record,
)


def _record(
    *,
    run_id: str = "run-42",
    status: str = "warning",
    reasons: tuple[str, ...] = ("r1_grounding_warning",),
    completed_stages: tuple[str, ...] = ("r1",),
    final_quality_gate: str = "warning",
    artifact_path: str | None = None,
) -> RunQualityRecord:
    return RunQualityRecord(
        canonical_ticker="600009.SH",
        run_id=run_id,
        status=status,
        reasons=reasons,
        completed_stages=completed_stages,
        final_quality_gate=final_quality_gate,
        artifact_path=artifact_path,
    )


def _dossier() -> dict:
    return {
        "core_snapshot": {
            "ticker": "600009.SH",
            "name": "测试公司",
            "market_cap": 1_000_000_000,
            "pe_ttm": 20.0,
            "roe_3y": [10.0, 11.0, 12.0],
            "net_margin": 8.0,
        },
        "research_dossier": {
            "main_business": {"by_industry": [{"industry": "测试行业"}]},
            "peers": {"peer_avg_pe": 22.0},
            "research": {"consensus_eps": 1.2},
        },
    }


def _agent_json(name: str, signal: str) -> str:
    return json.dumps(
        {
            "name": name,
            "signal": signal,
            "conviction": 60,
            "core_thesis": f"{name} 的测试判断",
            "key_metrics": ["PE 20.0"],
            "risks": ["需求变化"],
            "what_would_change_my_mind": "连续两季恶化",
            "out_of_circle": False,
        },
        ensure_ascii=False,
    )


def test_replace_preserves_completed_stages_from_prior_evidence(tmp_path):
    write_quality_record(
        tmp_path,
        _record(
            status="da_skipped",
            reasons=("low_divergence",),
            completed_stages=("r1", "r2", "da"),
            final_quality_gate="warning",
        ),
    )

    replace_quality_record(
        tmp_path,
        _record(
            status="incomplete",
            reasons=("synthesizer_interrupted",),
            completed_stages=("r1", "r2", "da", "synthesizer"),
            final_quality_gate="not_run",
        ),
    )

    record = read_quality_record(tmp_path, "600009.SH", "run-42")
    assert record is not None
    assert record.completed_stages == ("r1", "r2", "da", "synthesizer")
    assert record.reasons == ("low_divergence", "synthesizer_interrupted")


def test_replace_can_explicitly_remove_unfinished_stage(tmp_path):
    write_quality_record(
        tmp_path,
        _record(
            status="complete",
            reasons=(),
            completed_stages=("r1", "r2", "da", "synthesizer", "final_validation"),
            final_quality_gate="passed",
        ),
    )

    replace_quality_record(
        tmp_path,
        _record(
            status="incomplete",
            reasons=("final_validation_interrupted",),
            completed_stages=("r1", "r2", "da", "synthesizer"),
            final_quality_gate="not_run",
        ),
        completed_stages_to_remove=("final_validation",),
    )

    record = read_quality_record(tmp_path, "600009.SH", "run-42")
    assert record is not None
    assert record.completed_stages == ("r1", "r2", "da", "synthesizer")


def test_missing_execution_mode_is_schema_invalid(tmp_path):
    path = tmp_path / "quality_status" / "600009.SH" / "run-42" / "record.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "canonical_ticker": "600009.SH",
                "run_id": "run-42",
                "status": "complete",
                "reasons": [],
                "completed_stages": ["r1", "r2", "da", "synthesizer", "final_validation"],
                "final_quality_gate": "passed",
                "schema_version": "g2-run-quality-status-v1",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(QualityStatusError, match="execution_mode"):
        read_quality_record(tmp_path, "600009.SH", "run-42")


def test_failed_record_can_be_downgraded_to_incomplete(tmp_path):
    write_quality_record(
        tmp_path,
        _record(
            status="failed",
            reasons=("agent_failed",),
            completed_stages=("agent",),
            final_quality_gate="failed",
        ),
    )

    replace_quality_record(
        tmp_path,
        _record(
            status="incomplete",
            reasons=("fallback_quality_persistence_interrupted",),
            completed_stages=(),
            final_quality_gate="not_run",
        ),
    )

    record = read_quality_record(tmp_path, "600009.SH", "run-42")
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == (
        "agent_failed",
        "fallback_quality_persistence_interrupted",
    )


def test_failed_record_cannot_be_downgraded_to_warning(tmp_path):
    write_quality_record(
        tmp_path,
        _record(
            status="failed",
            reasons=("hard_failure",),
            completed_stages=("r1",),
            final_quality_gate="failed",
        ),
    )

    with pytest.raises(QualityStatusError, match="unsafe status transition"):
        replace_quality_record(
            tmp_path,
            _record(
                status="warning",
                reasons=("soft_warning",),
                completed_stages=("r1",),
                final_quality_gate="warning",
            ),
        )


def test_failed_record_cannot_be_upgraded_to_complete_even_when_requested(tmp_path):
    write_quality_record(
        tmp_path,
        _record(
            status="failed",
            reasons=("hard_failure",),
            completed_stages=("r1",),
            final_quality_gate="failed",
        ),
    )

    with pytest.raises(QualityStatusError, match="status upgrade"):
        replace_quality_record(
            tmp_path,
            _record(
                status="complete",
                reasons=(),
                completed_stages=("r1", "r2", "da", "synthesizer", "final_validation"),
                final_quality_gate="passed",
            ),
            allow_complete_upgrade=True,
        )


def test_l4_rejects_quality_record_with_misbound_artifact(tmp_path):
    from datetime import date

    from monitor.aggregation import _read_l3_output

    run_date = date.today().isoformat()
    watchlist_dir = tmp_path / "watchlist"
    watchlist_path = watchlist_dir / "600009.SH" / "run-42" / f"{run_date}.json"
    watchlist_path.parent.mkdir(parents=True)
    watchlist_path.write_text(
        json.dumps(
            {
                "ticker": "600009.SH",
                "run_id": "run-42",
                "date": run_date,
                "final_verdict": "bullish",
                "conviction": 80,
                "quality_record_path": "quality_status/600009.SH/run-42/record.json",
                "run_quality_status": "complete",
                "final_quality_gate": "passed",
                "success_cache_eligible": True,
            }
        ),
        encoding="utf-8",
    )
    misbound_artifact = (
        tmp_path / "debate" / "600519.SH" / "other-run" / f"{run_date}.md"
    )
    misbound_artifact.parent.mkdir(parents=True)
    misbound_artifact.write_text("## Round 1\n", encoding="utf-8")
    write_quality_record(
        tmp_path,
        _record(
            artifact_path=str(misbound_artifact),
            status="complete",
            reasons=(),
            completed_stages=("r1", "r2", "da", "synthesizer", "final_validation"),
            final_quality_gate="passed",
        ),
    )

    result = _read_l3_output("600009.SH", run_date, watchlist_dir)

    assert result is not None
    assert result["run_quality_status"] == "incomplete"
    assert result["success_cache_eligible"] is False
    assert result["_quality_proof_valid"] is False
    assert "quality_record_proof_invalid" in result["run_quality_reasons"]


def test_l4_rejects_quality_record_with_mode_mismatch(tmp_path):
    from datetime import date

    from monitor.aggregation import _read_l3_output

    run_date = date.today().isoformat()
    watchlist_dir = tmp_path / "watchlist"
    watchlist_path = watchlist_dir / "600009.SH" / "run-42" / f"{run_date}.json"
    watchlist_path.parent.mkdir(parents=True)
    watchlist_path.write_text(
        json.dumps(
            {
                "ticker": "600009.SH",
                "run_id": "run-42",
                "date": run_date,
                "final_verdict": "bullish",
                "execution_mode": "council",
                "quality_record_path": "quality_status/600009.SH/run-42/record.json",
            }
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "debate" / "600009.SH" / "run-42" / f"{run_date}.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("## Round 1\n", encoding="utf-8")
    write_quality_record(
        tmp_path,
        RunQualityRecord(
            canonical_ticker="600009.SH",
            run_id="run-42",
            status="complete",
            reasons=(),
            completed_stages=("r1", "r2", "da", "synthesizer", "final_validation"),
            final_quality_gate="passed",
            artifact_path=str(artifact),
            execution_mode="single_agent",
        ),
    )

    result = _read_l3_output("600009.SH", run_date, watchlist_dir)

    assert result is not None
    assert result["run_quality_status"] == "incomplete"
    assert result["success_cache_eligible"] is False


def test_cache_misses_when_bound_artifact_is_not_a_file(tmp_path, monkeypatch):
    from datetime import date

    from council.debate import _check_cache

    monkeypatch.chdir(tmp_path)
    run_date = date.today().isoformat()
    artifact = tmp_path / "debate" / "600009.SH" / "run-42" / f"{run_date}.md"
    artifact.mkdir(parents=True)
    write_quality_record(
        tmp_path,
        _record(
            status="complete",
            reasons=(),
            completed_stages=("r1", "r2", "da", "synthesizer", "final_validation"),
            final_quality_gate="passed",
            artifact_path=str(artifact),
        ),
    )

    assert _check_cache("600009.SH", expected_execution_mode="council") is None


def test_l4_invalid_quality_proof_clears_payload_cache_eligibility(tmp_path):
    from datetime import date

    from monitor.aggregation import _read_l3_output

    run_date = date.today().isoformat()
    watchlist_dir = tmp_path / "watchlist"
    path = watchlist_dir / "600009.SH" / "run-42" / f"{run_date}.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "ticker": "600009.SH",
                "run_id": "run-42",
                "date": run_date,
                "final_verdict": "bullish",
                "run_quality_status": "warning",
                "run_quality_reasons": ["warning"],
                "success_cache_eligible": True,
                "quality_record_path": "quality_status/600009.SH/run-42/record.json",
            }
        ),
        encoding="utf-8",
    )

    result = _read_l3_output("600009.SH", run_date, watchlist_dir)

    assert result is not None
    assert result["success_cache_eligible"] is False
    assert result["_quality_proof_valid"] is False


def test_l4_invalid_non_complete_artifact_binding_marks_proof_invalid(tmp_path):
    from datetime import date

    from monitor.aggregation import _read_l3_output

    run_date = date.today().isoformat()
    watchlist_dir = tmp_path / "watchlist"
    path = watchlist_dir / "600009.SH" / "run-42" / f"{run_date}.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "ticker": "600009.SH",
                "run_id": "run-42",
                "date": run_date,
                "final_verdict": "bullish",
                "run_quality_status": "warning",
                "run_quality_reasons": ["warning"],
                "success_cache_eligible": False,
                "quality_record_path": "quality_status/600009.SH/run-42/record.json",
            }
        ),
        encoding="utf-8",
    )
    artifact = tmp_path / "debate" / "600519.SH" / "other-run" / f"{run_date}.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("diagnostic", encoding="utf-8")
    write_quality_record(
        tmp_path,
        _record(
            status="warning",
            artifact_path=str(artifact),
            final_quality_gate="warning",
        ),
    )

    result = _read_l3_output("600009.SH", run_date, watchlist_dir)

    assert result is not None
    assert result["_quality_proof_valid"] is False


def test_run_id_is_normalized_before_persistence():
    record = RunQualityRecord(
        canonical_ticker="600009.SH",
        run_id="  run-42  ",
        status="warning",
    )

    assert record.run_id == "run-42"


def test_skipped_single_agent_stages_are_not_marked_completed(tmp_path, monkeypatch):
    from council.debate import run_debate

    monkeypatch.chdir(tmp_path)

    async def fake_call(*_args, **_kwargs):
        return (_agent_json("buffett", "neutral"), {})

    monkeypatch.setattr("council.debate.call_llm", fake_call)

    result = __import__("asyncio").run(
        run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
            force=True,
        )
    )
    record = read_quality_record(tmp_path, "600009.SH", result.run_id)

    assert record is not None
    assert record.completed_stages == ("r1", "final_validation")
    assert "r2" not in record.completed_stages
    assert "da" not in record.completed_stages
    assert "synthesizer" not in record.completed_stages


def test_usage_artifact_failure_does_not_mark_synthesizer_completed(
    tmp_path, monkeypatch
):
    from council.debate import run_debate

    monkeypatch.chdir(tmp_path)

    async def fake_call(*_args, **_kwargs):
        return (_agent_json("buffett", "neutral"), {})

    def fail_usage_summary(*_args, **_kwargs):
        raise OSError("usage artifact failed")

    monkeypatch.setattr("council.debate.call_llm", fake_call)
    monkeypatch.setattr("council.debate._append_usage_summary", fail_usage_summary)

    with pytest.raises(OSError, match="usage artifact failed"):
        __import__("asyncio").run(
            run_debate(
                "600009.SH",
                agents=["buffett"],
                features=_dossier(),
                force=True,
            )
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("quality_artifact_interrupted",)
    assert record.completed_stages == ("r1",)


def test_reader_normalizes_non_utf8_record_to_quality_status_error(tmp_path):
    path = tmp_path / "quality_status" / "600009.SH" / "run-42" / "record.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00")

    with pytest.raises(QualityStatusError, match="quality record"):
        read_quality_record(tmp_path, "600009.SH", "run-42")


def test_reader_rejects_non_object_json_record(tmp_path):
    path = write_quality_record(tmp_path, _record())
    path.write_text(json.dumps(["not", "a", "record"]), encoding="utf-8")

    with pytest.raises(QualityStatusError, match="invalid quality record"):
        read_quality_record(tmp_path, "600009.SH", "run-42")
