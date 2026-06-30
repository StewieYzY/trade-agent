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
        # Mock run_debate 返回包含 R1+R2 的 CouncilResult
        from council.schema import CouncilResult
        mock_council_result = CouncilResult(
            ticker="600519.SH",
            round1=[mock_agent_output],
            round2=[mock_agent_output],
            round3=None,
            round4=None,
            final_verdict="bullish",
            key_variables=[],
            consensus_summary=None,
            dissent_points=None,
            pending_verification=None,
            debate_path=None,
        )

        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.calibrate.run_debate", new_callable=AsyncMock, return_value=mock_council_result), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps(mock_da_output.to_dict(), ensure_ascii=False)
            passed = await run_da_calibration()

        assert passed is True

    @pytest.mark.anyio
    async def test_da_calibration_fails_on_invalid_signal(
        self, mock_features, mock_agent_output
    ):
        """DA 校准失败：signal != 'neutral'."""
        from council.schema import CouncilResult
        mock_council_result = CouncilResult(
            ticker="600519.SH",
            round1=[mock_agent_output],
            round2=[mock_agent_output],
            round3=None,
            round4=None,
            final_verdict="bullish",
            key_variables=[],
            consensus_summary=None,
            dissent_points=None,
            pending_verification=None,
            debate_path=None,
        )

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
             patch("council.calibrate.run_debate", new_callable=AsyncMock, return_value=mock_council_result), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps(invalid_da_output.to_dict(), ensure_ascii=False)
            passed = await run_da_calibration()

        assert passed is False

    @pytest.mark.anyio
    async def test_da_calibration_fails_on_empty_blind_spots(
        self, mock_features, mock_agent_output
    ):
        """DA 校准失败：blind_spots 为空."""
        from council.schema import CouncilResult
        mock_council_result = CouncilResult(
            ticker="600519.SH",
            round1=[mock_agent_output],
            round2=[mock_agent_output],
            round3=None,
            round4=None,
            final_verdict="bullish",
            key_variables=[],
            consensus_summary=None,
            dissent_points=None,
            pending_verification=None,
            debate_path=None,
        )

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
             patch("council.calibrate.run_debate", new_callable=AsyncMock, return_value=mock_council_result), \
             patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = json.dumps(empty_blind_spots.to_dict(), ensure_ascii=False)
            passed = await run_da_calibration()

        assert passed is False


class TestSynthesizerCalibration:
    """Synthesizer 校准测试."""

    @pytest.mark.anyio
    async def test_synthesizer_calibration_passes(
        self, mock_features, mock_agent_output, mock_da_output, mock_synthesizer_output
    ):
        """Synthesizer 校准通过：schema 合法 + dissent_points 存在."""
        from council.schema import CouncilResult
        mock_council_result = CouncilResult(
            ticker="600519.SH",
            round1=[mock_agent_output],
            round2=[mock_agent_output],
            round3=None,
            round4=None,
            final_verdict="bullish",
            key_variables=[],
            consensus_summary=None,
            dissent_points=None,
            pending_verification=None,
            debate_path=None,
        )

        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.calibrate.run_debate", new_callable=AsyncMock, return_value=mock_council_result), \
             patch("council.calibrate._call_da", new_callable=AsyncMock, return_value=mock_da_output), \
             patch("council.calibrate._call_synthesizer", new_callable=AsyncMock, return_value=mock_synthesizer_output):
            passed = await run_synthesizer_calibration()

        assert passed is True

    @pytest.mark.anyio
    async def test_synthesizer_calibration_passes_with_empty_dissent(
        self, mock_features, mock_agent_output, mock_da_output
    ):
        """Synthesizer 校准通过：dissent_points 可以为空列表."""
        from council.schema import CouncilResult
        mock_council_result = CouncilResult(
            ticker="600519.SH",
            round1=[mock_agent_output],
            round2=[mock_agent_output],
            round3=None,
            round4=None,
            final_verdict="bullish",
            key_variables=[],
            consensus_summary=None,
            dissent_points=None,
            pending_verification=None,
            debate_path=None,
        )

        syn_no_dissent = SynthesizerOutput(
            final_signal="bullish",
            conviction=80,
            consensus_summary="一致看好",
            dissent_points=[],  # 空列表是合法的
            pending_verification=["test"],
        )

        with patch("council.calibrate.assemble_council_features", return_value=mock_features), \
             patch("council.calibrate.run_debate", new_callable=AsyncMock, return_value=mock_council_result), \
             patch("council.calibrate._call_da", new_callable=AsyncMock, return_value=mock_da_output), \
             patch("council.calibrate._call_synthesizer", new_callable=AsyncMock, return_value=syn_no_dissent):
            passed = await run_synthesizer_calibration()

        assert passed is True


class TestRunCalibration:
    """run_calibration 执行验证."""

    @pytest.mark.anyio
    async def test_run_calibration_bullish(self, mock_features, mock_agent_output, mock_da_output, mock_synthesizer_output):
        """完整校准流程通过."""
        # Mock 各子校准函数
        with patch("council.calibrate.run_agent_calibration", new_callable=AsyncMock, return_value=True), \
             patch("council.calibrate.run_da_calibration", new_callable=AsyncMock, return_value=True), \
             patch("council.calibrate.run_synthesizer_calibration", new_callable=AsyncMock, return_value=True):
            result = await run_calibration()
            assert result is True

    @pytest.mark.anyio
    async def test_run_calibration_bearish(self, mock_features):
        """看多案例收到 bearish 信号时校准失败."""
        # Mock 投资大师校准失败（信号不匹配）
        with patch("council.calibrate.run_agent_calibration", new_callable=AsyncMock, return_value=False), \
             patch("council.calibrate.run_da_calibration", new_callable=AsyncMock, return_value=True), \
             patch("council.calibrate.run_synthesizer_calibration", new_callable=AsyncMock, return_value=True):
            result = await run_calibration()
            assert result is False
