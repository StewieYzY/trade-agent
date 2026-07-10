"""f2 §5.3/5.4: verify_divergence_report 单元测试（hard gate）.

校验 R4 SynthesizerOutput 的分歧报告字段完整性：
- divergence_level 非空 + calibration_status="uncalibrated" → 通过
- divergence_level="high"/"extreme" 缺 key_disagreements → 拦截
- 缺 divergence_level → 拦截
"""
from __future__ import annotations

from council.schema import SynthesizerOutput
from council.verify_quality_gate import verify_divergence_report


def _syn(
    divergence_level: str | None = "medium",
    key_disagreements: list[dict] | None = None,
    calibration_status: str = "uncalibrated",
) -> SynthesizerOutput:
    """构造 SynthesizerOutput."""
    return SynthesizerOutput(
        final_signal="bullish",
        conviction=70,
        consensus_summary="看好",
        divergence_level=divergence_level,
        key_disagreements=key_disagreements if key_disagreements is not None else [],
        calibration_status=calibration_status,
    )


class TestDivergenceReport:
    def test_complete_report_passes(self):
        """divergence_level 非空 + calibration_status 正确 → 通过."""
        syn = _syn(divergence_level="medium", key_disagreements=[{"topic": "估值"}])
        ok, issues = verify_divergence_report(syn)
        assert ok is True
        assert issues == []

    def test_high_missing_key_disagreements_blocked(self):
        """divergence_level=high 但 key_disagreements 空 → 拦截."""
        syn = _syn(divergence_level="high", key_disagreements=[])
        ok, issues = verify_divergence_report(syn)
        assert ok is False
        assert any("key_disagreements" in i for i in issues)

    def test_extreme_missing_key_disagreements_blocked(self):
        """divergence_level=extreme 但 key_disagreements 空 → 拦截."""
        syn = _syn(divergence_level="extreme", key_disagreements=[])
        ok, issues = verify_divergence_report(syn)
        assert ok is False

    def test_missing_divergence_level_blocked(self):
        """缺 divergence_level（None）→ 拦截."""
        syn = _syn(divergence_level=None)
        ok, issues = verify_divergence_report(syn)
        assert ok is False
        assert any("divergence_level" in i for i in issues)

    def test_wrong_calibration_status_blocked(self):
        """calibration_status 不是 uncalibrated → 拦截."""
        syn = _syn(divergence_level="medium", calibration_status="calibrated")
        ok, issues = verify_divergence_report(syn)
        assert ok is False
