"""f2 CR P1#2: verify_quality_gate CLI 函数返回值语义测试.

verify_divergence_report / verify_da_fact_check 是机器可判定的 hard gate，
失败时 verify_quality_gate() SHALL 返回 False（非无条件 return True）。
人工检查项（R1 同质化、R2 修订、DA 盲点覆盖）保持 WARNING 不阻断。
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from council.schema import AgentOutput, CouncilResult, SynthesizerOutput
from council.verify_quality_gate import verify_quality_gate


VALID_AGENT_DATA = {
    "signal": "bullish", "conviction": 80, "core_thesis": "好公司",
    "key_metrics": [], "risks": [], "what_would_change_my_mind": "业绩下滑",
    "out_of_circle": False, "historical_parallel": None,
}


def _make_result(
    r4_divergence_level: str | None = "medium",
    r4_key_disagreements: list[dict] | None = None,
    r3: AgentOutput | None = None,
    da_skipped_reason: str | None = None,
) -> CouncilResult:
    """构造 CouncilResult，r4 的 divergence 字段可控."""
    syn = SynthesizerOutput(
        final_signal="bullish", conviction=70, consensus_summary="看好",
        divergence_level=r4_divergence_level,
        key_disagreements=r4_key_disagreements if r4_key_disagreements is not None else [{"topic": "估值"}],
    )
    agent = AgentOutput.from_dict("buffett", VALID_AGENT_DATA)
    return CouncilResult(
        ticker="600519.SH",
        round1=[agent],
        round2=[agent],
        round3=r3,
        round4=syn,
        final_verdict="bullish",
        key_variables=["x"],
        consensus_summary="看好",
        da_skipped_reason=da_skipped_reason,
    )


class TestVerifyQualityGateHardFail:
    @pytest.mark.anyio
    async def test_missing_divergence_level_returns_false(self, tmp_path, monkeypatch):
        """R4 缺 divergence_level → verify_divergence_report hard fail → return False."""
        monkeypatch.chdir(tmp_path)
        result = _make_result(r4_divergence_level=None)
        with patch("council.verify_quality_gate.assemble_council_features", return_value={"name": "t"}), \
             patch("council.verify_quality_gate.run_debate", new_callable=AsyncMock, return_value=result):
            ok = await verify_quality_gate("600519.SH")
        assert ok is False  # hard fail，非 True

    @pytest.mark.anyio
    async def test_high_divergence_missing_key_disagreements_returns_false(self, tmp_path, monkeypatch):
        """divergence_level=high 但 key_disagreements 空 → hard fail → return False."""
        monkeypatch.chdir(tmp_path)
        result = _make_result(r4_divergence_level="high", r4_key_disagreements=[])
        with patch("council.verify_quality_gate.assemble_council_features", return_value={"name": "t"}), \
             patch("council.verify_quality_gate.run_debate", new_callable=AsyncMock, return_value=result):
            ok = await verify_quality_gate("600519.SH")
        assert ok is False

    @pytest.mark.anyio
    async def test_da_ran_missing_evidence_quality_returns_false(self, tmp_path, monkeypatch):
        """DA ran 但缺 evidence_quality_assessment → verify_da_fact_check hard fail → return False."""
        monkeypatch.chdir(tmp_path)
        # DA 没 evidence_quality_assessment
        da = AgentOutput(name="da", signal="neutral", conviction=0, core_thesis="盲点",
                        what_would_change_my_mind="x", out_of_circle=False, extra={})
        result = _make_result(r3=da, da_skipped_reason=None)
        with patch("council.verify_quality_gate.assemble_council_features", return_value={"name": "t"}), \
             patch("council.verify_quality_gate.run_debate", new_callable=AsyncMock, return_value=result):
            ok = await verify_quality_gate("600519.SH")
        assert ok is False

    @pytest.mark.anyio
    async def test_all_pass_returns_true(self, tmp_path, monkeypatch):
        """全部门通过 → return True（含 DA ran + 完整分歧报告）."""
        monkeypatch.chdir(tmp_path)
        da = AgentOutput(
            name="da", signal="neutral", conviction=0, core_thesis="盲点",
            what_would_change_my_mind="x", out_of_circle=False,
            extra={"evidence_quality_assessment": {"buffett": "accurate"},
                   "recommendation": "no_clear_winner",
                   "blind_spots": [{"title": "t", "detail": "d", "which_agents_missed_it": ["buffett"]}]},
        )
        result = _make_result(r3=da, da_skipped_reason=None)
        with patch("council.verify_quality_gate.assemble_council_features", return_value={"name": "t"}), \
             patch("council.verify_quality_gate.run_debate", new_callable=AsyncMock, return_value=result):
            ok = await verify_quality_gate("600519.SH")
        assert ok is True
