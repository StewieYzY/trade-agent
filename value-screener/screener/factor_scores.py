"""Factor Scores — 三因子打分（价值/质量/安全边际）.

S2 规格：~800 → ~300

综合分公式：
  composite = quality × 0.50 + value × 0.30 + safety_margin × 0.20

质量因子（50%）：
- F-Score (40%)
- ROE 5 年平均 (30%)
- 经营现金流连续 3 年正 (30%)

估值因子（30%）：
- PE 分位 (40%)
- PB < 2 (30%)
- PE×PB < 22.5 (30%)

安全边际（20%）：
- DCF 安全边际: non-decision（量纲未验证，不参与排序）
- 质押率反向 (100%): < 20% 得满分，20-60% 线性衰减，> 60% 得 0
"""

from __future__ import annotations

from data.lib.stock_features import compute_f_score
from data.lib.fin_models import compute_simple_dcf


def _score_linear_decay(value: float, low: float, high: float, invert: bool = False) -> float:
    """线性衰减评分.

    Args:
        value: 输入值
        low: 低阈值（得满分或 0 分）
        high: 高阈值（得 0 分或满分）
        invert: 是否反转（True: value < low 得 0，value > high 得满分）

    Returns:
        0-100 分数
    """
    if value is None:
        return 0.0

    if not invert:
        # 正常：value < low 得满分，value > high 得 0
        if value <= low:
            return 100.0
        elif value >= high:
            return 0.0
        else:
            return (high - value) / (high - low) * 100.0
    else:
        # 反转：value < low 得 0，value > high 得满分
        if value <= low:
            return 0.0
        elif value >= high:
            return 100.0
        else:
            return (value - low) / (high - low) * 100.0


def _compute_quality_score(ticker_data: dict) -> float:
    """计算质量因子（50% 权重）.

    子项：
    - F-Score (40%): 0-9 → 0-100
    - ROE 5 年平均 (30%): > 15% 得满分
    - 经营现金流连续 3 年正 (30%): 3 年都正得满分
    """
    financials = ticker_data.get("financials", {})

    scores = []

    # 子项 1: F-Score (40%)
    # 检查 financials 是否有有效数据，空数据不应参与加权
    if financials and (financials.get("income", {}).get("net_profit")
                       or financials.get("balance_sheet", {}).get("TOTAL_ASSETS")
                       or financials.get("cash_flow", {}).get("NETCASH_OPERATE")):
        f_score = compute_f_score(financials)
        f_score_norm = f_score / 9.0 * 100.0
        scores.append(("f_score", f_score_norm, 0.40))

    # 子项 2: ROE 5 年平均 (30%)
    # ROE = net_profit / equity = net_profit / (TOTAL_ASSETS - TOTAL_CURRENT_LIAB - TOTAL_NONCURRENT_LIAB)
    income = financials.get("income", {})
    balance_sheet = financials.get("balance_sheet", {})

    net_profits = income.get("net_profit", [])
    total_assets = balance_sheet.get("TOTAL_ASSETS", [])
    total_current_liab = balance_sheet.get("TOTAL_CURRENT_LIAB", [])
    total_noncurrent_liab = balance_sheet.get("TOTAL_NONCURRENT_LIAB", [])

    if (net_profits and total_assets
            and len(net_profits) == len(total_assets)
            and len(total_assets) == len(total_current_liab)
            and len(total_assets) == len(total_noncurrent_liab)):
        roe_list = []
        for np_val, ta, tcl, tncl in zip(net_profits, total_assets, total_current_liab, total_noncurrent_liab):
            if np_val is None or ta is None or tcl is None or tncl is None:
                continue
            equity = ta - tcl - tncl
            if equity <= 0:
                continue
            roe_list.append(np_val / equity)

        if roe_list:
            # 取最近 5 年或所有可用年份
            roe_recent = roe_list[-5:] if len(roe_list) >= 5 else roe_list
            roe_avg = sum(roe_recent) / len(roe_recent)

            # ROE > 15% 得满分，线性插值到 0%
            roe_score = min(100.0, roe_avg / 0.15 * 100.0)
            scores.append(("roe_avg", roe_score, 0.30))

    # 子项 3: 经营现金流连续 3 年正 (30%)
    cash_flow = financials.get("cash_flow", {})
    ocf_list = cash_flow.get("NETCASH_OPERATE", [])

    if ocf_list and len(ocf_list) >= 3:
        ocf_recent = ocf_list[-3:]
        positive_count = sum(1 for ocf in ocf_recent if ocf is not None and ocf > 0)

        # 3 年都正得满分，按比例衰减
        cash_flow_score = positive_count / 3.0 * 100.0
        scores.append(("cash_flow", cash_flow_score, 0.30))

    if not scores:
        return 0.0

    # 加权求和（仅对有数据的子项）
    total_weight = sum(w for _, _, w in scores)
    if total_weight == 0:
        return 0.0

    return sum(s * w / total_weight for _, s, w in scores)


