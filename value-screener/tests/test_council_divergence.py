"""f2 §2 分歧度量化函数 compute_divergence 单元测试（D1，纯 Python，零 LLM）.

覆盖 D1 阈值映射：
- low：signal_consensus ≥ 0.8 且 conviction_std < 10
- medium：signal_consensus ≥ 0.6 或 conviction_std 10-20
- high：signal 无多数派（2:2 或 2:1:1）
- extreme：signal 完全分散（每个 signal 出现次数 ≤1）

不硬编码 agent 数（spec review #4）：signal_consensus 用「计数/总数」，
conviction_std 用 statistics.stdev 自然适配任意长度。
"""
from __future__ import annotations

import pytest

from council.schema import AgentOutput
from council.divergence import compute_divergence


# ── 构造 helper：省去每个 case 写满必填字段 ───────────────────

def _agent(name: str, signal: str, conviction: int) -> AgentOutput:
    """构造最小合法 AgentOutput，conviction/signal 是分歧度唯一读的字段."""
    return AgentOutput(
        name=name,
        signal=signal,
        conviction=conviction,
        core_thesis="placeholder",
        what_would_change_my_mind="placeholder",
        out_of_circle=False,
    )


# ── D1 四级 level 映射 ────────────────────────────────────────

class TestDivergenceLevel:
    def test_all_bullish_low_std_is_low(self):
        """全员 bullish + std<10 → low（跳 R2/R3）."""
        round1 = [
            _agent("buffett", "bullish", 80),
            _agent("munger", "bullish", 82),
            _agent("duan", "bullish", 78),
            _agent("feng_liu", "bullish", 81),
        ]
        result = compute_divergence(round1)
        assert result["level"] == "low"
        assert result["signal_consensus"] == 1.0
        # std of [80,82,78,81] ≈ 1.708
        assert result["conviction_std"] == pytest.approx(1.708, abs=0.01)

    def test_3_bullish_1_neutral_std15_is_medium(self):
        """3 bullish + 1 neutral → medium（signal_consensus=0.75<0.8，
        但 ≥0.6，走 medium 分支）. conviction_std=stdev([80,80,80,65])=7.5."""
        round1 = [
            _agent("buffett", "bullish", 80),
            _agent("munger", "bullish", 80),
            _agent("duan", "bullish", 80),
            _agent("feng_liu", "neutral", 65),
        ]
        result = compute_divergence(round1)
        assert result["level"] == "medium"
        assert result["signal_consensus"] == 0.75
        assert result["conviction_std"] == pytest.approx(
            7.5, abs=0.01
        )  # stdev (样本，n-1) of [80,80,80,65]

    def test_2_bullish_2_bearish_is_high(self):
        """2 bullish + 2 bearish → high（signal 无多数派，2:2 平分）."""
        round1 = [
            _agent("buffett", "bullish", 80),
            _agent("munger", "bullish", 75),
            _agent("duan", "bearish", 30),
            _agent("feng_liu", "bearish", 35),
        ]
        result = compute_divergence(round1)
        assert result["level"] == "high"
        assert result["signal_consensus"] == 0.5  # 2/4
        assert result["conviction_std"] == pytest.approx(
            26.14, abs=0.01
        )  # stdev (样本) of [80,75,30,35]

    def test_all_different_is_extreme(self):
        """1 bullish + 1 bearish + 1 neutral + 1 skip → extreme
        （每个 signal 出现次数都 ≤1，完全分散，跳 R2/R3）."""
        round1 = [
            _agent("buffett", "bullish", 80),
            _agent("munger", "bearish", 30),
            _agent("duan", "neutral", 50),
            _agent("feng_liu", "skip", 10),
        ]
        result = compute_divergence(round1)
        assert result["level"] == "extreme"
        assert result["signal_consensus"] == 0.25  # 1/4
        assert result["conviction_std"] == pytest.approx(
            29.86, abs=0.01
        )  # stdev (样本) of [80,30,50,10]


# ── 边界 case（Task 2.3）─────────────────────────────────────

class TestDivergenceEdgeCases:
    def test_single_agent_returns_std_zero(self):
        """单 agent 列表：conviction_std 返回 0（statistics.stdev 对单元素
        会抛 statistics.StatisticsError，需特殊处理），level 应为 low
        （signal_consensus=1.0 且 std=0<10）."""
        round1 = [_agent("buffett", "bullish", 80)]
        result = compute_divergence(round1)
        assert result["conviction_std"] == 0
        assert result["signal_consensus"] == 1.0
        assert result["level"] == "low"

    def test_empty_list_raises_value_error(self):
        """空列表：无 agent 无法计算分歧度，抛 ValueError（合理 fail-fast，
        调用方 debate.py 在 R1 后调用时 round1 不会为空——若为空是上游 bug，
        应暴露而非静默返回 low 导致后续逻辑误跳轮）."""
        with pytest.raises(ValueError, match="empty"):
            compute_divergence([])

    def test_all_conviction_equal_std_zero(self):
        """conviction 全相同 → std=0，若 signal 也全一致 → low."""
        round1 = [
            _agent("buffett", "bullish", 75),
            _agent("munger", "bullish", 75),
            _agent("duan", "bullish", 75),
            _agent("feng_liu", "bullish", 75),
        ]
        result = compute_divergence(round1)
        assert result["conviction_std"] == 0
        assert result["signal_consensus"] == 1.0
        assert result["level"] == "low"

    def test_all_skip_signal(self):
        """4 个 skip → signal_consensus=1.0，level 取决于 std。
        全 skip 意味全员放弃判断，std 若 <10 → low（跳 R2/R3 合理，
        无东西可辩）."""
        round1 = [
            _agent("buffett", "skip", 10),
            _agent("munger", "skip", 10),
            _agent("duan", "skip", 10),
            _agent("feng_liu", "skip", 10),
        ]
        result = compute_divergence(round1)
        assert result["signal_consensus"] == 1.0
        assert result["conviction_std"] == 0
        assert result["level"] == "low"
