"""L3 council 校准测试.

覆盖 calibrate.py 的 run_calibration 逻辑，验证校准用例执行。
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from council.calibrate import CALIBRATION_CASES, run_calibration
from council.schema import AgentOutput


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


class TestRunCalibration:
    """run_calibration 执行验证."""

    @pytest.mark.anyio
    async def test_run_calibration_bullish(self):
        """看多案例校准通过."""
        # Mock returns bullish for 600519, non-bullish for 600900
        call_count = 0

        async def mock_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # First call is 600519 (bullish), second is 600900 (non-bullish)
            if call_count == 1:
                return json.dumps({
                    "signal": "bullish",
                    "conviction": 85,
                    "core_thesis": "品牌护城河深厚",
                    "key_metrics": ["ROE 30%"],
                    "risks": ["宏观风险"],
                    "what_would_change_my_mind": "收入下降",
                    "out_of_circle": False,
                    "historical_parallel": None,
                }, ensure_ascii=False)
            else:
                return json.dumps({
                    "signal": "neutral",
                    "conviction": 50,
                    "core_thesis": "公用事业估值偏高",
                    "key_metrics": ["PE 20x"],
                    "risks": ["政策风险"],
                    "what_would_change_my_mind": "分红率提升",
                    "out_of_circle": False,
                    "historical_parallel": None,
                }, ensure_ascii=False)

        with patch("council.debate.call_llm", new_callable=AsyncMock, side_effect=mock_llm):
            result = await run_calibration()
            assert result is True

    @pytest.mark.anyio
    async def test_run_calibration_bearish(self):
        """看多案例收到 bearish 信号时校准失败."""
        async def mock_llm(*args, **kwargs):
            # 两个案例都返回 bearish
            return json.dumps({
                "signal": "bearish",
                "conviction": 70,
                "core_thesis": "风险过高",
                "key_metrics": ["负债率 80%"],
                "risks": ["现金流紧张"],
                "what_would_change_my_mind": "负债率下降",
                "out_of_circle": False,
                "historical_parallel": None,
            }, ensure_ascii=False)

        with patch("council.debate.call_llm", new_callable=AsyncMock, side_effect=mock_llm):
            result = await run_calibration()
            # 茅台期望 bullish 但收到 bearish → FAILED
            assert result is False
