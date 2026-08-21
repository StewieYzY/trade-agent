from __future__ import annotations

import asyncio
import json
from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from council import fallback
from council.debate import _check_cache, run_debate
from council.schema import AgentOutput
from data.lib.quality_status import (
    QualityStatusError,
    RunQualityRecord,
    is_success_cache_eligible,
    quality_record_path,
    replace_quality_record,
    read_quality_record,
    write_quality_record,
)


def _record(
    *,
    run_id: str = "run-a",
    status: str = "complete",
    final_quality_gate: str = "passed",
    artifact_path: str | None = None,
    execution_mode: str = "council",
    reasons: tuple[str, ...] = (),
    completed_stages: tuple[str, ...] = (
        "r1",
        "r2",
        "da",
        "synthesizer",
        "final_validation",
    ),
) -> RunQualityRecord:
    return RunQualityRecord(
        canonical_ticker="600009.SH",
        run_id=run_id,
        status=status,
        reasons=reasons,
        completed_stages=completed_stages,
        final_quality_gate=final_quality_gate,
        artifact_path=artifact_path,
        execution_mode=execution_mode,
    )


def test_complete_requires_passed_final_quality_gate():
    with pytest.raises(QualityStatusError, match="complete"):
        _record(final_quality_gate="warning")


def test_complete_requires_execution_mode_stages():
    with pytest.raises(QualityStatusError, match="completed_stages"):
        _record(completed_stages=("final_validation",))


def test_replace_cannot_upgrade_incomplete_record_to_complete(tmp_path):
    write_quality_record(
        tmp_path,
        _record(
            status="incomplete",
            final_quality_gate="not_run",
            completed_stages=("r1",),
        ),
    )

    with pytest.raises(QualityStatusError, match="upgrade"):
        replace_quality_record(tmp_path, _record())


def test_unknown_status_is_rejected():
    with pytest.raises(QualityStatusError, match="status"):
        _record(status="passed")


def test_non_complete_status_is_not_success_cache_eligible():
    for status in ("warning", "failed", "incomplete", "runtime_degraded", "da_skipped"):
        assert not is_success_cache_eligible(
            _record(status=status, final_quality_gate="passed")
        )


def test_fallback_complete_record_is_not_council_cache_eligible():
    assert not is_success_cache_eligible(
        _record(
            execution_mode="fallback",
            completed_stages=("agent", "fact_check", "synthesis", "final_validation"),
        )
    )


def test_same_ticker_different_runs_persist_without_overwrite(tmp_path):
    first = write_quality_record(tmp_path, _record(run_id="run-a"))
    second = write_quality_record(tmp_path, _record(run_id="run-b"))

    assert first != second
    assert read_quality_record(tmp_path, "600009.SH", "run-a").run_id == "run-a"
    assert read_quality_record(tmp_path, "600009.SH", "run-b").run_id == "run-b"
    assert quality_record_path(tmp_path, "600009.SH", "run-a").exists()
    assert quality_record_path(tmp_path, "600009.SH", "run-b").exists()


def test_quality_record_refuses_conflicting_rewrite(tmp_path):
    write_quality_record(tmp_path, _record())

    with pytest.raises(FileExistsError, match="overwrite"):
        write_quality_record(tmp_path, _record())


def test_replacing_quality_record_preserves_prior_reasons(tmp_path):
    write_quality_record(
        tmp_path,
        _record(
            status="da_skipped",
            final_quality_gate="warning",
            reasons=("low_divergence",),
        ),
    )
    replace_quality_record(
        tmp_path,
        _record(
            status="incomplete",
            final_quality_gate="not_run",
            reasons=("final_validation_interrupted",),
        ),
    )

    record = read_quality_record(tmp_path, "600009.SH", "run-a")
    assert record is not None
    assert record.reasons == ("low_divergence", "final_validation_interrupted")


@pytest.mark.parametrize("unfinished_stage", ("r2", "da", "synthesizer", "final_validation"))
def test_incomplete_stage_record_is_not_success_cache_eligible(unfinished_stage):
    completed = tuple(
        stage
        for stage in ("r1", "r2", "da", "synthesizer", "final_validation")
        if stage != unfinished_stage
    )

    record = _record(
        status="incomplete",
        final_quality_gate="not_run",
        reasons=(f"{unfinished_stage}_interrupted",),
        completed_stages=completed,
    )

    assert not is_success_cache_eligible(record)


