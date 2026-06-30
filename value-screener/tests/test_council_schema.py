"""L3 council schema 单元测试.

覆盖 AgentOutput 校验（合法/非法 JSON/字段缺失/枚举越界）
和 CouncilResult fallback 逻辑。
"""
from __future__ import annotations

import json
import pytest

from council.schema import AgentOutput, CouncilResult, ValidationError


# ── AgentOutput 校验 ──────────────────────────────────────────

VALID_DATA = {
    "signal": "bullish",
    "conviction": 85,
    "core_thesis": "品牌护城河深厚",
    "key_metrics": ["ROE 32%", "净利率 47%"],
    "risks": ["宏观经济放缓"],
    "what_would_change_my_mind": "连续两季收入负增长",
    "out_of_circle": False,
    "historical_parallel": "类似可口可乐",
}


class TestAgentOutputFromDict:
    def test_valid(self):
        out = AgentOutput.from_dict("buffett", VALID_DATA)
        assert out.name == "buffett"
        assert out.signal == "bullish"
        assert out.conviction == 85
        assert out.core_thesis == "品牌护城河深厚"

    def test_invalid_signal(self):
        data = {**VALID_DATA, "signal": "strong_buy"}
        with pytest.raises(ValidationError, match="invalid signal"):
            AgentOutput.from_dict("buffett", data)

    def test_missing_signal(self):
        data = {k: v for k, v in VALID_DATA.items() if k != "signal"}
        with pytest.raises(ValidationError, match="missing required"):
            AgentOutput.from_dict("buffett", data)

    def test_missing_core_thesis(self):
        data = {k: v for k, v in VALID_DATA.items() if k != "core_thesis"}
        with pytest.raises(ValidationError, match="missing required"):
            AgentOutput.from_dict("buffett", data)

    def test_missing_wwcm(self):
        data = {k: v for k, v in VALID_DATA.items() if k != "what_would_change_my_mind"}
        with pytest.raises(ValidationError, match="missing required"):
            AgentOutput.from_dict("buffett", data)

    def test_conviction_out_of_range(self):
        data = {**VALID_DATA, "conviction": 150}
        with pytest.raises(ValidationError, match="conviction must be int 0-100"):
            AgentOutput.from_dict("buffett", data)

    def test_conviction_negative(self):
        data = {**VALID_DATA, "conviction": -5}
        with pytest.raises(ValidationError, match="conviction must be int 0-100"):
            AgentOutput.from_dict("buffett", data)

    def test_conviction_not_int(self):
        data = {**VALID_DATA, "conviction": "high"}
        with pytest.raises(ValidationError, match="conviction must be int 0-100"):
            AgentOutput.from_dict("buffett", data)

    def test_empty_core_thesis(self):
        data = {**VALID_DATA, "core_thesis": "   "}
        with pytest.raises(ValidationError, match="core_thesis must be non-empty"):
            AgentOutput.from_dict("buffett", data)

    def test_empty_wwcm(self):
        data = {**VALID_DATA, "what_would_change_my_mind": ""}
        with pytest.raises(ValidationError, match="what_would_change_my_mind must be non-empty"):
            AgentOutput.from_dict("buffett", data)

    def test_out_of_circle_not_bool(self):
        data = {**VALID_DATA, "out_of_circle": "no"}
        with pytest.raises(ValidationError, match="out_of_circle must be bool"):
            AgentOutput.from_dict("buffett", data)

    def test_key_metrics_not_list(self):
        data = {**VALID_DATA, "key_metrics": "ROE 32%"}
        with pytest.raises(ValidationError, match="key_metrics must be list"):
            AgentOutput.from_dict("buffett", data)

    def test_risks_not_list(self):
        data = {**VALID_DATA, "risks": "macro risk"}
        with pytest.raises(ValidationError, match="risks must be list"):
            AgentOutput.from_dict("buffett", data)

    def test_minimal_valid(self):
        """所有选填字段缺省值仍合法."""
        data = {
            "signal": "neutral",
            "conviction": 50,
            "core_thesis": "看不清",
            "what_would_change_my_mind": "更多数据",
            "out_of_circle": True,
        }
        out = AgentOutput.from_dict("buffett", data)
        assert out.key_metrics == []
        assert out.risks == []
        assert out.historical_parallel is None


class TestAgentOutputFromJson:
    def test_valid_json(self):
        json_str = json.dumps(VALID_DATA)
        out = AgentOutput.from_json("buffett", json_str)
        assert out.signal == "bullish"

    def test_invalid_json(self):
        with pytest.raises(ValidationError, match="invalid JSON"):
            AgentOutput.from_json("buffett", "{not valid json")


class TestAgentOutputSerialization:
    def test_to_dict_roundtrip(self):
        out = AgentOutput.from_dict("buffett", VALID_DATA)
        d = out.to_dict()
        assert d["signal"] == "bullish"
        assert d["name"] == "buffett"
        out2 = AgentOutput.from_dict(d["name"], d)
        assert out2.signal == out.signal

    def test_to_json(self):
        out = AgentOutput.from_dict("buffett", VALID_DATA)
        json_str = out.to_json()
        parsed = json.loads(json_str)
        assert parsed["signal"] == "bullish"


# ── CouncilResult ──────────────────────────────────────────────

class TestCouncilResult:
    def test_single_agent_fallback(self):
        """单 agent: final_verdict 取 rounds[0][0].signal."""
        agent = AgentOutput.from_dict("buffett", VALID_DATA)
        result = CouncilResult(
            ticker="600519",
            rounds=[[agent], None, None, None],
            final_verdict="",
        )
        assert result.final_verdict == "bullish"

    def test_explicit_final_verdict_preserved(self):
        """显式传入 final_verdict 不被覆盖."""
        agent = AgentOutput.from_dict("buffett", VALID_DATA)
        result = CouncilResult(
            ticker="600519",
            rounds=[[agent], None, None, None],
            final_verdict="neutral",
        )
        assert result.final_verdict == "neutral"

    def test_extract_key_variables(self):
        a1 = AgentOutput.from_dict("buffett", VALID_DATA)
        a2 = AgentOutput.from_dict("buffett", {
            **VALID_DATA,
            "what_would_change_my_mind": "利率大幅上升",
        })
        variables = CouncilResult.extract_key_variables([[a1, a2], None, None, None])
        assert len(variables) == 2
        assert "连续两季收入负增长" in variables[0]

    def test_extract_key_variables_skips_none_rounds(self):
        a1 = AgentOutput.from_dict("buffett", VALID_DATA)
        variables = CouncilResult.extract_key_variables([[a1], None, None, None])
        assert len(variables) == 1

    def test_to_json(self):
        agent = AgentOutput.from_dict("buffett", VALID_DATA)
        result = CouncilResult(
            ticker="600519",
            rounds=[[agent], None, None, None],
            final_verdict="bullish",
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["ticker"] == "600519"
        assert parsed["final_verdict"] == "bullish"
        assert parsed["rounds"][1] is None
