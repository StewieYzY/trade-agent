"""Heat Filter — 低热度排除（防御性排除）.

S4 规格：~300 → ~200

低热度条件：
- HF1: 换手率分位 > 70% → 排除（剔被炒的，当前换手率处于 60 日历史高位）
- HF2: 近 60 日涨幅 > 20% → 排除（剔刚炒完的）

注意：低热度是排除维度，不是反转因子（AD-02 约束）
"""

from __future__ import annotations


def check_heat_filter(ticker_data: dict) -> dict:
    """检查单只股票是否通过低热度排除.

    Args:
        ticker_data: {
            "kline": {"turnover_rate": [...], "close": [...]}
        }

    Returns:
        {"pass": bool, "failed_filters": [str]}
    """
    kline = ticker_data.get("kline", {})

    # 数据缺失容错
    if not kline:
        return {"pass": True, "failed_filters": []}

    turnover_rate = kline.get("turnover_rate", [])
    close = kline.get("close", [])

    # 数据不足容错（需要至少 60 日数据）
    if len(turnover_rate) < 60 or len(close) < 60:
        return {"pass": True, "failed_filters": []}

    failed_filters = []

    # HF1: 换手率分位 > 70% → 排除（剔被炒的）
    # 计算近 60 日换手率的分位数
    recent_turnover = turnover_rate[-60:]
    current_turnover = recent_turnover[-1]

    # 计算当前换手率在 60 日中的分位数（0-100%）
    count_below = sum(1 for t in recent_turnover[:-1] if t < current_turnover)
    percentile = (count_below / (len(recent_turnover) - 1)) * 100

    if percentile > 70:
        failed_filters.append("HF1")

    # HF2: 近 60 日涨幅 > 20% → 排除（剔刚炒完的）
    close_60d_ago = close[-60]
    close_current = close[-1]

    if close_60d_ago > 0:
        gain_60d = (close_current - close_60d_ago) / close_60d_ago * 100

        if gain_60d > 20:
            failed_filters.append("HF2")

    return {"pass": len(failed_filters) == 0, "failed_filters": failed_filters}
