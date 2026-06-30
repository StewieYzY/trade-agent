"""L3 council 校准测试.

覆盖 calibrate.py 的 run_calibration 逻辑，验证校准用例执行。
包括投资大师校准（巴菲特、段永平）和 DA/Synthesizer schema 验证。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from council.calibrate import (
    CALIBRATION_CASES,
    run_agent_calibration,
    run_da_calibration,
    run_synthesizer_calibration,
    run_calibration,
)
from council.schema import AgentOutput, SynthesizerOutput


@pytest.fixture
def mock_features():
    """Mock 特征数据."""
    return {
        "name": "贵州茅台",
        "pe_ttm": 30.5,
        "pb": 8.2,
        "roe_5y_avg": 32.1,
    }


@pytest.fixture
def mock_agent_output():
    """Mock AgentOutput."""
    return AgentOutput(
        name="buffett",
        signal="bullish",
        conviction=85,
        core_thesis="品牌护城河深厚",
        key_metrics=["ROE 32%", "毛利率 90%+"],
        risks=["估值偏高"],
        what_would_change_my_mind="市场份额大幅下降",
        out_of_circle=False,
        historical_parallel="可口可乐",
        extra={},
    )


@pytest.fixture
def mock_da_output():
    """Mock DA AgentOutput."""
    return AgentOutput(
        name="da",
        signal="neutral",
        conviction=0,
        core_thesis="发现关键盲点",
        key_metrics=[],
        risks=[],
        what_would_change_my_mind="N/A",
        out_of_circle=False,
        historical_parallel=None,
        extra={
            "blind_spots": [
                {
                    "title": "市场集中度风险",
                    "detail": "白酒行业CR5已达60%，增长空间有限",
                    "which_agents_missed_it": ["buffett", "munger"],
                }
            ]
        },
    )


@pytest.fixture
def mock_synthesizer_output():
    """Mock SynthesizerOutput."""
    return SynthesizerOutput(
        final_signal="bullish",
        conviction=75,
        consensus_summary="多数看好长期价值，但估值需谨慎",
        dissent_points=[
            {
                "topic": "估值合理性",
                "who_disagrees": "munger",
                "their_reason": "PE 30x 偏高，安全边际不足",
            }
        ],
        pending_verification=["市场份额变化趋势", "新品类拓展情况"],
    )


class TestCalibrationCases:
    """校准用例定义验证."""

    def test_cases_defined(self):
        """至少有 2 个校准用例."""
        assert len(CALIBRATION_CASES) >= 2

    def test_bullish_case(self):
        """看多案例定义正确."""
        bullish = next(c for c in CALIBRATION_CASES if c["expected_signal"] == "bullish")
        assert "ticker" in bullish
        assert bullish["ticker"] == "600519.SH"

    def test_bearish_case(self):
        """看空案例定义正确（assert_op=ne）."""
        ne_cases = [c for c in CALIBRATION_CASES if c.get("assert_op") == "ne"]
        assert len(ne_cases) == 1
        assert ne_cases[0]["ticker"] == "600900.SH"
        assert ne_cases[0]["expected_signal"] == "bullish"  # 期望不等于 bullish

    def test_duan_case_defined(self):
        """段永平校准用例已定义."""
        duan_case = next((c for c in CALIBRATION_CASES if c.get("agent_id") == "duan"), None)
        assert duan_case is not None
        assert duan_case["ticker"] == "600519.SH"
        assert duan_case["expected_signal"] == "bullish"


class TestAgentCalibration:
    """投资大师校准测试."""

    @pytest.mark.anyio
    async def test_duan_calibration_passes(self, mock_features, mock_agent_output):
        """段永平校准通过：signal == 'bullish'."""
        case = next(c for c in CALIBRATION_CASES if c.get("agent_id") == "duan")

        with patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps(mock_agent_output.to_dict(), ensure_ascii=False)
            passed = await run_agent_calibration(case)

        assert passed is True

    @pytest.mark.anyio
    async def test_duan_calibration_fails_on_wrong_signal(self, mock_features):
        """段永平校准失败：signal != 'bullish'."""
        case = next(c for c in CALIBRATION_CASES if c.get("agent_id") == "duan")

        bearish_output = AgentOutput(
            name="duan",
            signal="bearish",
            conviction=60,
            core_thesis="不看好",
            key_metrics=[],
            risks=[],
            what_would_change_my_mind="N/A",
            out_of_circle=False,
            historical_parallel=None,
            extra={},
        )

        with patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps(bearish_output.to_dict(), ensure_ascii=False)
            passed = await run_agent_calibration(case)

        assert passed is False


class TestDACalibration:
    """DA 校准测试."""

    @pytest.mark.anyio
    async def test_da_calibration_passes(
        self, mock_features, mock_agent_output, mock_da_output
    ):
        """DA 校准通过：schema 合法 + blind_spots 非空."""
        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            # Mock run_debate 返回 R1，然后 _call_da 返回 DA
            mock_llm.side_effect = [
                json.dumps(mock_agent_output.to_dict(), ensure_ascii=False),  # R1
                json.dumps(mock_da_output.to_dict(), ensure_ascii=False),     # DA
            ]

            passed = await run_da_calibration()

        assert passed is True

    @pytest.mark.anyio
    async def test_da_calibration_fails_on_invalid_signal(
        self, mock_features, mock_agent_output
    ):
        """DA 校准失败：signal != 'neutral'."""
        invalid_da_output = AgentOutput(
            name="da",
            signal="bullish",  # 错误
            conviction=0,
            core_thesis="test",
            key_metrics=[],
            risks=[],
            what_would_change_my_mind="N/A",
            out_of_circle=False,
            historical_parallel=None,
            extra={"blind_spots": [{"title": "t", "detail": "d", "which_agents_missed_it": ["a"]}]},
        )

        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                json.dumps(mock_agent_output.to_dict(), ensure_ascii=False),
                json.dumps(invalid_da_output.to_dict(), ensure_ascii=False),
            ]

            passed = await run_da_calibration()

        assert passed is False

    @pytest.mark.anyio
    async def test_da_calibration_fails_on_empty_blind_spots(
        self, mock_features, mock_agent_output
    ):
        """DA 校准失败：blind_spots 为空."""
        empty_blind_spots = AgentOutput(
            name="da",
            signal="neutral",
            conviction=0,
            core_thesis="test",
            key_metrics=[],
            risks=[],
            what_would_change_my_mind="N/A",
            out_of_circle=False,
            historical_parallel=None,
            extra={"blind_spots": []},  # 空列表
        )

        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                json.dumps(mock_agent_output.to_dict(), ensure_ascii=False),
                json.dumps(empty_blind_spots.to_dict(), ensure_ascii=False),
            ]

            passed = await run_da_calibration()

        assert passed is False


class TestSynthesizerCalibration:
    """Synthesizer 校准测试."""

    @pytest.mark.anyio
    async def test_synthesizer_calibration_passes(
        self, mock_features, mock_agent_output, mock_da_output, mock_synthesizer_output
    ):
        """Synthesizer 校准通过：schema 合法 + dissent_points 存在."""
        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            # Mock LLM 返回序列：R1, DA, Synthesizer
            mock_llm.side_effect = [
                json.dumps(mock_agent_output.to_dict(), ensure_ascii=False),
                json.dumps(mock_da_output.to_dict(), ensure_ascii=False),
                json.dumps(mock_synthesizer_output.to_dict(), ensure_ascii=False),
            ]

            passed = await run_synthesizer_calibration()

        assert passed is True

    @pytest.mark.anyio
    async def test_synthesizer_calibration_passes_with_empty_dissent(
        self, mock_features, mock_agent_output, mock_da_output
    ):
        """Synthesizer 校准通过：dissent_points 可以为空列表."""
        syn_no_dissent = SynthesizerOutput(
            final_signal="bullish",
            conviction=80,
            consensus_summary="一致看好",
            dissent_points=[],  # 空列表是合法的
            pending_verification=["test"],
        )

        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = [
                json.dumps(mock_agent_output.to_dict(), ensure_ascii=False),
                json.dumps(mock_da_output.to_dict(), ensure_ascii=False),
                json.dumps(syn_no_dissent.to_dict(), ensure_ascii=False),
            ]

            passed = await run_synthesizer_calibration()

        assert passed is True


class TestRunCalibration:
    """run_calibration 执行验证."""

    @pytest.mark.anyio
    async def test_run_calibration_bullish(self, mock_features, mock_agent_output, mock_da_output, mock_synthesizer_output):
        """完整校准流程通过."""
        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            # Mock LLM 返回序列：
            # - 巴菲特看多 (600519): bullish
            # - 巴菲特看空 (600900): neutral
            # - 段永平看多 (600519): bullish
            # - DA: neutral + blind_spots
            # - Synthesizer: bullish + dissent_points
            bullish_output = json.dumps(mock_agent_output.to_dict(), ensure_ascii=False)
            neutral_output = json.dumps({
                "name": "buffett",
                "signal": "neutral",
                "conviction": 50,
                "core_thesis": "公用事业估值偏高",
                "key_metrics": ["PE 20x"],
                "risks": ["政策风险"],
                "what_would_change_my_mind": "分红率提升",
                "out_of_circle": False,
                "historical_parallel": None,
            }, ensure_ascii=False)
            da_output = json.dumps(mock_da_output.to_dict(), ensure_ascii=False)
            syn_output = json.dumps(mock_synthesizer_output.to_dict(), ensure_ascii=False)

            mock_llm.side_effect = [
                bullish_output,  # 巴菲特 600519
                neutral_output,  # 巴菲特 600900
                bullish_output,  # 段永平 600519
                bullish_output,  # DA R1
                da_output,       # DA
                bullish_output,  # Synthesizer R1
                da_output,       # Synthesizer DA
                syn_output,      # Synthesizer
            ]

            result = await run_calibration()
            assert result is True

    @pytest.mark.anyio
    async def test_run_calibration_bearish(self, mock_features):
        """看多案例收到 bearish 信号时校准失败."""
        async def mock_llm(*args, **kwargs):
            # 两个案例都返回 bearish
            return json.dumps({
                "name": "buffett",
                "signal": "bearish",
                "conviction": 70,
                "core_thesis": "风险过高",
                "key_metrics": ["负债率 80%"],
                "risks": ["现金流紧张"],
                "what_would_change_my_mind": "负债率下降",
                "out_of_circle": False,
                "historical_parallel": None,
            }, ensure_ascii=False)

        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.assemble_council_features", return_value=mock_features), \
             patch("council.debate.call_llm", new_callable=AsyncMock, side_effect=mock_llm):
            result = await run_calibration()
            # 茅台期望 bullish 但收到 bearish → FAILED
            assert result is False
