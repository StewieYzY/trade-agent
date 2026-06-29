"""L1→L2 数据交接（design.md §1 决策 1, tasks 1.4-1.7）.

从 L0 CacheManager 取全维度原始数据，组装为 ~200 tokens 特征快照。
派生指标（ROE/净利率/负债率/商誉比）从 financials 计算，复用 data/lib/fin_models 口径。

字段归属（design.md §1 决策 1）：
- pe_ttm 从 valuation dim 取（key: pe_ttm），不从 basic 取（key: pe）
- ROE 用近 3 年（非 5 年，与 L1 factor_scores 区分）
- dividend_yield / receivables_growth 不在快照中（L0 无该字段）

Insufficient data guard（spec Requirement: Insufficient data guard）：
- 关键字段（name/industry/market_cap）任一缺失 → 跳过 LLM 调用
- 整体缺失 >50% 字段 → 跳过 LLM 调用
"""
from __future__ import annotations

from data.cache.manager import CacheManager


def _compute_roe_3y(financials: dict) -> tuple[list[float] | None, str]:
    """计算近 3 年 ROE 序列 + 趋势标注.

    ROE = net_profit / (TOTAL_ASSETS - TOTAL_CURRENT_LIAB - TOTAL_NONCURRENT_LIAB)

    Returns:
        (roe_list, trend_annotation)
        trend_annotation: '趋势上升' / '趋势下降' / '趋势平稳' / '数据缺失'
    """
    if not financials:
        return None, "数据缺失"

    income = financials.get("income", {})
    balance_sheet = financials.get("balance_sheet", {})

    net_profits = income.get("net_profit", [])
    total_assets = balance_sheet.get("TOTAL_ASSETS", [])
    total_current_liab = balance_sheet.get("TOTAL_CURRENT_LIAB", [])
    total_noncurrent_liab = balance_sheet.get("TOTAL_NONCURRENT_LIAB", [])

    if not (net_profits and total_assets and total_current_liab and total_noncurrent_liab):
        return None, "数据缺失"
    if not (len(net_profits) == len(total_assets) == len(total_current_liab) == len(total_noncurrent_liab)):
        return None, "数据缺失"

    roe_list = []
    for np_val, ta, tcl, tncl in zip(net_profits, total_assets, total_current_liab, total_noncurrent_liab):
        if np_val is None or ta is None or tcl is None or tncl is None:
            continue
        equity = ta - tcl - tncl
        if equity <= 0:
            continue
        roe_list.append(np_val / equity * 100)  # 转为百分比

    if not roe_list:
        return None, "数据缺失"

    # 取近 3 年
    roe_3y = roe_list[-3:] if len(roe_list) >= 3 else roe_list

    # 趋势标注
    if len(roe_3y) < 2:
        trend = "数据不足"
    else:
        # 简单判断：最后一年 vs 第一年
        if roe_3y[-1] > roe_3y[0] * 1.1:
            trend = "趋势上升"
        elif roe_3y[-1] < roe_3y[0] * 0.9:
            trend = "趋势下降"
        else:
            trend = "趋势平稳"

    return roe_3y, trend


def _compute_net_margin(financials: dict) -> float | None:
    """净利率 = net_profit / revenue * 100."""
    if not financials:
        return None
    income = financials.get("income", {})
    net_profits = income.get("net_profit", [])
    revenues = income.get("revenue", [])

    if not net_profits or not revenues:
        return None
    latest_np = net_profits[-1]
    latest_rev = revenues[-1]

    if latest_np is None or latest_rev is None or latest_rev == 0:
        return None
    return latest_np / latest_rev * 100


def _compute_debt_ratio(financials: dict) -> float | None:
    """负债率 = (TOTAL_CURRENT_LIAB + TOTAL_NONCURRENT_LIAB) / TOTAL_ASSETS * 100."""
    if not financials:
        return None
    balance_sheet = financials.get("balance_sheet", {})

    total_assets = balance_sheet.get("TOTAL_ASSETS", [])
    total_current_liab = balance_sheet.get("TOTAL_CURRENT_LIAB", [])
    total_noncurrent_liab = balance_sheet.get("TOTAL_NONCURRENT_LIAB", [])

    if not (total_assets and total_current_liab and total_noncurrent_liab):
        return None

    ta = total_assets[-1]
    tcl = total_current_liab[-1]
    tncl = total_noncurrent_liab[-1]

    if ta is None or tcl is None or tncl is None or ta == 0:
        return None
    return (tcl + tncl) / ta * 100


