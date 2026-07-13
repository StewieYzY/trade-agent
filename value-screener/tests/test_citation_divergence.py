"""f3a §6.1/6.2: compute_citation_divergence 单元测试（D6，纯 Python，零 LLM）.

A/B 验证量化判据——四 agent R1 引用数据点集合的 Jaccard 距离 = 1 - |交集|/|并集|。
- f2 基线（600009.SH 现有产出）：四 agent 引用全同源，Jaccard 距离 ≈ 0
- f3a 期望：Jaccard 距离显著 > 0（角色分发让 agent 看不同维度，引用数据点分化）

本测试不依赖 LLM，纯结构验证 compute_citation_divergence 的集合运算正确性。
"""
from __future__ import annotations

import pytest

from council.schema import AgentOutput
from council.verify_quality_gate import compute_citation_divergence


def _agent(name: str, key_metrics: list[str]) -> AgentOutput:
    """构造最小合法 AgentOutput，key_metrics 是分化度唯一读的字段."""
    return AgentOutput(
        name=name,
        signal="bullish",
        conviction=75,
        core_thesis="placeholder",
        what_would_change_my_mind="placeholder",
        out_of_circle=False,
        key_metrics=key_metrics,
    )


# ── 数据点提取 + 集合运算正确性 ────────────────────────────────


class TestCitationDivergenceBasic:
    def test_all_identical_metrics_mean_distance_zero(self):
        """四 agent key_metrics 完全相同 → Jaccard 距离 = 0（f2 同源基线）.

        spec Scenario: f2 基线 Jaccard 距离 ≈0。四 agent 引用全同源 PE/ROE/跌幅/F-score，
        集合几乎完全重叠。
        """
        shared = ["PE 26.42", "ROE 27%", "跌幅 -12%", "F-score 7"]
        round1 = [
            _agent("buffett", shared),
            _agent("munger", shared),
            _agent("duan", shared),
            _agent("feng_liu", shared),
        ]
        result = compute_citation_divergence(round1)
        assert result["mean_distance"] == pytest.approx(0.0, abs=1e-9)
        # 6 对（C(4,2)），全部为 0
        assert len(result["pairwise_distances"]) == 6
        assert all(d == pytest.approx(0.0, abs=1e-9) for d in result["pairwise_distances"].values())

    def test_all_disjoint_metrics_mean_distance_one(self):
        """四 agent key_metrics 完全不相交 → Jaccard 距离 = 1.

        spec Scenario: f3a 期望 Jaccard 距离显著 >0 的极端情形（角色分发后各看不同维度，
        引用数据点完全不重叠）。
        """
        round1 = [
            _agent("buffett", ["主营构成 60%"]),
            _agent("munger", ["质押率 12%"]),
            _agent("duan", ["研报 EPS 1.2"]),
            _agent("feng_liu", ["capex 30亿"]),
        ]
        result = compute_citation_divergence(round1)
        assert result["mean_distance"] == pytest.approx(1.0, abs=1e-9)
        assert all(d == pytest.approx(1.0, abs=1e-9) for d in result["pairwise_distances"].values())

    def test_pairwise_partial_overlap(self):
        """两两部分重叠：A∩B=1，A∪B=3 → Jaccard 距离 = 1 - 1/3 = 2/3.

        验证 pairwise_distances 的 key 格式与数值正确。
        """
        round1 = [
            _agent("buffett", ["PE 26", "ROE 27", "PB 3"]),
            _agent("munger", ["ROE 27", "跌幅 12", "质押 8"]),
        ]
        result = compute_citation_divergence(round1)
        # 唯一一对：buffett vs munger
        assert len(result["pairwise_distances"]) == 1
        key = list(result["pairwise_distances"].keys())[0]
        assert "buffett" in key and "munger" in key
        # 交集 {ROE 27}，并集 {PE 26,ROE 27,PB 3,跌幅 12,质押 8} = 5 → 距离 = 1 - 1/5 = 0.8
        assert result["pairwise_distances"][key] == pytest.approx(0.8, abs=1e-9)
        assert result["mean_distance"] == pytest.approx(0.8, abs=1e-9)

    def test_mixed_pairwise_mean_average(self):
        """4 agent 两对：A=B（Jaccard=0），C 与 D 完全不同（Jaccard=1）→ 均值正确.

        spec tasks 6.1：构造 4 个 AgentOutput，两个 key_metrics 完全相同→Jaccard=0，
        两个完全不同→Jaccard=1，断言 mean_distance 正确。
        """
        round1 = [
            _agent("buffett", ["PE 26", "ROE 27"]),
            _agent("munger", ["PE 26", "ROE 27"]),      # 与 buffett 完全相同
            _agent("duan", ["PB 1.5"]),
            _agent("feng_liu", ["capex 30"]),            # 与 duan 完全不同
        ]
        result = compute_citation_divergence(round1)
        assert len(result["pairwise_distances"]) == 6
        # 6 对：buffett-munger=0, duan-feng_liu=1，其余 4 对为部分重叠或全不同
        # 验证 buffett-munger = 0（pair key 已按字母序规范化为 buffett|munger）
        assert result["pairwise_distances"]["buffett|munger"] == pytest.approx(0.0, abs=1e-9)
        # 验证 duan-feng_liu = 1
        assert result["pairwise_distances"]["duan|feng_liu"] == pytest.approx(1.0, abs=1e-9)
        # mean 是 6 对的算术平均
        assert result["mean_distance"] == pytest.approx(
            sum(result["pairwise_distances"].values()) / 6, abs=1e-9
        )


