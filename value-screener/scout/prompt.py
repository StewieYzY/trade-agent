"""Scout System Prompt & 特征快照格式化（design.md §2, tasks 1.2-1.3）.

Scout 是 L2 成本闸门，用轻量 LLM 将 ~200 只 L1 候选压缩至 ~20 只 deep_dive。
设计参考：design.md §2 (Scout Prompt 设计) + total-design §5.2。

System Prompt 固定 5 问 + JSON schema 输出；User Message 为 ~200 tokens 特征快照，
由 input_assembly.assemble_snapshot 产出 features dict 后经 format_snapshot 渲染。
"""
from __future__ import annotations

SCOUT_SYSTEM_PROMPT = """你是 A 股价值投资初筛分析师。请用 3-5 句话回答：

1. 这是一家什么生意？（一句话）
2. 便宜吗？（PE/PB 分位 + 同行对比）
3. 生意好吗？（ROE 趋势 + 现金流质量）
4. 有什么明显的红旗？（负债/质押/商誉/大股东减持）
5. 一句话结论：值得深研 / 观望 / 排除

输出 JSON:
{
  "verdict": "deep_dive|watch|skip",
  "confidence": 0-100,
  "one_liner": "...",
  "red_flags": [...],
  "green_flags": [...],
  "anti_trap_flags": [...]
}

约束：
- red_flags / green_flags / anti_trap_flags 中每条必须引用具体数据（数字或百分比）
- verdict 三选一：deep_dive（值得深研）/ watch（观望）/ skip（排除）
- confidence 为 0-100 整数，反映你对判断的把握程度
- one_liner 不超过 50 字
"""


def _fmt(value, suffix: str = "", missing: str = "数据缺失") -> str:
    """单字段格式化：None → '数据缺失'，否则 value+suffix."""
    if value is None:
        return missing
    if isinstance(value, float):
        # 保留 2 位小数，去除尾部 0
        if value == int(value):
            return f"{int(value)}{suffix}"
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def format_snapshot(features: dict) -> str:
    """将 features dict 渲染为 ~200 tokens 的 User Message 文本（design.md §2）。

    features 字段来源见 input_assembly.assemble_snapshot 文档。
    趋势标注（如 '← 趋势下降'）由 input_assembly 在组装时预计算，本函数只做渲染。

    Args:
        features: assemble_snapshot 返回的特征 dict（已含趋势标注字段
            roe_trend / cashflow_match / revenue_growth 等）

    Returns:
        渲染后的 user message 文本
    """
    # 括号内趋势标注：已预计算在 features 中（input_assembly 负责）
    roe_trend = features.get("roe_trend")
    cashflow_match = features.get("cashflow_match")

    def pct(v):
        return _fmt(v, "%")

    def yi(v):
        return _fmt(v, "亿")

    def val(v):
        return _fmt(v)

    lines = [
        f"股票: {_fmt(features.get('name'))} ({_fmt(features.get('ticker'))})",
        f"行业: {_fmt(features.get('industry'))}",
        f"市值: {yi(features.get('market_cap'))}",
        f"PE(TTM): {val(features.get('pe_ttm'))} (5年分位: {pct(features.get('pe_percentile_5y'))})",
        f"PB: {val(features.get('pb'))}",
        f"ROE(近3年): {_fmt(features.get('roe_3y'))}  ← {_fmt(roe_trend, missing='数据缺失')}",
        f"净利率: {pct(features.get('net_margin'))}",
        f"负债率: {pct(features.get('debt_ratio'))}",
        f"经营现金流: {yi(features.get('operating_cashflow'))} (净利润 {yi(features.get('net_profit'))}) ← {_fmt(cashflow_match, missing='数据缺失')}",
        f"营收增速: {pct(features.get('revenue_growth'))}",
        f"商誉/净资产: {pct(features.get('goodwill_ratio'))}",
        f"大股东质押: {pct(features.get('pledge_ratio'))}",
        f"近60日涨幅: {pct(features.get('price_change_60d'))}",
        f"换手率分位: {pct(features.get('turnover_percentile'))}",
        f"F-Score: {_fmt(features.get('f_score'))}/9",
    ]
    return "\n".join(lines)
