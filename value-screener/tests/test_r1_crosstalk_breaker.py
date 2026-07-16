"""f3c-r1-crosstalk-root-cause: R1 质量门主流程断路器测试.

task 3.1：显性环形引用 hard fail 阻断产出（不进 R2，不写"成功"JSON）+
         无环形真实产出通过断路器进入分流。
task 3.2：凭空数字 + 隐性串台 soft warning 不阻断（仍产出）+ 运行时降级下
         显性环形仍 hard fail（降级豁免 R3 跳过不豁免串台铁证）。

LLM 调用全部 mock，不花 token。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from council.debate import run_debate
from council.schema import AgentOutput, SynthesizerOutput


# ── 共用 mock 数据 ──────────────────────────────────────────────

LLM_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def _agent_json(name: str, core_thesis: str, key_metrics: list[str] | None = None) -> str:
    """构造单个 agent 的 R1 LLM 响应 JSON."""
    return json.dumps({
        "signal": "bullish",
        "conviction": 75,
        "core_thesis": core_thesis,
        "key_metrics": key_metrics or [],
        "risks": ["估值偏高"],
        "what_would_change_my_mind": "业绩下滑",
        "out_of_circle": False,
        "historical_parallel": None,
    }, ensure_ascii=False)


def _mk_synth() -> SynthesizerOutput:
    """构造一个通过结构校验的 SynthesizerOutput（R4 用，非本测试重点）."""
    return SynthesizerOutput.from_dict({
        "final_signal": "neutral",
        "conviction": 50,
        "consensus_summary": "多数中性",
        "dissent_points": ["冯柳逆向"],
        "pending_verification": ["国际客流恢复"],
        "key_variables": [{"name": "免税收入", "value": "待跟踪", "why_it_matters": "核心增长"}],
    })


def _full_dossier_with_core() -> dict:
    """构造含 core_snapshot 的分层 dossier（verify_r1_feature_grounding 需递归取数）.

    core_snapshot 含 roe_3y=30.0 → "ROE 30%" 有来源，不误判凭空。
    """
    return {
        "core_snapshot": {"pe_ttm": 26.42, "roe_3y": [28.0, 29.0, 30.0], "net_margin": 15.86},
        "research_dossier": {
            "main_business": {"main_products": []},
            "degraded_fields": [],
        },
    }


# ── task 3.1：显性环形 hard fail 阻断 ───────────────────────────

class TestR1CrosstalkBreakerHardFail:
    """显性环形引用命中 → run_debate 在 R1 后 hard fail 阻断。"""

    @pytest.mark.anyio
    async def test_circular_reference_blocks_before_r2(self, tmp_path, monkeypatch):
        """R1 含显性环形（buffett core_thesis 写'munger 看好'）→ 阻断，不进 R2/R3/R4."""
        monkeypatch.chdir(tmp_path)

        # R1 响应：buffett→"munger 看好长期价值"（环形），其余 agent 正常
        r1_responses = iter([
            (_agent_json("buffett", "munger 看好长期价值", ["ROE 30%"]), LLM_USAGE),
            (_agent_json("munger", "长期价值可靠", ["ROE 30%"]), LLM_USAGE),
        ])

        async def fake_call_llm(system_prompt, user_message, reasoning_level="heavy"):
            return next(r1_responses)

        with patch("council.debate.build_research_dossier", return_value=_full_dossier_with_core()), \
             patch("council.debate.call_llm", side_effect=fake_call_llm), \
             patch("council.debate._call_da", new_callable=AsyncMock, return_value=AgentOutput.from_dict("da", {"signal": "neutral", "conviction": 0, "core_thesis": "无盲点", "key_metrics": [], "risks": [], "what_would_change_my_mind": "无", "out_of_circle": False, "historical_parallel": None, "extra": {"blind_spots": [{"title": "t", "detail": "d", "which_agents_missed_it": ["buffett"]}], "evidence_quality_assessment": {"buffett": "accurate"}, "recommendation": "defer_to_buffett_consensus"}})) as mock_da, \
             patch("council.debate._call_synthesizer", new_callable=AsyncMock, return_value=_mk_synth()) as mock_synth:
            # 显性环形应 hard fail：抛 ValueError（与 insufficient_data 同模式）
            with pytest.raises(ValueError, match="circular_reference|环形引用|crosstalk"):
                await run_debate("600519", agents=["buffett", "munger"])

        # 阻断发生在 R1 后：DA / Synthesizer 不应被调用
        mock_da.assert_not_called()
        mock_synth.assert_not_called()

    @pytest.mark.anyio
    async def test_no_circular_passes_into_divergence(self, tmp_path, monkeypatch):
        """无环形真实产出 → 通过断路器进入分流（R2/R3/R4 正常编排）."""
        monkeypatch.chdir(tmp_path)

        r1_responses = iter([
            (_agent_json("buffett", "品牌护城河深厚", ["ROE 30%"]), LLM_USAGE),
            (_agent_json("munger", "估值偏贵但生意好", ["ROE 30%"]), LLM_USAGE),
        ])

        async def fake_call_llm(system_prompt, user_message, reasoning_level="heavy"):
            return next(r1_responses)

        with patch("council.debate.build_research_dossier", return_value=_full_dossier_with_core()), \
             patch("council.debate.call_llm", side_effect=fake_call_llm), \
             patch("council.debate._call_da", new_callable=AsyncMock, return_value=AgentOutput.from_dict("da", {"signal": "neutral", "conviction": 0, "core_thesis": "无盲点", "key_metrics": [], "risks": [], "what_would_change_my_mind": "无", "out_of_circle": False, "historical_parallel": None, "extra": {"blind_spots": [{"title": "t", "detail": "d", "which_agents_missed_it": ["buffett"]}], "evidence_quality_assessment": {"buffett": "accurate"}, "recommendation": "defer_to_buffett_consensus"}})), \
             patch("council.debate._call_synthesizer", new_callable=AsyncMock, return_value=_mk_synth()):
            result = await run_debate("600519", agents=["buffett", "munger"])

        # 通过断路器：R1 完整、进了后续轮次
        assert len(result.round1) == 2
        # 不抛错即代表通过断路器


# ── task 3.2：凭空数字/隐性 soft 不阻断 + 降级下仍拦显性 ────────

class TestR1BreakerSoftAndDegraded:
    """凭空数字 + 隐性串台 → soft warning 不阻断；降级下显性环形仍 hard fail。"""

    @pytest.mark.anyio
    async def test_fabricated_number_soft_warning_not_blocked(self, tmp_path, monkeypatch):
        """R1 key_metrics 含凭空数字（features 无对应）→ soft warning，不阻断产出."""
        monkeypatch.chdir(tmp_path)

        # ROE 50% 凭空（dossier core roe_3y=[28,29,30]，无 50）
        r1_responses = iter([
            (_agent_json("buffett", "护城河好", ["ROE 50%"]), LLM_USAGE),
            (_agent_json("munger", "生意不错", ["ROE 50%"]), LLM_USAGE),
        ])

        async def fake_call_llm(system_prompt, user_message, reasoning_level="heavy"):
            return next(r1_responses)

        with patch("council.debate.build_research_dossier", return_value=_full_dossier_with_core()), \
             patch("council.debate.call_llm", side_effect=fake_call_llm), \
             patch("council.debate._call_da", new_callable=AsyncMock, return_value=AgentOutput.from_dict("da", {"signal": "neutral", "conviction": 0, "core_thesis": "无", "key_metrics": [], "risks": [], "what_would_change_my_mind": "无", "out_of_circle": False, "historical_parallel": None, "extra": {"blind_spots": [{"title": "t", "detail": "d", "which_agents_missed_it": ["buffett"]}], "evidence_quality_assessment": {"buffett": "moderate"}, "recommendation": "no_clear_winner"}})), \
             patch("council.debate._call_synthesizer", new_callable=AsyncMock, return_value=_mk_synth()):
            # 凭空数字 soft 不阻断：run_debate 应正常返回，不抛错
            result = await run_debate("600519", agents=["buffett", "munger"])

        assert len(result.round1) == 2  # 仍产出，未阻断

    @pytest.mark.anyio
    async def test_implicit_crosstalk_soft_not_blocked(self, tmp_path, monkeypatch):
        """隐性串台（不点名，写'另一位价值投资者看好'）→ soft warning，不阻断.

        detect_circular_reference 是字符串子串匹配，'另一位价值投资者'不含 agent_id
        字面 → 不命中 hard fail → soft warning 不阻断（f3c §D3 逃逸面，本 change 不拦）。
        """
        monkeypatch.chdir(tmp_path)

        r1_responses = iter([
            (_agent_json("buffett", "另一位价值投资者也看好长期价值", ["ROE 30%"]), LLM_USAGE),
            (_agent_json("munger", "价值投资派达成共识", ["ROE 30%"]), LLM_USAGE),
        ])

        async def fake_call_llm(system_prompt, user_message, reasoning_level="heavy"):
            return next(r1_responses)

        with patch("council.debate.build_research_dossier", return_value=_full_dossier_with_core()), \
             patch("council.debate.call_llm", side_effect=fake_call_llm), \
             patch("council.debate._call_da", new_callable=AsyncMock, return_value=AgentOutput.from_dict("da", {"signal": "neutral", "conviction": 0, "core_thesis": "无", "key_metrics": [], "risks": [], "what_would_change_my_mind": "无", "out_of_circle": False, "historical_parallel": None, "extra": {"blind_spots": [{"title": "t", "detail": "d", "which_agents_missed_it": ["buffett"]}], "evidence_quality_assessment": {"buffett": "accurate"}, "recommendation": "defer_to_buffett_consensus"}})), \
             patch("council.debate._call_synthesizer", new_callable=AsyncMock, return_value=_mk_synth()):
            result = await run_debate("600519", agents=["buffett", "munger"])

        assert len(result.round1) == 2  # 隐性串台不直呼 agent_id → 不 hard fail

    @pytest.mark.anyio
    async def test_circular_still_blocks_under_runtime_degradation(self, tmp_path, monkeypatch):
        """运行时降级（R1 部分失败 error_rate≥0.4）下，幸存 agent 显性环形仍 hard fail.

        降级豁免 R3 DA 跳过，不豁免串台铁证。用可控 call_agent mock：
        4 agent 中 2 个抛 RuntimeError（→ r1_errors），2 个成功，其中 buffett
        core_thesis="munger 看好"（显性环形）。error_rate=0.5≥0.4 触发降级，
        但断路器在降级判断之前对幸存 round1 拦环形 → hard fail。
        """
        monkeypatch.chdir(tmp_path)

        # 用 call_agent mock 直接造 R1 结果，避开真假混合的脆弱性
        async def fake_call_agent(agent_id, ticker, features, *, other_opinions=None,
                                   reasoning_level="heavy", usage_accumulator=None):
            if agent_id == "buffett":
                return AgentOutput.from_dict("buffett", {
                    "signal": "bullish", "conviction": 75,
                    "core_thesis": "munger 看好长期价值",  # 显性环形
                    "key_metrics": ["ROE 30%"], "risks": ["估值偏高"],
                    "what_would_change_my_mind": "业绩下滑",
                    "out_of_circle": False, "historical_parallel": None,
                })
            if agent_id == "munger":
                return AgentOutput.from_dict("munger", {
                    "signal": "bullish", "conviction": 75,
                    "core_thesis": "长期价值可靠",
                    "key_metrics": ["ROE 30%"], "risks": ["估值偏高"],
                    "what_would_change_my_mind": "业绩下滑",
                    "out_of_circle": False, "historical_parallel": None,
                })
            # duan / feng_liu 失败 → r1_errors，制造 error_rate=0.5
            raise RuntimeError(f"模拟 {agent_id} 失败")

        with patch("council.debate.build_research_dossier", return_value=_full_dossier_with_core()), \
             patch("council.debate.call_agent", side_effect=fake_call_agent):
            # 降级下显性环形仍 hard fail（断路器在降级判断之前）
            with pytest.raises(ValueError, match="circular_reference|环形引用|crosstalk"):
                await run_debate("600519", agents=["buffett", "munger", "duan", "feng_liu"])