def _compute_goodwill_ratio(financials: dict) -> float | None:
    """商誉/净资产 = GOODWILL / (TOTAL_ASSETS - TOTAL_CURRENT_LIAB - TOTAL_NONCURRENT_LIAB) * 100."""
    if not financials:
        return None
    balance_sheet = financials.get("balance_sheet", {})

    goodwill_list = balance_sheet.get("GOODWILL", [])
    total_assets = balance_sheet.get("TOTAL_ASSETS", [])
    total_current_liab = balance_sheet.get("TOTAL_CURRENT_LIAB", [])
    total_noncurrent_liab = balance_sheet.get("TOTAL_NONCURRENT_LIAB", [])

    if not (goodwill_list and total_assets and total_current_liab and total_noncurrent_liab):
        return None

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
                return gw / equity * 100

    return None


def _annotate_cashflow_match(operating_cashflow: float | None, net_profit: float | None) -> str:
    """现金流匹配标注：经营现金流 vs 净利润.

    Returns:
        '匹配' / '不匹配' / '数据缺失'
    """
    if operating_cashflow is None or net_profit is None:
        return "数据缺失"

    # 净利润正但经营现金流负 → 不匹配（anti_trap A2）
    if net_profit > 0 and operating_cashflow < 0:
        return "不匹配（利润正但现金流负）"

    # 经营现金流 > 净利润 → 匹配（现金流质量高）
    if operating_cashflow > net_profit * 0.8:  # 容差 20%
        return "匹配"

    return "部分匹配"


def _compute_price_change_60d(kline: dict) -> float | None:
    """近 60 日涨幅 = (close[-1] / close[-60] - 1) * 100."""
    if not kline:
        return None
    close = kline.get("close", [])
    if not close or len(close) < 60:
        return None

    latest = close[-1]
    past = close[-60]

    if latest is None or past is None or past == 0:
        return None
    return (latest / past - 1) * 100


def _compute_turnover_percentile(kline: dict) -> float | None:
    """换手率分位：近 60 日换手率在 250 日历史中的分位.

    Returns:
        0-100 分位值
    """
    if not kline:
        return None
    turnover_rate = kline.get("turnover_rate", [])
    if not turnover_rate or len(turnover_rate) < 60:
        return None

    # 取近 250 日（或全部可用）
    recent_250 = turnover_rate[-250:] if len(turnover_rate) >= 250 else turnover_rate
    recent_60 = turnover_rate[-60:]

    # 计算近 60 日均值
    valid_60 = [v for v in recent_60 if v is not None]
    if not valid_60:
        return None
    avg_60 = sum(valid_60) / len(valid_60)

    # 在 250 日序列中算分位
    valid_250 = [v for v in recent_250 if v is not None]
    if not valid_250:
        return None

    below = sum(1 for v in valid_250 if v <= avg_60)
    return below / len(valid_250) * 100


def _compute_revenue_growth(financials: dict) -> float | None:
    """营收增速 = (revenue[-1] / revenue[-2] - 1) * 100."""
    if not financials:
        return None
    income = financials.get("income", {})
    revenues = income.get("revenue", [])

    if not revenues or len(revenues) < 2:
        return None

    latest = revenues[-1]
    prev = revenues[-2]

    if latest is None or prev is None or prev == 0:
        return None
    return (latest / prev - 1) * 100