def test_r1_only_debate_markdown_is_not_a_success_cache_hit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "debate" / "600009.SH" / "2026-08-18.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """## Round 1 · 各自表态

### 巴菲特
```json
{"name":"buffett","signal":"neutral","conviction":50,"core_thesis":"仅有 R1","key_metrics":[],"risks":[],"what_would_change_my_mind":"补证据","out_of_circle":false}
```
""",
        encoding="utf-8",
    )

    assert _check_cache("600009.SH") is None


def test_complete_quality_record_is_required_for_success_cache_hit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_id = "single-agent-complete"
    path = (
        tmp_path
        / "debate"
        / "600009.SH"
        / run_id
        / f"{date.today().isoformat()}.md"
    )
    path.parent.mkdir(parents=True)
    path.write_text(
        """## Round 1 · 各自表态

### 巴菲特
```json
{"name":"buffett","signal":"neutral","conviction":50,"core_thesis":"完整记录","key_metrics":[],"risks":[],"what_would_change_my_mind":"补证据","out_of_circle":false}
```
## Round 2 · 交叉质疑
（单 agent 模式，跳过）
## Round 3 · Devil's Advocate
（单 agent 模式，跳过）
## Round 4 · 收敛共识
（单 agent 模式，跳过）
""",
        encoding="utf-8",
    )
    write_quality_record(
        tmp_path,
        _record(
            run_id=run_id,
            artifact_path=str(path),
            execution_mode="single_agent",
            completed_stages=("r1", "final_validation"),
        ),
    )

    assert _check_cache("600009.SH") is not None


def test_success_cache_does_not_cross_execution_modes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_id = "single-agent-run"
    path = tmp_path / "debate" / "600009.SH" / run_id / "2026-08-18.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """## Round 1 · 各自表态

### 巴菲特
```json
{"name":"buffett","signal":"neutral","conviction":50,"core_thesis":"单 agent 完整记录","key_metrics":[],"risks":[],"what_would_change_my_mind":"补证据","out_of_circle":false}
```
""",
        encoding="utf-8",
    )
    write_quality_record(
        tmp_path,
        _record(
            run_id=run_id,
            artifact_path=str(path),
            execution_mode="single_agent",
            completed_stages=("r1", "final_validation"),
        ),
    )

    assert _check_cache("600009.SH", expected_execution_mode="council") is None


def test_latest_mode_mismatch_blocks_older_matching_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from datetime import date

    today = date.today().isoformat()
    md = """## Round 1 · 各自表态

### 巴菲特
```json
{"name":"buffett","signal":"neutral","conviction":50,"core_thesis":"完整记录","key_metrics":[],"risks":[],"what_would_change_my_mind":"补证据","out_of_circle":false}
```
"""
    older_path = tmp_path / "debate" / "600009.SH" / "older-council" / f"{today}.md"
    older_path.parent.mkdir(parents=True)
    older_path.write_text(md, encoding="utf-8")
    write_quality_record(
        tmp_path,
        _record(
            run_id="older-council",
            artifact_path=str(older_path),
            execution_mode="council",
        ),
    )

    newer_path = tmp_path / "debate" / "600009.SH" / "newer-single" / f"{today}.md"
    newer_path.parent.mkdir(parents=True)
    newer_path.write_text(md, encoding="utf-8")
    write_quality_record(
        tmp_path,
        _record(
            run_id="newer-single",
            artifact_path=str(newer_path),
            execution_mode="single_agent",
            completed_stages=("r1", "final_validation"),
        ),
    )

    assert _check_cache("600009.SH", expected_execution_mode="council") is None


def test_complete_record_with_reasons_is_rejected():
    with pytest.raises(QualityStatusError, match="reasons"):
        _record(reasons=("low_divergence",))


def test_success_cache_does_not_cross_dates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_id = "yesterday-run"
    path = tmp_path / "debate" / "600009.SH" / run_id / "2026-08-17.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """## Round 1 · 各自表态

