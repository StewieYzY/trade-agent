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
    total_current_liab = balance_sheet.get("TOTAL_CURRENT_LIAB", [])
    total_noncurrent_liab = balance_sheet.get("TOTAL_NONCURRENT_LIAB", [])

    # 检查数据完整性：所有序列长度应一致
    if not (net_profits and total_assets and total_current_liab and total_noncurrent_liab):
        return 0.0, 0
    if not (len(net_profits) == len(total_assets) == len(total_current_liab) == len(total_noncurrent_liab)):
        return 0.0, 0
    if len(net_profits) < 3:
        return 0.0, 0

    # 计算每年的 ROE = net_profit / (TOTAL_ASSETS - TOTAL_CURRENT_LIAB - TOTAL_NONCURRENT_LIAB)
    roe_list = []
    for np_val, ta, tcl, tncl in zip(net_profits, total_assets, total_current_liab, total_noncurrent_liab):
        if np_val is None or ta is None or tcl is None or tncl is None:
            continue
        equity = ta - tcl - tncl
        if equity <= 0:
            continue
        roe_list.append(np_val / equity)

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

    # 计算近 3 年间的下降年数
    decline_years = 0
    for i in range(1, len(roe_list)):
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
    goodwill_list = balance_sheet.get("GOODWILL", [])
    total_assets = balance_sheet.get("TOTAL_ASSETS", [])
    total_current_liab = balance_sheet.get("TOTAL_CURRENT_LIAB", [])
    total_noncurrent_liab = balance_sheet.get("TOTAL_NONCURRENT_LIAB", [])

    # GOODWILL 是多期 list（不是单个值），需逐期找最新有效的
    if goodwill_list and total_assets and total_current_liab and total_noncurrent_liab:
        latest_goodwill = None
        latest_net_assets = None

        # 从最新一期往回找，取第一个所有字段都有效的
        for i in range(len(goodwill_list) - 1, -1, -1):
            if i >= len(total_assets) or i >= len(total_current_liab) or i >= len(total_noncurrent_liab):
                continue
            gw = goodwill_list[i]
            ta = total_assets[i]
            tcl = total_current_liab[i]
            tncl = total_noncurrent_liab[i]

            if gw is not None and ta is not None and tcl is not None and tncl is not None:
                equity = ta - tcl - tncl
                if equity > 0:
                    latest_goodwill = gw
                    latest_net_assets = equity
                    break

        if latest_goodwill is not None and latest_net_assets is not None:
            goodwill_ratio = latest_goodwill / latest_net_assets
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
