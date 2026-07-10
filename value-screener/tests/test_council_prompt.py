"""L3 prompt builders 单元测试.

覆盖:
- 每位大师 prompt 含关键内容
- DA/synthesizer prompt 含职责定义
- 冯柳 prompt 含特有字段说明
"""
from __future__ import annotations

import pytest

from council.prompt import (
    build_buffett_prompt,
    build_munger_prompt,
    build_duan_prompt,
    build_feng_liu_prompt,
    build_da_prompt,
    build_synthesizer_prompt,
)


class TestMungerPrompt:
    def test_contains_converse_thinking(self):
        """芒格 prompt 含逆向思考."""
        prompt = build_munger_prompt()
        assert "逆向思考" in prompt
        assert "反过来想" in prompt

    def test_contains_psychological_biases(self):
        """含 25 心理偏差检测."""
        prompt = build_munger_prompt()
        assert "心理偏差" in prompt
        assert "激励偏差" in prompt
        assert "确认偏差" in prompt

    def test_contains_lattice_mental_models(self):
        """含格栅思维."""
        prompt = build_munger_prompt()
        assert "格栅思维" in prompt

    def test_contains_json_format(self):
        """含 JSON 输出格式约束."""
        prompt = build_munger_prompt()
        assert "signal" in prompt
        assert "conviction" in prompt
        assert "core_thesis" in prompt


class TestDuanPrompt:
    def test_contains_business_model(self):
        """段永平 prompt 含商业模式优先."""
        prompt = build_duan_prompt()
        assert "商业模式优先" in prompt

    def test_contains_benfen(self):
        """含管理层本分度."""
        prompt = build_duan_prompt()
        assert "本分" in prompt

    def test_contains_circle_of_competence(self):
        """含能力圈."""
        prompt = build_duan_prompt()
        assert "能力圈" in prompt

    def test_contains_json_format(self):
        """含 JSON 输出格式约束."""
        prompt = build_duan_prompt()
        assert "signal" in prompt
        assert "core_thesis" in prompt


class TestFengLiuPrompt:
    def test_contains_weak_system(self):
        """冯柳 prompt 含弱者体系."""
        prompt = build_feng_liu_prompt()
        assert "弱者体系" in prompt

    def test_contains_cognitive_gaps(self):
        """含三类认知差."""
        prompt = build_feng_liu_prompt()
        assert "行为差" in prompt
        assert "分析差" in prompt
        assert "信息差" in prompt

    def test_contains_odds_priority(self):
        """含赔率优先于胜率."""
        prompt = build_feng_liu_prompt()
        assert "赔率优先于胜率" in prompt

    def test_contains_extra_fields(self):
        """末尾列出 5 个特有字段."""
        prompt = build_feng_liu_prompt()
        assert "market_consensus" in prompt
        assert "consensus_flaw" in prompt
        assert "odds_assessment" in prompt
        assert "is_reversible" in prompt
        assert "catalyst" in prompt

    def test_contains_json_format(self):
        """含 JSON 输出格式约束."""
        prompt = build_feng_liu_prompt()
        assert "signal" in prompt
        assert "core_thesis" in prompt


class TestDAPrompt:
    def test_contains_concrete_vulnerabilities(self):
        """DA prompt 强调具体漏洞."""
        prompt = build_da_prompt()
        assert "具体" in prompt
        assert "泛泛之谈" in prompt

    def test_contains_blind_spots_structure(self):
        """列出 blind_spots 结构."""
        prompt = build_da_prompt()
        assert "blind_spots" in prompt
        assert "title" in prompt
        assert "detail" in prompt
        assert "which_agents_missed_it" in prompt

    def test_signal_fixed_neutral(self):
        """signal 固定 neutral."""
        prompt = build_da_prompt()
        assert '"neutral"' in prompt


class TestSynthesizerPrompt:
    def test_contains_synthesizer_output_fields(self):
        """列出 SynthesizerOutput 字段."""
        prompt = build_synthesizer_prompt()
        assert "final_signal" in prompt
        assert "consensus_summary" in prompt
        assert "dissent_points" in prompt
        assert "pending_verification" in prompt

    def test_emphasizes_preserving_dissent(self):
        """强调保留分歧."""
        prompt = build_synthesizer_prompt()
        assert "保留真实分歧点" in prompt
        assert "不抹平" in prompt

    def test_weighted_majority(self):
        """含加权多数逻辑."""
        prompt = build_synthesizer_prompt()
        assert "加权多数" in prompt


class TestAllPromptsReturnStrings:
    def test_all_return_non_empty_strings(self):
        """所有 prompt builder 返回非空字符串."""
        builders = [
            build_buffett_prompt,
            build_munger_prompt,
            build_duan_prompt,
            build_feng_liu_prompt,
            build_da_prompt,
            build_synthesizer_prompt,
        ]
        for builder in builders:
            result = builder()
            assert isinstance(result, str)
            assert len(result) > 100


# ── f2 §4 prompt 改造测试 ──────────────────────────────────────

class TestAgentNewEvidenceFields:
    """f2 §4.1: 各 agent prompt 输出格式段含 new_evidence / evidence_exhausted 字段说明."""

    @pytest.mark.parametrize("builder", [
        build_buffett_prompt, build_munger_prompt,
        build_duan_prompt, build_feng_liu_prompt,
    ])
    def test_agent_prompt_contains_new_evidence_fields(self, builder):
        prompt = builder()
        assert "new_evidence" in prompt
        assert "evidence_exhausted" in prompt


class TestDAPromptArbitration:
    """f2 §4.3: DA prompt 加仲裁职责（事实回查 + evidence_quality_assessment + recommendation）."""

    def test_contains_fact_check_duty(self):
        """DA prompt 含事实回查约束（回查 features 实际值）."""
        prompt = build_da_prompt()
        assert "回查" in prompt or "事实" in prompt
        assert "evidence_quality_assessment" in prompt

    def test_contains_recommendation_field(self):
        """DA prompt 含 recommendation 输出结构."""
        prompt = build_da_prompt()
        assert "recommendation" in prompt

    def test_contains_evidence_quality_assessment_values(self):
        """evidence_quality_assessment 的取值说明（accurate/moderate/weak/inaccurate）."""
        prompt = build_da_prompt()
        assert "accurate" in prompt
        assert "inaccurate" in prompt


class TestSynthesizerPromptDivergenceReport:
    """f2 §4.4: synthesizer prompt 加 DA 仲裁依赖 + 分歧报告字段 + structural 约束."""

    def test_contains_da_arbitration_dependency(self):
        """synthesizer 基于 DA 的 evidence_quality_assessment/recommendation 做最终判断."""
        prompt = build_synthesizer_prompt()
        assert "evidence_quality_assessment" in prompt
        assert "recommendation" in prompt

    def test_contains_divergence_report_fields(self):
        """含分歧报告输出字段（divergence_level/key_disagreements/confidence_adjustment/
        divergence_source/calibration_status）."""
        prompt = build_synthesizer_prompt()
        assert "divergence_level" in prompt
        assert "key_disagreements" in prompt
        assert "confidence_adjustment" in prompt
        assert "divergence_source" in prompt
        assert "calibration_status" in prompt

    def test_contains_structural_unresolvable_constraint(self):
        """structural 高分歧时标「不可解决」约束."""
        prompt = build_synthesizer_prompt()
        assert "不可解决" in prompt
        assert "structural" in prompt