### 巴菲特
```json
{"name":"buffett","signal":"neutral","conviction":50,"core_thesis":"昨日结果","key_metrics":[],"risks":[],"what_would_change_my_mind":"补证据","out_of_circle":false}
```
""",
        encoding="utf-8",
    )
    write_quality_record(
        tmp_path,
        _record(
            run_id=run_id,
            artifact_path=str(path),
            execution_mode="single_agent",
            completed_stages=("r1", "final_validation"),
        ),
    )

    assert _check_cache("600009.SH", expected_execution_mode="single_agent") is None


def test_quality_record_reader_rejects_payload_path_identity_mismatch(tmp_path):
    path = write_quality_record(tmp_path, _record())
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["canonical_ticker"] = "600519.SH"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(QualityStatusError, match="does not match requested"):
        read_quality_record(tmp_path, "600009.SH", "run-a")


def test_success_cache_rejects_artifact_outside_ticker_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    outside = tmp_path / "debate" / "600519.SH" / "other-run" / "2026-08-18.md"
    outside.parent.mkdir(parents=True)
    outside.write_text(
        """## Round 1 · 各自表态

### 巴菲特
```json
{"name":"buffett","signal":"neutral","conviction":50,"core_thesis":"其他 run 产物","key_metrics":[],"risks":[],"what_would_change_my_mind":"补证据","out_of_circle":false}
```
""",
        encoding="utf-8",
    )
    write_quality_record(
        tmp_path,
        _record(
            artifact_path=str(outside),
            execution_mode="single_agent",
            completed_stages=("r1", "final_validation"),
        ),
    )

    assert _check_cache(
        "600009.SH",
        expected_execution_mode="single_agent",
    ) is None


def test_latest_non_complete_record_blocks_older_complete_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "debate" / "600009.SH" / "2026-08-18.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        """## Round 1 · 各自表态

### 巴菲特
```json
{"name":"buffett","signal":"neutral","conviction":50,"core_thesis":"状态覆盖","key_metrics":[],"risks":[],"what_would_change_my_mind":"补证据","out_of_circle":false}
```
""",
        encoding="utf-8",
    )
    write_quality_record(
        tmp_path,
        _record(run_id="old-complete", artifact_path=str(path)),
    )
    write_quality_record(
        tmp_path,
        _record(
            run_id="new-warning",
            status="warning",
            final_quality_gate="warning",
            reasons=("new_warning",),
            artifact_path=str(path),
        ),
    )

    assert _check_cache("600009.SH") is None


def test_latest_invalid_record_blocks_older_complete_cache(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from datetime import date

    today = date.today().isoformat()
    md = """## Round 1 · 各自表态