def _compute_value_score(ticker_data: dict, industry_pe_map: dict | None = None) -> float:
    """计算估值因子（30% 权重）.

    子项：
    - PE 行业折价 (40%): ratio = pe_ttm / industry_median_pe
        * ratio < 0.7 得满分
        * 0.7 <= ratio < 1.0 线性衰减
        * ratio >= 1.0 得 0 分
    - PB < 2 (30%): PB < 2 得满分，2-3 线性衰减，> 3 得 0
    - PE×PB < 22.5 (30%): PE×PB < 22.5 得满分，22.5-30 线性衰减
    """
    valuation = ticker_data.get("valuation", {})
    basic = ticker_data.get("basic", {})

    scores = []

    # 子项 1: PE 行业折价 (40%)
    pe_ttm = valuation.get("pe_ttm") or basic.get("pe")
    industry = basic.get("industry")

    # 尝试行业折价（主信号）
    industry_ratio_used = False
    if (industry_pe_map is not None
            and industry is not None
            and industry in industry_pe_map
            and pe_ttm is not None
            and pe_ttm > 0):
        industry_median_pe = industry_pe_map[industry]
        if industry_median_pe > 0:
            ratio = pe_ttm / industry_median_pe
            pe_score = _score_linear_decay(ratio, 0.7, 1.0, invert=False)
            scores.append(("pe_industry_ratio", pe_score, 0.40))
            industry_ratio_used = True

    # 降级到历史分位（兜底信号）
    if not industry_ratio_used:
        pe_percentile = valuation.get("pe_percentile_5y")
        if pe_percentile is not None:
            pe_score = _score_linear_decay(pe_percentile, 30.0, 70.0, invert=False)
            scores.append(("pe_percentile", pe_score, 0.40))

    # 子项 2: PB < 2 (30%)
    pb = valuation.get("pb") or basic.get("pb")
    if pb is not None:
        pb_score = _score_linear_decay(pb, 2.0, 3.0, invert=False)
        scores.append(("pb", pb_score, 0.30))

    # 子项 3: PE×PB < 22.5 (30%)
    pe = valuation.get("pe_ttm") or basic.get("pe")
    if pe is not None and pb is not None:
        pe_pb = pe * pb
        pe_pb_score = _score_linear_decay(pe_pb, 22.5, 30.0, invert=False)
        scores.append(("pe_pb", pe_pb_score, 0.30))

    if not scores:
        return 0.0

    total_weight = sum(w for _, _, w in scores)
    if total_weight == 0:
        return 0.0

    return sum(s * w / total_weight for _, s, w in scores)