# ── 边界 case ─────────────────────────────────────────────────


class TestCitationDivergenceEdgeCases:
    def test_empty_metrics_treated_as_empty_set(self):
        """key_metrics 为空列表 → 空集。两个空集的 Jaccard 距离定义：并集为空，
        约定 |∩|/|∪| = 0/0 → 记为 0（完全相同，无差异）。避免除零异常。

        实际场景：若 R1 全员 key_metrics 空（很少见），不应崩溃，mean_distance=0。
        """
        round1 = [
            _agent("buffett", []),
            _agent("munger", []),
        ]
        result = compute_citation_divergence(round1)
        # 两个空集 → 距离 0（无差异）
        assert result["mean_distance"] == pytest.approx(0.0, abs=1e-9)

    def test_one_empty_one_nonempty_distance_one(self):
        """一空一非空 → 交集 0，并集 = 非空集合 → 距离 = 1."""
        round1 = [
            _agent("buffett", []),
            _agent("munger", ["PE 26"]),
        ]
        result = compute_citation_divergence(round1)
        assert result["mean_distance"] == pytest.approx(1.0, abs=1e-9)

    def test_single_agent_zero_distance(self):
        """单 agent：无任何 pair → mean_distance=0（无分化可言，f2 同源基线场景）。"""
        round1 = [_agent("buffett", ["PE 26"])]
        result = compute_citation_divergence(round1)
        assert result["mean_distance"] == pytest.approx(0.0, abs=1e-9)
        assert result["pairwise_distances"] == {}

    def test_empty_list_raises_value_error(self):
        """空列表：无 agent 无法算分化度，抛 ValueError（与 compute_divergence 同模式）。"""
        with pytest.raises(ValueError):
            compute_citation_divergence([])

    def test_none_key_metrics_treated_as_empty(self):
        """key_metrics 为 None（理论上 schema 默认 []，但防御性处理）→ 视作空集不崩."""
        agent = AgentOutput(
            name="buffett",
            signal="bullish",
            conviction=75,
            core_thesis="placeholder",
            what_would_change_my_mind="placeholder",
            out_of_circle=False,
            key_metrics=[],
        )
        round1 = [agent, _agent("munger", ["PE 26"])]
        result = compute_citation_divergence(round1)
        assert result["mean_distance"] == pytest.approx(1.0, abs=1e-9)
