"""f3a §5: feature_numbers 递归遍历测试（D7/D9）.

_collect_feature_numbers(features) 递归遍历 dict/list 收集所有数值，
verify_r1_feature_grounding 和 verify_r2_new_evidence 都调它（消除两处重复）。
f3 dossier 的 research_dossier 是嵌套 dict，定性维度数字需递归展开才能进 feature_numbers，
否则 R1/R2 引用这些数字会被误判「凭空编造」。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.schema import AgentOutput
from council.verify_quality_gate import (
    _collect_feature_numbers,
    verify_r1_feature_grounding,
    verify_r2_new_evidence,
)


def _nested_dossier() -> dict:
    """分层 dossier 含嵌套 research_dossier（peer_avg_pe=15.3 在 research_dossier.peers 内）."""
    return {
        "core_snapshot": {
            "ticker": "600009",
            "pe_ttm": 26.42,
            "roe_3y": [15.0, 16.0, 17.0],
        },
        "research_dossier": {
            "main_business": {"by_industry": [{"revenue_ratio": 0.94, "gross_margin": 0.25}]},
            "peers": {"peer_avg_pe": 15.3, "industry_pe_rank": 2, "peer_count": 4},
            "capex_proxy": {"latest": 1.307e9, "series": [1.244e9, 1.958e9, 1.307e9]},
            "research": {"consensus_eps": 1.152, "target_price": 30.41, "buy_rating_pct": 1.0, "coverage_count": 2},
            "degraded_fields": [],
        },
        "pledge": 8.5,
    }


# ── _collect_feature_numbers 递归 ──────────────────────────────


class TestCollectFeatureNumbersRecursive:
    def test_collects_nested_peer_avg_pe(self):
        """research_dossier.peers.peer_avg_pe=15.3 递归收集到."""
        numbers = _collect_feature_numbers(_nested_dossier())
        # 取绝对值（与 verify 逻辑一致）
        abs_numbers = [abs(n) for n in numbers]
        assert 15.3 == pytest.approx(15.3, abs=0.01)
        assert any(abs(n - 15.3) <= 0.5 for n in abs_numbers), f"未收集到嵌套 peer_avg_pe 15.3: {numbers}"

    def test_collects_deeply_nested_consensus_eps(self):
        """research.research.consensus_eps=1.152 深嵌套收集到."""
        numbers = _collect_feature_numbers(_nested_dossier())
        abs_numbers = [abs(n) for n in numbers]
        assert any(abs(n - 1.152) <= 0.5 for n in abs_numbers), f"未收集到 consensus_eps 1.152"

    def test_collects_list_inside_nested_dict(self):
        """capex_proxy.series list 中的每个数值都收集到."""
        numbers = _collect_feature_numbers(_nested_dossier())
        abs_numbers = [abs(n) for n in numbers]
        # series 含 1.244e9, 1.958e9, 1.307e9
        assert any(abs(n - 1.244e9) <= 1e6 for n in abs_numbers)
        assert any(abs(n - 1.958e9) <= 1e6 for n in abs_numbers)

    def test_collects_top_level_flat_numbers_too(self):
        """旧扁平 features 的顶层标量仍收集到（向后兼容）."""
        flat = {"pe_ttm": 26.42, "roe_3y": [15.0, 16.0, 17.0], "net_margin": 30.0}
        numbers = _collect_feature_numbers(flat)
        abs_numbers = [abs(n) for n in numbers]
        assert any(abs(n - 26.42) <= 0.5 for n in abs_numbers)
        assert any(abs(n - 17.0) <= 0.5 for n in abs_numbers)
        assert any(abs(n - 30.0) <= 0.5 for n in abs_numbers)

    def test_handles_none_and_strings(self):
        """None/字符串/bool 跳过不崩，只收数值."""
        mixed = {"a": None, "b": "str", "c": True, "d": 42.0, "e": {"f": "x", "g": 7}}
        numbers = _collect_feature_numbers(mixed)
        assert 42.0 in [abs(n) for n in numbers] or any(abs(n - 42.0) < 0.01 for n in numbers)
        assert any(abs(n - 7) < 0.01 for n in numbers)

    def test_empty_features_returns_empty(self):
        """空 dict / None → 空列表不崩."""
        assert _collect_feature_numbers({}) == []
        assert _collect_feature_numbers(None) == []


# ── verify_r1_feature_grounding 嵌套兼容 ───────────────────────


def _make_agent(name="buffett", key_metrics=None, core_thesis="基本面良好"):
    return AgentOutput.from_dict(name, {
        "signal": "bullish",
        "conviction": 75,
        "core_thesis": core_thesis,
        "key_metrics": key_metrics or [],
        "risks": [],
        "what_would_change_my_mind": "业绩下滑",
        "out_of_circle": False,
        "historical_parallel": None,
    })


class TestR1GroundingNested:
    def test_r1_cites_nested_peer_avg_pe_passes(self):
        """R1 key_metrics 引用「行业平均 PE 15.3」，dossier.peers.peer_avg_pe=15.3 → 通过（不误判凭空）."""
        agent = _make_agent(key_metrics=["行业平均 PE 15.3", "PE_TTM 26.42"])
        ok, issues = verify_r1_feature_grounding(agent, _nested_dossier())
        assert ok is True
        assert issues == []

    def test_r1_cites_nested_consensus_eps_passes(self):
        """R1 引用「研报 EPS 1.152」，dossier.research.consensus_eps=1.152 → 通过."""
        agent = _make_agent(key_metrics=["研报 consensus EPS 1.152", "目标价 30.41"])
        ok, issues = verify_r1_feature_grounding(agent, _nested_dossier())
        assert ok is True

    def test_r1_fabricated_number_still_detected_with_nested(self):
        """嵌套 dossier 下，凭空数字（dossier 无对应值）仍被检出."""
        agent = _make_agent(key_metrics=["ROE 99%"])  # 99 不在 dossier 任何字段
        ok, issues = verify_r1_feature_grounding(agent, _nested_dossier())
        assert ok is False
        assert any("99" in i for i in issues)


# ── verify_r2_new_evidence 嵌套兼容 ───────────────────────────


def _r2_agent(new_evidence=None, evidence_exhausted=False):
    return AgentOutput(
        name="buffett", signal="bullish", conviction=80,
        core_thesis="看好", key_metrics=[], risks=[],
        what_would_change_my_mind="业绩下滑", out_of_circle=False,
        new_evidence=new_evidence or [], evidence_exhausted=evidence_exhausted,
    )


class TestR2NewEvidenceNested:
    def test_r2_cites_nested_peer_avg_pe_passes(self):
        """R2 new_evidence 引用「行业平均 PE 15.3」，dossier 嵌套有 → 通过无 warning."""
        agent = _r2_agent(new_evidence=["行业平均 PE 15.3"])
        ok, warnings = verify_r2_new_evidence(agent, _nested_dossier())
        assert ok is True
        assert warnings == []

    def test_r2_cites_nested_consensus_eps_passes(self):
        """R2 new_evidence 引用「研报 EPS 1.152」→ 通过无 warning."""
        agent = _r2_agent(new_evidence=["研报 EPS 1.152"])
        ok, warnings = verify_r2_new_evidence(agent, _nested_dossier())
        assert ok is True
        assert warnings == []

    def test_r2_fabricated_number_still_warns_with_nested(self):
        """嵌套 dossier 下，凭空数字仍 soft warning."""
        agent = _r2_agent(new_evidence=["ROE 99%"])
        ok, warnings = verify_r2_new_evidence(agent, _nested_dossier())
        assert ok is True  # soft 不拦截
        assert any("suspected_fabricated_evidence" in w for w in warnings)