def assemble_snapshot(ticker: str, cache_manager: CacheManager | None = None) -> dict:
    """从 L0 CacheManager 取全维度数据，组装为特征快照 dict.

    Args:
        ticker: 股票代码（6 位）
        cache_manager: CacheManager 实例（缺省用默认路径）

    Returns:
        features dict（含所有字段 + 趋势标注），或
        {"error": "insufficient_data", "missing_fields": [...]} 若数据不足

    字段来源：
    - basic: name, industry, market_cap
    - valuation: pe_ttm, pb, pe_percentile_5y
    - financials: roe_3y, net_margin, debt_ratio, goodwill_ratio, operating_cashflow, net_profit, revenue_growth
    - kline: price_change_60d, turnover_percentile
    - risk: pledge_ratio, audit_opinion
    - F-Score: 从 data.lib.stock_features.compute_f_score 计算
    """
    if cache_manager is None:
        cache_manager = CacheManager()

    # 取全维度数据
    basic = cache_manager.get(ticker, "basic") or {}
    valuation = cache_manager.get(ticker, "valuation") or {}
    financials = cache_manager.get(ticker, "financials") or {}
    kline = cache_manager.get(ticker, "kline") or {}
    risk = cache_manager.get(ticker, "risk") or {}

    # 提取字段
    name = basic.get("name")
    industry = basic.get("industry")
    market_cap = basic.get("market_cap")
    if market_cap is not None:
        market_cap = market_cap / 1e8  # 转为亿

    pe_ttm = valuation.get("pe_ttm")
    pb = valuation.get("pb")
    pe_percentile_5y = valuation.get("pe_percentile_5y")

    roe_3y, roe_trend = _compute_roe_3y(financials)
    net_margin = _compute_net_margin(financials)
    debt_ratio = _compute_debt_ratio(financials)
    goodwill_ratio = _compute_goodwill_ratio(financials)

    income = financials.get("income", {})
    net_profits = income.get("net_profit", [])
    cash_flow = financials.get("cash_flow", {})
    netcash_operate = cash_flow.get("NETCASH_OPERATE", [])

    net_profit = net_profits[-1] if net_profits else None
    operating_cashflow = netcash_operate[-1] if netcash_operate else None
    if operating_cashflow is not None:
        operating_cashflow = operating_cashflow / 1e8  # 转为亿
    if net_profit is not None:
        net_profit = net_profit / 1e8  # 转为亿

    cashflow_match = _annotate_cashflow_match(operating_cashflow, net_profit)
    revenue_growth = _compute_revenue_growth(financials)

    pledge_ratio = risk.get("pledge_ratio")
    audit_opinion = risk.get("audit_opinion")

    price_change_60d = _compute_price_change_60d(kline)
    turnover_percentile = _compute_turnover_percentile(kline)

    # F-Score
    f_score = None
    if financials:
        from data.lib.stock_features import compute_f_score
        try:
            f_score = compute_f_score(financials)
        except (KeyError, ValueError, AttributeError):
            f_score = None

    features = {
        "ticker": ticker,
        "name": name,
        "industry": industry,
        "market_cap": market_cap,
        "pe_ttm": pe_ttm,
        "pb": pb,
        "pe_percentile_5y": pe_percentile_5y,
        "roe_3y": roe_3y,
        "roe_trend": roe_trend,
        "net_margin": net_margin,
        "debt_ratio": debt_ratio,
        "goodwill_ratio": goodwill_ratio,
        "operating_cashflow": operating_cashflow,
        "net_profit": net_profit,
        "cashflow_match": cashflow_match,
        "revenue_growth": revenue_growth,
        "pledge_ratio": pledge_ratio,
        "audit_opinion": audit_opinion,
        "price_change_60d": price_change_60d,
        "turnover_percentile": turnover_percentile,
        "f_score": f_score,
    }

    # Insufficient data guard
    critical_fields = ["name", "industry", "market_cap"]
    missing_critical = [f for f in critical_fields if features.get(f) is None]

    # 统计整体缺失（排除 ticker 和趋势标注字段）
    data_fields = [
        "name", "industry", "market_cap", "pe_ttm", "pb", "pe_percentile_5y",
        "roe_3y", "net_margin", "debt_ratio", "goodwill_ratio",
        "operating_cashflow", "net_profit", "revenue_growth",
        "pledge_ratio", "price_change_60d", "turnover_percentile", "f_score",
    ]
    missing_fields = [f for f in data_fields if features.get(f) is None]
    missing_ratio = len(missing_fields) / len(data_fields) if data_fields else 0

    if missing_critical or missing_ratio > 0.5:
        return {"error": "insufficient_data", "missing_fields": missing_fields}

    return features