def _compute_safety_margin_score(ticker_data: dict) -> tuple[float, str | None]:
    """计算安全边际因子（20% 权重）.

    子项：
    - DCF 安全边际: non-decision（量纲未验证，不参与排序）
    - 质押率反向 (100%): < 20% 得满分，20-60% 线性衰减，> 60% 得 0

    Returns:
        (score, dcf_note): 安全边际分数和 DCF 状态说明
    """
    financials = ticker_data.get("financials", {})
    basic = ticker_data.get("basic", {})
    risk = ticker_data.get("risk", {})

    # DCF 诊断：尝试计算但不参与排序
    dcf_note = _diagnose_dcf(financials, basic)

    # 安全边际 100% 由质押率构成
    pledge_ratio = risk.get("pledge_ratio")
    if pledge_ratio is not None:
        # < 20% 得满分，20-60% 线性衰减，> 60% 得 0
        if pledge_ratio <= 20.0:
            pledge_score = 100.0
        elif pledge_ratio >= 60.0:
            pledge_score = 0.0
        else:
            pledge_score = (60.0 - pledge_ratio) / (60.0 - 20.0) * 100.0
        return (pledge_score, dcf_note)

    # 质押率缺失时安全边际为 0
    return (0.0, dcf_note)


def _diagnose_dcf(financials: dict, basic: dict) -> str | None:
    """诊断 DCF 状态，返回原因说明.

    尝试计算 DCF 但不用于排序，仅用于诊断和解释。
    """
    cash_flow = financials.get("cash_flow", {})
    income = financials.get("income", {})

    netcash_operate = cash_flow.get("NETCASH_OPERATE", [])
    construct_long_asset = cash_flow.get("CONSTRUCT_LONG_ASSET", [])

    # 计算 FCF 序列
    fcf_series = []
    if netcash_operate and construct_long_asset and len(netcash_operate) == len(construct_long_asset):
        for nco, cla in zip(netcash_operate, construct_long_asset):
            if nco is not None and cla is not None:
                fcf_series.append(nco - cla)
            else:
                fcf_series.append(None)

    revenue_series = income.get("revenue", [])
    current_price = basic.get("price")

    # 过滤 None
    valid_fcf = [fcf for fcf in fcf_series if fcf is not None]

    # 数据不足
    if len(valid_fcf) < 2 or not revenue_series or current_price is None:
        return "insufficient_data"

    # 尝试计算 DCF（仅用于诊断）
    try:
        compute_simple_dcf(
            fcf_series=valid_fcf,
            revenue_series=revenue_series,
            current_price=current_price,
            assumptions={"discount_rate": 0.10, "terminal_growth": 0.03}
        )
        # DCF 计算成功，但量纲未验证（企业价值 vs 每股价格）
        return "dcf_dimension_mismatch"
    except (ValueError, ZeroDivisionError, TypeError):
        # 已知异常类型，记录但不传播
        return "calculation_error"


def compute_factor_scores(ticker_data: dict, industry_pe_map: dict | None = None) -> dict:
    """计算三因子综合分.

    Args:
        ticker_data: {
            "basic": {"pe", "pb", "price", ...},
            "financials": {...},
            "valuation": {"pe_percentile_5y", "pb", ...},
            "risk": {"pledge_ratio", ...}
        }
        industry_pe_map: {industry: median_pe} 行业 PE 中位数映射（可选，R2 增强）

    Returns:
        {"quality": float, "value": float, "safety_margin": float, "composite": float,
         "f_score": int, "dcf_note": str | None}
    """
    financials = ticker_data.get("financials", {})
    f_score = compute_f_score(financials) if financials else 0

    quality = _compute_quality_score(ticker_data)
    value = _compute_value_score(ticker_data, industry_pe_map)
    safety_margin, dcf_note = _compute_safety_margin_score(ticker_data)

    composite = quality * 0.50 + value * 0.30 + safety_margin * 0.20

    return {
        "quality": round(quality, 2),
        "value": round(value, 2),
        "safety_margin": round(safety_margin, 2),
        "composite": round(composite, 2),
        "f_score": f_score,
        "dcf_note": dcf_note
    }
