"""f2 §5.1/5.2: verify_r2_new_evidence 单元测试（soft warning 语义）.

D2 scope 调整（2026-07-10）：R2 新证据从 hard gate 降为 soft warning。
- new_evidence 非空 → 通过（无 warning）
- evidence_exhausted=true → 通过（无 warning）
- 两者皆无 → soft warning（pass=True + warnings 含 r2_no_new_evidence），不拦截
- new_evidence 含凭空数字 → soft warning（pass=True + warnings 含 suspected_fabricated_evidence），
  复用 verify_r1_feature_grounding 的数字提取逻辑检测，但降级为 warning 而非 hard fail
"""
from __future__ import annotations

from council.schema import AgentOutput
from council.verify_quality_gate import verify_r2_new_evidence


def _r2_agent(new_evidence: list[str] | None = None, evidence_exhausted: bool = False) -> AgentOutput:
    """构造 R2 AgentOutput."""
    return AgentOutput(
        name="buffett",
        signal="bullish",
        conviction=80,
        core_thesis="看好",
        key_metrics=[],
        risks=[],
        what_would_change_my_mind="业绩下滑",
        out_of_circle=False,
        new_evidence=new_evidence or [],
        evidence_exhausted=evidence_exhausted,
    )


class TestR2NewEvidenceSoft:
    def test_new_evidence_non_empty_passes(self):
        """new_evidence 非空 → 通过，无 warning."""
        agent = _r2_agent(new_evidence=["PB 1.2"])
        features = {"pb": 1.2}
        ok, warnings = verify_r2_new_evidence(agent, features)
        assert ok is True
        assert warnings == []

    def test_evidence_exhausted_passes(self):
        """evidence_exhausted=true（new_evidence 空）→ 通过，无 warning."""
        agent = _r2_agent(new_evidence=[], evidence_exhausted=True)
        features = {"pb": 1.2}
        ok, warnings = verify_r2_new_evidence(agent, features)
        assert ok is True
        assert warnings == []

    def test_no_evidence_no_exhausted_soft_warning(self):
        """两者皆无 → soft warning（不拦截）."""
        agent = _r2_agent(new_evidence=[], evidence_exhausted=False)
        features = {"pb": 1.2}
        ok, warnings = verify_r2_new_evidence(agent, features)
        assert ok is True  # pass=True，不拦截
        assert len(warnings) > 0
        assert any("r2_no_new_evidence" in w for w in warnings)

    def test_fabricated_number_soft_warning(self):
        """new_evidence 含凭空数字（features 无对应值）→ soft warning，不拦截."""
        # "ROE 50%" 但 features 中无 50
        agent = _r2_agent(new_evidence=["ROE 50%"])
        features = {"roe_3y": 18.2}  # 无 50
        ok, warnings = verify_r2_new_evidence(agent, features)
        assert ok is True  # soft，不拦截
        assert any("suspected_fabricated_evidence" in w for w in warnings)

    def test_grounded_number_passes(self):
        """new_evidence 数字在 features 中有来源 → 通过，无 warning."""
        agent = _r2_agent(new_evidence=["ROE 18.2%"])
        features = {"roe_3y": 18.2}
        ok, warnings = verify_r2_new_evidence(agent, features)
        assert ok is True
        assert warnings == []
