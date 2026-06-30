"""L3 council schema 单元测试.

覆盖 AgentOutput 校验（合法/非法 JSON/字段缺失/枚举越界）
和 CouncilResult fallback 逻辑。
"""
from __future__ import annotations

import json
import pytest

from council.schema import AgentOutput, CouncilResult, SynthesizerOutput, ValidationError


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
        """单 agent: final_verdict 取 round1[0].signal."""
        agent = AgentOutput.from_dict("buffett", VALID_DATA)
        result = CouncilResult(
            ticker="600519",
            round1=[agent],
            final_verdict="",
        )
        assert result.final_verdict == "bullish"

    def test_explicit_final_verdict_preserved(self):
        """显式传入 final_verdict 不被覆盖."""
        agent = AgentOutput.from_dict("buffett", VALID_DATA)
        result = CouncilResult(
            ticker="600519",
            round1=[agent],
            final_verdict="neutral",
        )
        assert result.final_verdict == "neutral"

    def test_extract_key_variables(self):
        a1 = AgentOutput.from_dict("buffett", VALID_DATA)
        a2 = AgentOutput.from_dict("buffett", {
            **VALID_DATA,
            "what_would_change_my_mind": "利率大幅上升",
        })
        variables = CouncilResult.extract_key_variables([a1, a2])
        assert len(variables) == 2
        assert "连续两季收入负增长" in variables[0]

    def test_extract_key_variables_with_round2(self):
        a1 = AgentOutput.from_dict("buffett", VALID_DATA)
        a2 = AgentOutput.from_dict("buffett", {
            **VALID_DATA,
            "what_would_change_my_mind": "市场情绪转变",
        })
        variables = CouncilResult.extract_key_variables([a1], [a2])
        assert len(variables) == 2

    def test_extract_key_variables_skips_none_round2(self):
        a1 = AgentOutput.from_dict("buffett", VALID_DATA)
        variables = CouncilResult.extract_key_variables([a1])
        assert len(variables) == 1

    def test_to_json(self):
        agent = AgentOutput.from_dict("buffett", VALID_DATA)
        result = CouncilResult(
            ticker="600519",
            round1=[agent],
            final_verdict="bullish",
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["ticker"] == "600519"
        assert parsed["final_verdict"] == "bullish"
        assert parsed["round1"] is not None
        assert parsed["round2"] is None

    def test_full_council_result_to_json(self):
        """全天团 CouncilResult 序列化."""
        agent = AgentOutput.from_dict("buffett", VALID_DATA)
        synthesizer = SynthesizerOutput(
            final_signal="bullish",
            conviction=75,
            consensus_summary="品牌护城河深厚",
            dissent_points=[{"topic": "估值", "who_disagrees": "munger", "their_reason": "PE 过高"}],
            pending_verification=["现金流验证"],
        )
        result = CouncilResult(
            ticker="600519",
            round1=[agent],
            round2=[agent],
            round3=agent,
            round4=synthesizer,
            final_verdict="bullish",
            consensus_summary="品牌护城河深厚",
            dissent_points=[{"topic": "估值"}],
            pending_verification=["现金流验证"],
        )
        json_str = result.to_json()
        parsed = json.loads(json_str)
        assert parsed["round1"] is not None
        assert parsed["round2"] is not None
        assert parsed["round3"] is not None
        assert parsed["round4"] is not None
        assert parsed["consensus_summary"] == "品牌护城河深厚"


# ── AgentOutput extra 字段 ─────────────────────────────────────

class TestAgentOutputExtraField:
    def test_extra_field_passthrough_feng_liu(self):
        """冯柳特有字段透传."""
        data = {
            **VALID_DATA,
            "market_consensus": "市场认为业绩下滑",
            "consensus_flaw": "过度反应短期利空",
            "odds_assessment": "赔率 3:1",
            "is_reversible": True,
            "catalyst": "Q3 业绩拐点",
        }
        out = AgentOutput.from_dict("feng_liu", data)
        assert out.extra["market_consensus"] == "市场认为业绩下滑"
        assert out.extra["consensus_flaw"] == "过度反应短期利空"
        assert out.extra["odds_assessment"] == "赔率 3:1"
        assert out.extra["is_reversible"] is True
        assert out.extra["catalyst"] == "Q3 业绩拐点"

    def test_extra_field_passthrough_da_blind_spots(self):
        """DA blind_spots 透传."""
        data = {
            **VALID_DATA,
            "blind_spots": [
                {
                    "title": "管理层减持",
                    "detail": "管理层去年减持了 15%",
                    "which_agents_missed_it": ["buffett", "munger"],
                }
            ],
        }
        out = AgentOutput.from_dict("da", data)
        assert "blind_spots" in out.extra
        assert len(out.extra["blind_spots"]) == 1
        assert out.extra["blind_spots"][0]["title"] == "管理层减持"

    def test_to_dict_includes_extra(self):
        """to_dict 包含 extra 字段."""
        data = {
            **VALID_DATA,
            "market_consensus": "市场共识",
        }
        out = AgentOutput.from_dict("feng_liu", data)
        d = out.to_dict()
        assert "market_consensus" in d
        assert d["market_consensus"] == "市场共识"

    def test_to_json_includes_extra(self):
        """to_json 包含 extra 字段."""
        data = {
            **VALID_DATA,
            "odds_assessment": "赔率 2:1",
        }
        out = AgentOutput.from_dict("feng_liu", data)
        json_str = out.to_json()
        parsed = json.loads(json_str)
        assert "odds_assessment" in parsed
        assert parsed["odds_assessment"] == "赔率 2:1"

    def test_base_field_validation_unchanged(self):
        """基础字段校验逻辑不变（extra 不影响）."""
        # signal 枚举校验仍然生效
        data = {**VALID_DATA, "signal": "strong_buy", "extra_field": "value"}
        with pytest.raises(ValidationError, match="invalid signal"):
            AgentOutput.from_dict("test", data)

        # conviction 范围校验仍然生效
        data = {**VALID_DATA, "conviction": 150, "extra_field": "value"}
        with pytest.raises(ValidationError, match="conviction must be int 0-100"):
            AgentOutput.from_dict("test", data)

    def test_no_extra_fields_when_clean(self):
        """无 extra 字段时 extra 为空 dict."""
        out = AgentOutput.from_dict("buffett", VALID_DATA)
        assert out.extra == {}


# ── SynthesizerOutput ──────────────────────────────────────────

class TestSynthesizerOutput:
    def test_valid_creation(self):
        """合法创建."""
        syn = SynthesizerOutput(
            final_signal="bullish",
            conviction=75,
            consensus_summary="品牌护城河深厚",
            dissent_points=[{"topic": "估值", "who_disagrees": "munger", "their_reason": "PE 过高"}],
            pending_verification=["现金流验证"],
        )
        assert syn.final_signal == "bullish"
        assert syn.conviction == 75
        assert syn.consensus_summary == "品牌护城河深厚"
        assert len(syn.dissent_points) == 1
        assert len(syn.pending_verification) == 1

    def test_invalid_final_signal(self):
        """final_signal 枚举校验."""
        with pytest.raises(ValidationError, match="invalid final_signal"):
            SynthesizerOutput(
                final_signal="strong_buy",
                conviction=75,
                consensus_summary="test",
            )

    def test_invalid_conviction_range(self):
        """conviction 范围校验."""
        with pytest.raises(ValidationError, match="conviction must be int 0-100"):
            SynthesizerOutput(
                final_signal="bullish",
                conviction=150,
                consensus_summary="test",
            )

    def test_empty_consensus_summary(self):
        """consensus_summary 非空校验."""
        with pytest.raises(ValidationError, match="consensus_summary must be non-empty"):
            SynthesizerOutput(
                final_signal="bullish",
                conviction=75,
                consensus_summary="",
            )

    def test_from_json(self):
        """从 JSON 反序列化."""
        json_str = json.dumps({
            "final_signal": "neutral",
            "conviction": 50,
            "consensus_summary": "分歧较大",
            "dissent_points": [],
            "pending_verification": [],
        })
        syn = SynthesizerOutput.from_json(json_str)
        assert syn.final_signal == "neutral"
        assert syn.conviction == 50

    def test_from_dict(self):
        """从 dict 反序列化."""
        data = {
            "final_signal": "bearish",
            "conviction": 30,
            "consensus_summary": "风险过高",
        }
        syn = SynthesizerOutput.from_dict(data)
        assert syn.final_signal == "bearish"
        assert syn.dissent_points == []
        assert syn.pending_verification == []

    def test_to_json(self):
        """序列化为 JSON."""
        syn = SynthesizerOutput(
            final_signal="bullish",
            conviction=80,
            consensus_summary="test",
        )
        json_str = syn.to_json()
        parsed = json.loads(json_str)
        assert parsed["final_signal"] == "bullish"
        assert parsed["conviction"] == 80

    def test_to_dict(self):
        """转换为 dict."""
        syn = SynthesizerOutput(
            final_signal="bullish",
            conviction=80,
            consensus_summary="test",
            dissent_points=[{"topic": "test"}],
        )
        d = syn.to_dict()
        assert d["final_signal"] == "bullish"
        assert d["consensus_summary"] == "test"
        assert len(d["dissent_points"]) == 1
