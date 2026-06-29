"""Anti-Trap Factors — 反价值陷阱扣分.

S3 规格：在 Factor Scores 基础上追加扣分

反陷阱因子（7 项扣分）：
- A1: ROE 3 年趋势下降 → 每降 1 年扣 2 分
- A2: 净利润正但经营现金流负 → 扣 10 分
- A3: 应收账款增速 > 营收增速 → 扣 5 分（MVP 跳过）
- A4: 商誉 / 净资产 > 30% → 扣 8 分
- A5: 大股东质押 > 60% → 扣 5 分
- A6: 非标审计意见 → 扣 15 分
- A7: 3 年内换过 CFO → 扣 0 分（MVP 跳过）

初始 100 分，各项扣分累加，最低 0 分。
"""

from __future__ import annotations


def _compute_roe_trend(financials: dict) -> tuple[float, int]:
    """计算 ROE 趋势（线性回归斜率）.

    Returns:
        (slope, decline_years): 斜率和下降年数
    """
    income = financials.get("income", {})
    balance_sheet = financials.get("balance_sheet", {})

    net_profits = income.get("net_profit", [])
    total_assets = balance_sheet.get("TOTAL_ASSETS", [])
    total_liabilities = balance_sheet.get("TOTAL_LIABILITIES", [])

    # 需要 4 年数据来计算 3 年间的下降趋势
    if len(net_profits) < 4 or len(total_assets) < 4 or len(total_liabilities) < 4:
        return 0.0, 0

    # 取最近 4 年数据
    net_profits = net_profits[-4:]
    total_assets = total_assets[-4:]
    total_liabilities = total_liabilities[-4:]

    # 计算 ROE 序列
    roe_list = []
    for i in range(len(net_profits)):
        ta = total_assets[i]
        tl = total_liabilities[i]
        if ta is None or tl is None or ta == 0:
            continue
        net_assets = ta - tl
        if net_assets <= 0:
            continue
        np = net_profits[i]
        if np is None:
            continue
        roe_list.append(np / net_assets)

    if len(roe_list) < 3:
        return 0.0, 0

    # 简单线性回归斜率（使用所有可用 ROE 数据）
    n = len(roe_list)
    x_mean = (n - 1) / 2.0
    y_mean = sum(roe_list) / n

    numerator = sum((i - x_mean) * (roe_list[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0, 0

    slope = numerator / denominator

    # 计算近 3 年间的下降年数（4 年数据有 3 个变化点）
    decline_years = 0
    for i in range(1, min(4, len(roe_list))):  # 最多检查 3 个变化点
        if roe_list[i] < roe_list[i - 1]:
            decline_years += 1

    return slope, decline_years


def compute_anti_trap(ticker_data: dict) -> dict:
    """计算反价值陷阱扣分.

    Args:
        ticker_data: {
            "financials": {...},
            "risk": {"pledge_ratio", "audit_opinion", ...}
        }

    Returns:
        {"score": float, "flags": [str]}
    """
    financials = ticker_data.get("financials", {})
    risk = ticker_data.get("risk", {})

    score = 100.0
    flags = []

    # A1: ROE 3 年趋势下降 → 每降 1 年扣 2 分
    slope, decline_years = _compute_roe_trend(financials)
    if slope < 0 and decline_years > 0:
        deduction = min(decline_years * 2, 10)  # 最多扣 10 分
        score -= deduction
        flags.append(f"A1_ROE_decline:{decline_years}y")

    # A2: 净利润正但经营现金流负 → 扣 10 分
    income = financials.get("income", {})
    cash_flow = financials.get("cash_flow", {})

    net_profits = income.get("net_profit", [])
    netcash_operate = cash_flow.get("NETCASH_OPERATE", [])

    if net_profits and netcash_operate:
        latest_np = net_profits[-1] if net_profits else None
        latest_cf = netcash_operate[-1] if netcash_operate else None

        if latest_np is not None and latest_cf is not None:
            if latest_np > 0 and latest_cf < 0:
                score -= 10
                flags.append("A2_profit_but_negative_cf")

    # A3: 应收账款增速 > 营收增速 → 扣 5 分（MVP 跳过）
    # 需要 accounts_receivable 数据，当前 L0 未采集

    # A4: 商誉/净资产 > 30% → 扣 8 分
    balance_sheet = financials.get("balance_sheet", {})
    goodwill = balance_sheet.get("GOODWILL")
    total_assets = balance_sheet.get("TOTAL_ASSETS", [])
    total_liabilities = balance_sheet.get("TOTAL_LIABILITIES", [])

    if goodwill and total_assets and total_liabilities:
        latest_ta = total_assets[-1] if total_assets else None
        latest_tl = total_liabilities[-1] if total_liabilities else None

        if latest_ta and latest_tl and latest_ta > latest_tl:
            net_assets = latest_ta - latest_tl
            if net_assets > 0:
                goodwill_ratio = goodwill / net_assets
                if goodwill_ratio > 0.3:
                    score -= 8
                    flags.append(f"A4_high_goodwill:{goodwill_ratio:.1%}")

    # A5: 大股东质押 > 60% → 扣 5 分
    pledge_ratio = risk.get("pledge_ratio")
    if pledge_ratio is not None and pledge_ratio > 60:
        score -= 5
        flags.append(f"A5_high_pledge:{pledge_ratio:.1f}%")

    # A6: 非标审计意见 → 扣 15 分
    audit_opinion = risk.get("audit_opinion")
    if audit_opinion and audit_opinion != "标准无保留意见":
        score -= 15
        flags.append(f"A6_non_standard_audit:{audit_opinion}")

    # A7: 3 年内换过 CFO → 扣 0 分（MVP 跳过）
    # 需要高管变动数据，当前 L0 未采集

    # 最低 0 分
    score = max(0.0, score)

    return {"score": round(score, 2), "flags": flags}
