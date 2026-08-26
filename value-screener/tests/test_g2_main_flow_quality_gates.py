"""G2 4.1：Council 正常主流程质量门接入的 RED/GREEN 行为测试."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from council.debate import run_debate
from council.schema import AgentOutput, SynthesizerOutput


USAGE = {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}


def _dossier() -> dict:
    return {
        "core_snapshot": {
            "ticker": "600519",
            "name": "贵州茅台",
            "market_cap": 2_000_000_000_000,
            "pe_ttm": 26.42,
            "roe_3y": [28.0, 29.0, 30.0],
            "net_margin": 15.86,
        },
        "research_dossier": {
            "main_business": {
                "code": "600519",
                "main_business_text": "高端白酒销售",
            },
            "degraded_fields": [],
        },
    }


def _agent(name: str, *, signal: str = "bullish", new_evidence: list[str] | None = None) -> AgentOutput:
    return AgentOutput(
        name=name,
        signal=signal,
        conviction=70,
        core_thesis=f"{name} thesis",
        key_metrics=["ROE 30%"],
        risks=["估值风险"],
        what_would_change_my_mind="盈利恶化",
        out_of_circle=False,
        new_evidence=new_evidence or [],
    )


def _synth(*, divergence_level: str = "high") -> SynthesizerOutput:
    return SynthesizerOutput(
        final_signal="neutral",
        conviction=50,
        consensus_summary="保留分歧",
        dissent_points=[{"topic": "估值"}],
        pending_verification=["盈利"],
        divergence_level=divergence_level,
        key_disagreements=[{"topic": "估值"}] if divergence_level in {"high", "extreme"} else [],
        calibration_status="uncalibrated",
    )


@pytest.mark.anyio
async def test_normal_council_invokes_all_quality_gates_with_stage_shapes(tmp_path, monkeypatch):
    """R1/R2/DA/R4 gate 均由正常编排调用，且传入真实阶段对象/上下文."""
    monkeypatch.chdir(tmp_path)
    agents = ["buffett", "munger", "duan", "feng_liu"]
    r1 = [_agent("buffett"), _agent("munger"), _agent("duan", signal="bearish"), _agent("feng_liu", signal="neutral")]
    r2 = [_agent(name, new_evidence=["ROE 30%"]) for name in agents]
    calls: list[tuple] = []

    async def fake_call_agent(agent_id, ticker, features, other_opinions=None,
                              reasoning_level="heavy", **kwargs):
        calls.append(("agent", agent_id, ticker, features, other_opinions, reasoning_level, kwargs))
        return (r1 if reasoning_level == "heavy" and not other_opinions else r2)[agents.index(agent_id)]

    async def fake_da(round1, round2, ticker, features, **kwargs):
        calls.append(("da", round1, round2, ticker, features, kwargs))
        return _agent("da")

    async def fake_synth(round1, round2, da_result, ticker, features, **kwargs):
        calls.append(("synth", round1, round2, da_result, ticker, features, kwargs))
        return _synth()

    def r1_gate(output, features):
        calls.append(("r1_gate", output, features))
        return True, []

    def r2_gate(output, features):
        calls.append(("r2_gate", output, features))
        return True, []

    def da_gate(output, agent_ids=None, da_skipped_reason=None):
        calls.append(("da_gate", output, agent_ids, da_skipped_reason))
        return True, []

    def r4_gate(output):
        calls.append(("r4_gate", output))
        return True, []

    with patch("council.debate.call_agent", side_effect=fake_call_agent), \
         patch("council.debate._call_da", side_effect=fake_da), \
         patch("council.debate._call_synthesizer", side_effect=fake_synth), \
         patch("council.verify_quality_gate.verify_r1_feature_grounding", side_effect=r1_gate), \
         patch("council.verify_quality_gate.verify_r2_new_evidence", side_effect=r2_gate), \
         patch("council.verify_quality_gate.verify_da_fact_check", side_effect=da_gate), \
         patch("council.verify_quality_gate.verify_divergence_report", side_effect=r4_gate):
        result = await run_debate("600519", features=_dossier(), agents=agents)

    assert result.run_quality_status == "complete"
    assert result.success_cache_eligible is True
    assert [item[0] for item in calls if item[0].endswith("_gate")] == [
        "r1_gate", "r1_gate", "r1_gate", "r1_gate",
        "r2_gate", "r2_gate", "r2_gate", "r2_gate",
        "da_gate", "r4_gate",
    ]
    da_call = next(item for item in calls if item[0] == "da_gate")
    assert da_call[1].name == "da"
    assert da_call[2] == tuple(agents)
    assert da_call[3] is None
    agent_calls = [item for item in calls if item[0] == "agent"]
    assert len(agent_calls) == 8
    assert all(item[2] == "600519.SH" for item in agent_calls)
    assert all(item[3] == _dossier() for item in agent_calls)
    assert all(item[5] == "heavy" for item in agent_calls)
    assert all("usage_accumulator" in item[6] for item in agent_calls)
    assert all(item[4] is None for item in agent_calls[:4])
    assert all(len(item[4]) == 3 for item in agent_calls[4:])
    raw_da_call = next(item for item in calls if item[0] == "da")
    assert raw_da_call[3] == "600519.SH"
    assert raw_da_call[4] == _dossier()
    assert "usage_accumulator" in raw_da_call[5]
    raw_synth_call = next(item for item in calls if item[0] == "synth")
    assert raw_synth_call[4] == "600519.SH"
    assert raw_synth_call[5] == _dossier()
    assert raw_synth_call[6]["da_skipped_reason"] is None
    assert "usage_accumulator" in raw_synth_call[6]


@pytest.mark.anyio
async def test_r2_warning_propagates_and_blocks_clean_success(tmp_path, monkeypatch):
    """R2 soft warning 不阻断方向性结果，但必须使终态 warning 且不可 cache."""
    monkeypatch.chdir(tmp_path)
    agents = ["buffett", "munger", "duan", "feng_liu"]
    r1 = [_agent("buffett"), _agent("munger"), _agent("duan", signal="bearish"), _agent("feng_liu", signal="neutral")]
    r2 = [_agent(name) for name in agents]

    async def fake_call_agent(agent_id, ticker, features, other_opinions=None,
                              reasoning_level="heavy", **kwargs):
        return (r1 if not other_opinions else r2)[agents.index(agent_id)]

    async def fake_da(*args, **kwargs):
        return _agent("da")

    async def fake_synth(*args, **kwargs):
        return _synth()

    with patch("council.debate.call_agent", side_effect=fake_call_agent), \
         patch("council.debate._call_da", side_effect=fake_da), \
         patch("council.debate._call_synthesizer", side_effect=fake_synth), \
         patch("council.verify_quality_gate.verify_r1_feature_grounding", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_r2_new_evidence", return_value=(True, ["soft: r2_no_new_evidence"])), \
         patch("council.verify_quality_gate.verify_da_fact_check", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_divergence_report", return_value=(True, [])):
        result = await run_debate("600519", features=_dossier(), agents=agents)

    assert result.run_quality_status == "warning"
    assert result.final_quality_gate == "warning"
    assert result.success_cache_eligible is False
    assert any("r2_no_new_evidence" in reason for reason in result.run_quality_reasons)


@pytest.mark.anyio
async def test_invalid_r4_quality_report_fails_before_watchlist_publish(tmp_path, monkeypatch):
    """R4 结构污染必须失败，不能靠方向性 verdict 写出 clean watchlist."""
    monkeypatch.chdir(tmp_path)
    agents = ["buffett", "munger", "duan", "feng_liu"]
    r1 = [_agent("buffett"), _agent("munger"), _agent("duan", signal="bearish"), _agent("feng_liu", signal="neutral")]
    r2 = [_agent(name, new_evidence=["ROE 30%"]) for name in agents]

    async def fake_call_agent(agent_id, ticker, features, other_opinions=None,
                              reasoning_level="heavy", **kwargs):
        return (r1 if not other_opinions else r2)[agents.index(agent_id)]

    with patch("council.debate.call_agent", side_effect=fake_call_agent), \
         patch("council.debate._call_da", new_callable=AsyncMock, return_value=_agent("da")), \
         patch("council.debate._call_synthesizer", new_callable=AsyncMock, return_value=_synth()), \
         patch("council.verify_quality_gate.verify_r1_feature_grounding", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_r2_new_evidence", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_da_fact_check", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_divergence_report", return_value=(False, ["divergence_level missing"])):
        with pytest.raises(ValueError, match="quality|divergence"):
            await run_debate("600519", features=_dossier(), agents=agents)

    assert not list((tmp_path / "watchlist").rglob("*.json"))


@pytest.mark.anyio
async def test_invalid_da_fact_check_fails_before_synthesizer(tmp_path, monkeypatch):
    """DA hard failure 必须在 R4 前断路，保留 failed record."""
    monkeypatch.chdir(tmp_path)
    agents = ["buffett", "munger", "duan", "feng_liu"]
    r1 = [_agent("buffett"), _agent("munger"), _agent("duan", signal="bearish"), _agent("feng_liu", signal="neutral")]
    r2 = [_agent(name, new_evidence=["ROE 30%"]) for name in agents]

    async def fake_call_agent(agent_id, ticker, features, other_opinions=None,
                              reasoning_level="heavy", **kwargs):
        return (r1 if not other_opinions else r2)[agents.index(agent_id)]

    synth = AsyncMock(return_value=_synth())
    with patch("council.debate.call_agent", side_effect=fake_call_agent), \
         patch("council.debate._call_da", new_callable=AsyncMock, return_value=_agent("da")), \
         patch("council.debate._call_synthesizer", synth), \
         patch("council.verify_quality_gate.verify_r1_feature_grounding", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_r2_new_evidence", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_da_fact_check", return_value=(False, ["missing evidence_quality_assessment"])):
        with pytest.raises(ValueError, match="quality_gate_failed: da"):
            await run_debate("600519", features=_dossier(), agents=agents)

    synth.assert_not_awaited()
    record_paths = list((tmp_path / "quality_status" / "600519.SH").glob("*/record.json"))
    assert len(record_paths) == 1
    payload = json.loads(record_paths[0].read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["final_quality_gate"] == "failed"
    assert payload["reasons"][0] == "da"


@pytest.mark.anyio
async def test_evidence_exhausted_skip_keeps_da_warning_and_blocks_cache(tmp_path, monkeypatch):
    """evidence_exhausted 跳 DA 时仍消费 skip gate，信息缺口必须可见."""
    monkeypatch.chdir(tmp_path)
    agents = ["buffett", "munger", "duan", "feng_liu"]
    r1 = [_agent("buffett"), _agent("munger"), _agent("duan", signal="bearish"), _agent("feng_liu", signal="neutral")]
    r2 = [_agent(name, new_evidence=[]) for name in agents]
    for output in r2[:3]:
        output.evidence_exhausted = True

    async def fake_call_agent(agent_id, ticker, features, other_opinions=None,
                              reasoning_level="heavy", **kwargs):
        return (r1 if not other_opinions else r2)[agents.index(agent_id)]

    def da_gate(output, agent_ids=None, da_skipped_reason=None):
        assert output is None
        assert agent_ids == tuple(agents)
        assert da_skipped_reason == "evidence_exhausted"
        return True, ["soft: da_skipped — evidence not fact-checked"]

    with patch("council.debate.call_agent", side_effect=fake_call_agent), \
         patch("council.debate._call_da", new_callable=AsyncMock) as da_mock, \
         patch("council.debate._call_synthesizer", new_callable=AsyncMock, return_value=_synth()), \
         patch("council.verify_quality_gate.verify_r1_feature_grounding", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_r2_new_evidence", return_value=(True, [])), \
         patch("council.verify_quality_gate.verify_da_fact_check", side_effect=da_gate), \
         patch("council.verify_quality_gate.verify_divergence_report", return_value=(True, [])):
        result = await run_debate("600519", features=_dossier(), agents=agents)

    da_mock.assert_not_awaited()
    assert result.da_skipped_reason == "evidence_exhausted"
    assert result.run_quality_status == "da_skipped"
    assert result.success_cache_eligible is False
    assert any("not fact-checked" in reason for reason in result.run_quality_reasons)


@pytest.mark.anyio
async def test_call_agent_mock_contract_includes_model_keyword_shape(monkeypatch):
    """外部 LLM mock 同时约束 positional/keyword 参数形状，避免静默签名漂移."""
    expected = _agent("buffett")
    observed = {}

    async def fake_llm(system_prompt, user_message, reasoning_level, *, model):
        observed.update({
            "system_prompt": system_prompt,
            "user_message": user_message,
            "reasoning_level": reasoning_level,
            "model": model,
        })
        return expected.to_json(), USAGE

    with patch("council.debate.call_llm", side_effect=fake_llm), \
         patch("council.debate.get_prompt_builder", return_value=lambda: "system"):
        from council.debate import call_agent

        result = await call_agent(
            "buffett",
            "600519.SH",
            _dossier(),
            other_opinions=None,
            reasoning_level="heavy",
            model="heavy-test-model",
        )

    assert result.name == "buffett"
    assert observed["reasoning_level"] == "heavy"
    assert observed["model"] == "heavy-test-model"
    assert "600519.SH" in observed["user_message"]
