"""f2 §5.5/5.6: verify_da_fact_check 单元测试（含 DA skipped 分支，spec review #3）.

- DA ran（da_output 非空）：
  - extra.evidence_quality_assessment 非空 → 通过
  - 缺 evidence_quality_assessment → 拦截
  - recommendation 引用不存在 agent_id → 拦截
- DA skipped（da_output=None，按 da_skipped_reason 分流）：
  - low_divergence / extreme_divergence（情况 A）→ 跳过（pass=True + 空 warnings）
  - evidence_exhausted / runtime_degraded（情况 B）→ soft warning
"""
from __future__ import annotations

from council.schema import AgentOutput
from council.verify_quality_gate import verify_da_fact_check


def _da_agent(
    evidence_quality_assessment: dict | None = None,
    recommendation: str | None = None,
) -> AgentOutput:
    """构造 DA AgentOutput."""
    extra = {}
    if evidence_quality_assessment is not None:
        extra["evidence_quality_assessment"] = evidence_quality_assessment
    if recommendation is not None:
        extra["recommendation"] = recommendation
    return AgentOutput(
        name="da",
        signal="neutral",
        conviction=0,
        core_thesis="盲点",
        key_metrics=[],
        risks=[],
        what_would_change_my_mind="证据",
        out_of_circle=False,
        extra=extra,
    )


class TestDAFactCheckRan:
    """DA ran（da_output 非空）."""

    def test_has_evidence_quality_assessment_passes(self):
        agent = _da_agent(
            evidence_quality_assessment={"buffett": "accurate", "munger": "moderate"},
            recommendation="defer_to_buffett_consensus",
        )
        ok, issues = verify_da_fact_check(agent)
        assert ok is True
        assert issues == []

    def test_missing_evidence_quality_assessment_blocked(self):
        agent = _da_agent(recommendation="no_clear_winner")  # 无 evidence_quality_assessment
        ok, issues = verify_da_fact_check(agent)
        assert ok is False
        assert any("evidence_quality_assessment" in i for i in issues)

    def test_recommendation_invalid_agent_blocked(self):
        agent = _da_agent(
            evidence_quality_assessment={"buffett": "accurate"},
            recommendation="defer_to_zhangkun_consensus",  # zhangkun 不在 registry
        )
        ok, issues = verify_da_fact_check(agent)
        assert ok is False


class TestDAFactCheckSkipped:
    """DA skipped（da_output=None，spec review #3 情况 A/B 分流）."""

    def test_low_divergence_skips_no_warning(self):
        """情况 A：low_divergence → 跳过，pass=True 空 warnings."""
        ok, warnings = verify_da_fact_check(None, da_skipped_reason="low_divergence")
        assert ok is True
        assert warnings == []

    def test_extreme_divergence_skips_no_warning(self):
        """情况 A：extreme_divergence → 跳过."""
        ok, warnings = verify_da_fact_check(None, da_skipped_reason="extreme_divergence")
        assert ok is True
        assert warnings == []

    def test_evidence_exhausted_soft_warning(self):
        """情况 B：evidence_exhausted → soft warning（信息缺口可见）."""
        ok, warnings = verify_da_fact_check(None, da_skipped_reason="evidence_exhausted")
        assert ok is True  # 不阻断
        assert len(warnings) > 0
        assert any("da_skipped" in w for w in warnings)

    def test_runtime_degraded_soft_warning(self):
        """情况 B：runtime_degraded → soft warning."""
        ok, warnings = verify_da_fact_check(None, da_skipped_reason="runtime_degraded")
        assert ok is True
        assert len(warnings) > 0
        assert any("da_skipped" in w for w in warnings)