### 巴菲特
```json
{"name":"buffett","signal":"neutral","conviction":50,"core_thesis":"状态覆盖","key_metrics":[],"risks":[],"what_would_change_my_mind":"补证据","out_of_circle":false}
```
"""
    older_path = tmp_path / "debate" / "600009.SH" / "old-complete" / f"{today}.md"
    older_path.parent.mkdir(parents=True)
    older_path.write_text(md, encoding="utf-8")
    write_quality_record(
        tmp_path,
        _record(run_id="old-complete", artifact_path=str(older_path)),
    )

    newer_path = tmp_path / "debate" / "600009.SH" / "new-invalid" / f"{today}.md"
    newer_path.parent.mkdir(parents=True)
    newer_path.write_text(md, encoding="utf-8")
    record_path = write_quality_record(
        tmp_path,
        _record(run_id="new-invalid", artifact_path=str(newer_path)),
    )
    record_path.write_text("{invalid json", encoding="utf-8")

    assert _check_cache("600009.SH") is None


def test_quality_record_is_readable_as_independent_diagnostic(tmp_path):
    path = write_quality_record(
        tmp_path,
        _record(
            status="warning",
            reasons=("r1_grounding_warning",),
            final_quality_gate="warning",
        ),
    )

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["status"] == "warning"
    assert payload["reasons"] == ["r1_grounding_warning"]
    assert read_quality_record(tmp_path, "600009.SH", "run-a").status == "warning"


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


@pytest.mark.anyio
async def test_r2_interruption_persists_incomplete_quality_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    responses = [
        (_agent_json("buffett", "bullish"), {}),
        (_agent_json("munger", "bearish"), {}),
    ]
    calls = 0

    async def fake_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise TimeoutError("R2 interrupted")
        return responses.pop(0) if responses else (_agent_json("buffett", "bullish"), {})

    with patch("council.debate.call_llm", new=AsyncMock(side_effect=fake_call)), \
         patch("council.divergence.compute_divergence", return_value={"level": "medium"}):
        with pytest.raises(TimeoutError, match="R2 interrupted"):
            await run_debate(
                "600009.SH",
                agents=["buffett", "munger"],
                features=_dossier(),
            )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("r2_interrupted",)
    assert not is_success_cache_eligible(record)


@pytest.mark.anyio
async def test_r1_circular_reference_persists_failed_quality_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def fake_call(*_args, **_kwargs):
        return (
            json.dumps(
                {
                    "name": "buffett",
                    "signal": "neutral",
                    "conviction": 50,
                    "core_thesis": "munger 已经同意",
                    "key_metrics": ["PE 20.0"],
                    "risks": ["需求变化"],
                    "what_would_change_my_mind": "连续两季恶化",
                    "out_of_circle": False,
                }
            ),
            {},
        )

    monkeypatch.setattr("council.debate.call_llm", fake_call)

    with pytest.raises(ValueError, match="circular_reference"):
        await run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "failed"
    assert record.reasons == ("r1_circular_reference",)


@pytest.mark.anyio
async def test_low_r1_error_rate_is_not_runtime_degraded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = 0

    async def fake_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("one R1 failed")
        if calls > 4:
            return (
                json.dumps(
                    {
                        "final_signal": "neutral",
                        "conviction": 30,
                        "consensus_summary": "降级测试",
                    }
                ),
                {},
            )
        agent_names = ("munger", "duan", "feng_liu")
        return (_agent_json(agent_names[calls - 2], "neutral"), {})

    with patch("council.debate.call_llm", new=AsyncMock(side_effect=fake_call)):
        result = await run_debate(
            "600009.SH",
            agents=["buffett", "munger", "duan", "feng_liu"],
            features=_dossier(),
        )

    assert result.run_quality_status == "da_skipped"
    assert "r1_agent_errors:1/4" in result.run_quality_reasons
    assert not result.success_cache_eligible


@pytest.mark.anyio
async def test_non_audit_runs_use_distinct_debate_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def fake_call(*_args, **_kwargs):
        return (_agent_json("buffett", "neutral"), {})

    with patch("council.debate.call_llm", new=AsyncMock(side_effect=fake_call)):
        first = await run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
            force=True,
        )
        second = await run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
            force=True,
        )

    paths = sorted((tmp_path / "debate" / "600009.SH").glob("*/*.md"))
    assert len(paths) == 2
    assert first.run_id != second.run_id
    assert quality_record_path(tmp_path, "600009.SH", first.run_id).exists()
    assert quality_record_path(tmp_path, "600009.SH", second.run_id).exists()


@pytest.mark.anyio
async def test_audit_publish_interruption_downgrades_quality_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def fake_call(*_args, **_kwargs):
        return (_agent_json("buffett", "neutral"), {})

    monkeypatch.setattr("council.debate.call_llm", fake_call)
    monkeypatch.setattr(
        "council.debate._write_council_output",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("audit publish interrupted")
        ),
    )

    with pytest.raises(OSError, match="audit publish interrupted"):
        await run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
            audit_root=tmp_path / "audit",
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert not is_success_cache_eligible(record)


@pytest.mark.anyio
async def test_audit_dossier_write_failure_persists_incomplete_quality_record(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    from data.lib.audit_chain import AuditChainWriter

    original_write = AuditChainWriter.write

    def fail_dossier(self, kind, payload):
        if kind == "dossier":
            raise OSError("audit dossier write failed")
        return original_write(self, kind, payload)

    monkeypatch.setattr(AuditChainWriter, "write", fail_dossier)

    with pytest.raises(OSError, match="audit dossier write failed"):
        await run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
            audit_root=tmp_path / "audit",
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("audit_dossier_interrupted",)


@pytest.mark.anyio
async def test_fallback_blocked_result_has_shared_quality_status(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL_HEAVY", "fixture-model")

    async def failed_call(*_args, **_kwargs):
        raise TimeoutError("fallback interrupted")

    monkeypatch.setattr(fallback, "call_llm", failed_call)

    result = await fallback.run_fallback(
        ticker="600009.SH",
        features=_dossier(),
        output_root=tmp_path / "fallback",
        run_id="fallback-run",
        model="fixture-model",
    )

    assert result["quality_status"] == "blocked"
    assert result["dossier_quality_status"] == "failed"
    assert result["dossier_quality_reasons"]
    assert result["dossier_quality_contract"]["failed"] is True
    assert result["run_quality_status"] == "failed"
    record = read_quality_record(
        tmp_path / "fallback",
        "600009.SH",
        "fallback-run",
    )
    assert record is not None
    assert record.status == "failed"


@pytest.mark.anyio
async def test_fallback_quality_record_write_failure_has_no_clean_result(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_MODEL_HEAVY", "fixture-model")

    async def fake_call(*_args, **_kwargs):
        return (_agent_json("buffett", "neutral"), {})

    original_write = fallback.write_quality_record
    write_calls = 0

    def fail_first_quality_write(*args, **kwargs):
        nonlocal write_calls
        write_calls += 1
        if write_calls == 1:
            raise OSError("quality record write failed")
        return original_write(*args, **kwargs)

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "write_quality_record", fail_first_quality_write)

    with pytest.raises(OSError, match="quality record write failed"):
        await fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path / "fallback",
            run_id="fallback-quality-write-failed",
            model="fixture-model",
        )

    assert not (
        tmp_path / "fallback" / "fallback-quality-write-failed" / "result.json"
    ).exists()


@pytest.mark.anyio
async def test_final_validation_interruption_does_not_leave_complete_record(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    async def fake_call(*_args, **_kwargs):
        return (
            _agent_json("buffett", "neutral"),
            {},
        )

    monkeypatch.setattr("council.debate.call_llm", fake_call)

    def fail_output(*_args, **_kwargs):
        raise OSError("final validation interrupted")

    monkeypatch.setattr("council.debate._write_council_output", fail_output)

    with pytest.raises(OSError, match="final validation interrupted"):
        await run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("final_validation_interrupted",)
    assert not is_success_cache_eligible(record)


@pytest.mark.anyio
async def test_publish_failure_removes_any_clean_watchlist_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def fake_call(*_args, **_kwargs):
        return (_agent_json("buffett", "neutral"), {})

    from council import debate

    original_write = debate._write_council_output

    def write_then_fail(*args, **kwargs):
        output_path = original_write(*args, **kwargs)
        raise OSError(f"publish failed after write: {output_path}")

    monkeypatch.setattr(debate, "call_llm", fake_call)
    monkeypatch.setattr(debate, "_write_council_output", write_then_fail)

    with pytest.raises(OSError, match="publish failed after write"):
        await run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
        )

    outputs = list((tmp_path / "watchlist" / "600009.SH").glob("*/*.json"))
    assert outputs == []
    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert not is_success_cache_eligible(record)


@pytest.mark.anyio
async def test_da_cancellation_persists_incomplete_quality_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    calls = 0

    async def fake_call(*_args, **_kwargs):
        nonlocal calls
        name = ("buffett", "munger")[calls % 2]
        calls += 1
        return (_agent_json(name, "neutral"), {})

    async def cancel_da(*_args, **_kwargs):
        raise asyncio.CancelledError("DA cancelled")

    monkeypatch.setattr("council.debate.call_llm", fake_call)
    monkeypatch.setattr(
        "council.divergence.compute_divergence",
        lambda *_args, **_kwargs: {"level": "medium"},
    )
    monkeypatch.setattr("council.debate._call_da", cancel_da)

    with pytest.raises(asyncio.CancelledError, match="DA cancelled"):
        await run_debate(
            "600009.SH",
            agents=["buffett", "munger"],
            features=_dossier(),
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("da_interrupted",)


@pytest.mark.anyio
async def test_r2_cancellation_persists_incomplete_quality_record(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = 0

    async def fake_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise asyncio.CancelledError("R2 cancelled")
        name = ("buffett", "munger")[calls - 1 if calls < 3 else calls - 2]
        return (_agent_json(name, "neutral"), {})

    monkeypatch.setattr("council.debate.call_llm", fake_call)
    monkeypatch.setattr(
        "council.divergence.compute_divergence",
        lambda *_args, **_kwargs: {"level": "medium"},
    )

    with pytest.raises(asyncio.CancelledError, match="R2 cancelled"):
        await run_debate(
            "600009.SH",
            agents=["buffett", "munger"],
            features=_dossier(),
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("r2_interrupted",)


@pytest.mark.anyio
async def test_stage_markdown_write_failure_persists_incomplete_quality_record(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    async def fake_call(*_args, **_kwargs):
        return (_agent_json("buffett", "neutral"), {})

    def fail_append(*_args, **_kwargs):
        raise OSError("stage markdown write failed")

    monkeypatch.setattr("council.debate.call_llm", fake_call)
    monkeypatch.setattr("council.debate._append_round", fail_append)

    with pytest.raises(OSError, match="stage markdown write failed"):
        await run_debate(
            "600009.SH",
            agents=["buffett"],
            features=_dossier(),
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("r1_interrupted",)


@pytest.mark.anyio
async def test_r1_cancellation_returned_by_gather_persists_incomplete_record(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    surviving_agent = AgentOutput.from_dict(
        "munger",
        {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "R1 survivor",
            "key_metrics": [],
            "risks": [],
            "what_would_change_my_mind": "补证据",
            "out_of_circle": False,
        },
    )
    monkeypatch.setattr(
        "council.debate.call_agent",
        AsyncMock(
            side_effect=[
                asyncio.CancelledError("R1 cancelled"),
                surviving_agent,
            ]
        ),
    )

    with pytest.raises(asyncio.CancelledError):
        await run_debate(
            "600009.SH",
            agents=["buffett", "munger"],
            features=_dossier(),
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    assert len(records) == 1
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("r1_interrupted",)


@pytest.mark.anyio
async def test_synthesizer_cancellation_persists_incomplete_quality_record(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    calls = 0

    async def fake_call(*_args, **_kwargs):
        nonlocal calls
        name = ("buffett", "munger")[calls % 2]
        calls += 1
        return (_agent_json(name, "neutral"), {})

    async def cancel_synthesizer(*_args, **_kwargs):
        raise asyncio.CancelledError("synthesizer cancelled")

    monkeypatch.setattr("council.debate.call_llm", fake_call)
    monkeypatch.setattr(
        "council.divergence.compute_divergence",
        lambda *_args, **_kwargs: {"level": "low"},
    )
    monkeypatch.setattr("council.debate._call_synthesizer", cancel_synthesizer)

    with pytest.raises(asyncio.CancelledError, match="synthesizer cancelled"):
        await run_debate(
            "600009.SH",
            agents=["buffett", "munger"],
            features=_dossier(),
        )

    records = list((tmp_path / "quality_status" / "600009.SH").glob("*/record.json"))
    record = read_quality_record(tmp_path, "600009.SH", records[0].parent.name)
    assert record is not None
    assert record.status == "incomplete"
    assert record.reasons == ("synthesizer_interrupted",)


@pytest.mark.anyio
async def test_low_r1_error_rate_keeps_da_skip_and_all_quality_reasons(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    calls = 0

    async def fake_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("one R1 failed")
        if calls == 5:
            return (
                json.dumps(
                    {
                        "final_signal": "neutral",
                        "conviction": 30,
                        "consensus_summary": "低错误率",
                    }
                ),
                {},
            )
        name = ("munger", "duan", "feng_liu")[calls - 2]
        return (_agent_json(name, "neutral"), {})

    monkeypatch.setattr("council.debate.call_llm", fake_call)
    monkeypatch.setattr(
        "council.divergence.compute_divergence",
        lambda *_args, **_kwargs: {"level": "low"},
    )

    result = await run_debate(
        "600009.SH",
        agents=["buffett", "munger", "duan", "feng_liu"],
        features=_dossier(),
    )

    assert result.run_quality_status == "da_skipped"
    assert set(result.run_quality_reasons) == {
        "r1_agent_errors:1/4",
        "low_divergence",
    }
    assert not result.success_cache_eligible


@pytest.mark.anyio
async def test_fallback_prompt_setup_failure_persists_terminal_quality_record(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_MODEL_HEAVY", "fixture-model")

    def fail_prompt_setup(*_args, **_kwargs):
        raise RuntimeError("prompt setup failed")

    monkeypatch.setattr(fallback, "get_prompt_builder", fail_prompt_setup)

    with pytest.raises(RuntimeError, match="prompt setup failed"):
        await fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path / "fallback",
            run_id="fallback-setup-failure",
            model="fixture-model",
        )

    record = read_quality_record(
        tmp_path / "fallback",
        "600009.SH",
        "fallback-setup-failure",
    )
    assert record is not None
    assert record.status == "failed"
    manifest = json.loads(
        (
            tmp_path
            / "fallback"
            / "fallback-setup-failure"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["state"] == "failed"
    assert manifest["run_quality_status"] == "failed"


@pytest.mark.anyio
async def test_fallback_setup_cancellation_persists_terminal_quality_record(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_MODEL_HEAVY", "fixture-model")

    def cancel_prompt_setup(*_args, **_kwargs):
        raise asyncio.CancelledError("fallback setup cancelled")

    monkeypatch.setattr(fallback, "get_prompt_builder", cancel_prompt_setup)

    with pytest.raises(asyncio.CancelledError):
        await fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path / "fallback",
            run_id="fallback-setup-cancelled",
            model="fixture-model",
        )

    record = read_quality_record(
        tmp_path / "fallback",
        "600009.SH",
        "fallback-setup-cancelled",
    )
    assert record is not None
    assert record.status == "incomplete"


@pytest.mark.anyio
async def test_fallback_cancellation_persists_terminal_quality_record(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_MODEL_HEAVY", "fixture-model")

    async def cancel_call(*_args, **_kwargs):
        raise asyncio.CancelledError("fallback cancelled")

    monkeypatch.setattr(fallback, "call_llm", cancel_call)

    with pytest.raises(asyncio.CancelledError, match="fallback cancelled"):
        await fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path / "fallback",
            run_id="fallback-cancelled",
            model="fixture-model",
        )

    record = read_quality_record(
        tmp_path / "fallback",
        "600009.SH",
        "fallback-cancelled",
    )
    assert record is not None
    assert record.status == "incomplete"
    manifest = json.loads(
        (
            tmp_path / "fallback" / "fallback-cancelled" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["state"] == "incomplete"
    assert manifest["run_quality_status"] == "incomplete"


@pytest.mark.anyio
async def test_fallback_audit_prompt_failure_persists_terminal_quality_record(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_MODEL_HEAVY", "fixture-model")
    original_write = fallback.AuditChainWriter.write

    def fail_prompt_write(self, kind, payload):
        if kind == "prompt":
            raise OSError("audit prompt write failed")
        return original_write(self, kind, payload)

    monkeypatch.setattr(fallback.AuditChainWriter, "write", fail_prompt_write)

    with pytest.raises(OSError, match="audit prompt write failed"):
        await fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path / "fallback",
            audit_root=tmp_path / "audit",
            run_id="fallback-audit-setup-failure",
            model="fixture-model",
        )

    record = read_quality_record(
        tmp_path / "fallback",
        "600009.SH",
        "fallback-audit-setup-failure",
    )
    assert record is not None
    assert record.status == "failed"
    manifest = json.loads(
        (
            tmp_path
            / "fallback"
            / "fallback-audit-setup-failure"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["state"] == "failed"
    assert manifest["run_quality_status"] == "failed"


@pytest.mark.anyio
async def test_fallback_audit_publish_failure_persists_terminal_quality_record(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LLM_MODEL_HEAVY", "fixture-model")

    async def fake_call(*_args, **_kwargs):
        return (_agent_json("buffett", "neutral"), {})

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(
        fallback,
        "_promote_staged_fallback_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("fallback publish failed")
        ),
    )

    with pytest.raises(OSError, match="fallback publish failed"):
        await fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path / "fallback",
            audit_root=tmp_path / "audit",
            run_id="fallback-publish-failed",
            model="fixture-model",
        )

    record = read_quality_record(
        tmp_path / "fallback",
        "600009.SH",
        "fallback-publish-failed",
    )
    assert record is not None
    assert record.status == "incomplete"
    manifest = json.loads(
        (
            tmp_path / "fallback" / "fallback-publish-failed" / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["state"] == "incomplete"
    assert manifest["run_quality_status"] == "incomplete"
