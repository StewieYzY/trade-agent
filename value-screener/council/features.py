"""L3 特征组装（design.md 决策 1: 直接 import scout.input_assembly）.

复用 L2 的 assemble_snapshot，封装 L3 特有逻辑（预留 history_years 参数）。
"""
from __future__ import annotations

from scout.input_assembly import assemble_snapshot


def assemble_council_features(ticker: str, history_years: int = 3) -> dict:
    """组装 L3 天团深研所需的特征数据.

    Args:
        ticker: 股票代码（支持 600519 或 600519.SH 格式）
        history_years: 历史年数（预留参数，当前 L2 默认 3 年）

    Returns:
        features dict，或 {"error": "insufficient_data", "missing_fields": [...]}

    实现：直接复用 scout.input_assembly.assemble_snapshot，
    L3 特有逻辑（如更长历史）在此扩展。
    """
    # 标准化 ticker：移除后缀（如 .SH / .SZ），保留 6 位数字
    normalized_ticker = ticker.split(".")[0]

    features = assemble_snapshot(normalized_ticker)

    if "error" in features:
        return features

    # 预留：若 history_years != 3，可扩展字段
    # 当前 L2 assemble_snapshot 固定 3 年 ROE，
    # 未来可加参数透传或在 features 上补充。

    return features
