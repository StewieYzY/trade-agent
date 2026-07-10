"""f2 §2 分歧度量化函数（D1，纯 Python，零 LLM）.

R1 完成后、R2 开始前，对 R1 的 AgentOutput 列表计算分歧度，决定后续轮次路径：
- low：signal 高度一致 + conviction 集中 → 跳 R2/R3 直接 R4（省 token）
- medium：中度分歧 → 正常跑 R2/R3
- high：signal 无多数派 → 正常跑 R2/R3，R4 标 divergence_level="high"
- extreme：signal 完全分散 → 跳 R2/R3，R4 输出 neutral + divergence_level="extreme"

不硬编码 agent 数（spec review #4）：signal_consensus 用「计数/总数」，
conviction_std 用 statistics.stdev 自然适配任意长度（当前 4，未来 5）。
"""
from __future__ import annotations

import statistics
from collections import Counter

from council.schema import AgentOutput


def compute_divergence(round1: list[AgentOutput]) -> dict:
    """计算 R1 分歧度，返回 {signal_consensus, conviction_std, level}.

    Args:
        round1: R1 各 agent 的 AgentOutput 列表（非空）

    Returns:
        dict 含三个 key：
        - signal_consensus: 多数 signal 占比（出现最多的 signal 计数/总数）
        - conviction_std: agent conviction 的标准差（单 agent 返回 0）
        - level: low / medium / high / extreme

    Raises:
        ValueError: round1 为空列表（上游 bug 应暴露，不静默返回 low 致误跳轮）
    """
    if not round1:
        raise ValueError("compute_divergence: empty round1 list")

    n = len(round1)

    # signal_consensus：出现最多的 signal 计数 / 总数
    signal_counts = Counter(a.signal for a in round1)
    max_signal_count = max(signal_counts.values())
    signal_consensus = max_signal_count / n

    # conviction_std：单 agent 返回 0（statistics.stdev 对单元素抛 StatisticsError）
    if n < 2:
        conviction_std = 0.0
    else:
        conviction_std = statistics.stdev(a.conviction for a in round1)

    # level 映射（判断顺序：extreme → low → high → medium）
    # extreme：signal 完全分散（多 agent 且每个 signal 出现次数 ≤1，无任何重复）
    #   单 agent 时 max_count=1 但属「全员一致」非 extreme，故要求 n>1
    if n > 1 and max_signal_count <= 1:
        level = "extreme"
    # low：signal 高度一致 + conviction 集中
    elif signal_consensus >= 0.8 and conviction_std < 10:
        level = "low"
    # high：signal 无多数派（consensus < 0.6，但有重复故非 extreme，如 2:2）
    elif signal_consensus < 0.6:
        level = "high"
    # medium：中度分歧（consensus 0.6-0.8，或 std 10-20 区间）
    else:
        level = "medium"

    return {
        "signal_consensus": signal_consensus,
        "conviction_std": conviction_std,
        "level": level,
    }
