"""特征工程 · stock_features 模块.

借鉴 UZI stock_features.py（591 行 ~108 特征）的纯函数模式；change 0 聚焦
F-Score 九项组装（Piotroski 1980），~108 标准化特征留 L1（依赖组装后的 raw_data schema）。

输出契约（design.md §2.2, tasks 8.2/8.6）：
  compute_f_score(financials: dict) -> int   # 0-9，每项满足得 1 分

输入：financials fetcher 的多期结构 {years, income, balance_sheet, cash_flow}，
函数内部取近两期算同比。纯计算，不触发采集，不继承 BaseFetcher。
派生口径遵循 Piotroski 1980 原版（ROA = 净利润/期末总资产，非平均）。
"""
from __future__ import annotations


def _f(v, default: float = 0.0) -> float:
    """安全转 float，None/空→default."""
    try:
        if v in (None, "", "-", "--"):
            return default
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _last2(series: list) -> tuple[float, float] | None:
    """取序列最后两期（t, t-1）。不足两期返回 None."""
    vals = [_f(v) for v in series if v is not None]
    if len(vals) < 2:
        return None
    return vals[-1], vals[-2]


def _ratio(num: float, denom: float) -> float | None:
    if denom in (0, None):
        return None
    return num / denom


def compute_f_score(financials: dict) -> int:
    """Piotroski F-Score 九项 → 0-9 整数.

    F1 ROA>0 | F2 CFO>0 | F3 ROA↑ | F4 CFO>ROA | F5 长期负债率↓
    F6 流动比率↑ | F7 毛利率↑ | F8 资产周转率↑ | F9 无稀释（股本↓或持平）
    """
    income = financials.get("income", {})
    bs = financials.get("balance_sheet", {})
    cf = financials.get("cash_flow", {})

    score = 0

    # ROA = 净利润 / 期末总资产（Piotroski 原版，非平均）
    np_series = income.get("net_profit", [])
    ta_series = bs.get("TOTAL_ASSETS", [])
    np_cur = _f(np_series[-1]) if np_series else 0.0
    ta_cur = _f(ta_series[-1]) if ta_series else 0.0
    roa_cur = _ratio(np_cur, ta_cur)

    # F1: ROA > 0
    if roa_cur is not None and roa_cur > 0:
        score += 1

    # F2: CFO > 0（经营现金流）
    ocf_series = cf.get("NETCASH_OPERATE", []) or income.get("operating_cash_flow", [])
    ocf_cur = _f(ocf_series[-1]) if ocf_series else 0.0
    if ocf_cur > 0:
        score += 1

    # F3: ROA ↑（两期）
    ta_prev = _f(ta_series[-2]) if len(ta_series) >= 2 else 0.0
    np_prev = _f(np_series[-2]) if len(np_series) >= 2 else 0.0
    roa_prev = _ratio(np_prev, ta_prev)
    if roa_cur is not None and roa_prev is not None and roa_cur > roa_prev:
        score += 1

    # F4: CFO/TA > ROA（应计项，现金流 ROA 比会计 ROA 更高质量）
    cfo_roa = _ratio(ocf_cur, ta_cur)
    if cfo_roa is not None and roa_cur is not None and cfo_roa > roa_cur:
        score += 1

    # F5: 长期负债率 ↓（TOTAL_NONCURRENT_LIAB / TOTAL_ASSETS，两期）
    ncl_series = bs.get("TOTAL_NONCURRENT_LIAB", [])
    lev_cur = _ratio(_f(ncl_series[-1]) if ncl_series else 0.0, ta_cur)
    lev_prev = _ratio(_f(ncl_series[-2]) if len(ncl_series) >= 2 else 0.0, ta_prev)
    if lev_cur is not None and lev_prev is not None and lev_cur < lev_prev:
        score += 1

    # F6: 流动比率 ↑（TOTAL_CURRENT_ASSETS / TOTAL_CURRENT_LIAB，两期）
    ca_series = bs.get("TOTAL_CURRENT_ASSETS", [])
    cl_series = bs.get("TOTAL_CURRENT_LIAB", [])
    cr_cur = _ratio(_f(ca_series[-1]) if ca_series else 0.0,
                    _f(cl_series[-1]) if cl_series else 0.0)
    cr_prev = _ratio(_f(ca_series[-2]) if len(ca_series) >= 2 else 0.0,
                     _f(cl_series[-2]) if len(cl_series) >= 2 else 0.0)
    if cr_cur is not None and cr_prev is not None and cr_cur > cr_prev:
        score += 1

    # F7: 毛利率 ↑（(营收-营业成本)/营收，两期）
    rev_series = income.get("revenue", [])
    oc_series = income.get("operating_cost", [])
    gm_cur = _ratio(_f(rev_series[-1]) - _f(oc_series[-1]) if rev_series and oc_series else 0.0,
                    _f(rev_series[-1]) if rev_series else 0.0)
    gm_prev = _ratio(_f(rev_series[-2]) - _f(oc_series[-2]) if len(rev_series) >= 2 and len(oc_series) >= 2 else 0.0,
                     _f(rev_series[-2]) if len(rev_series) >= 2 else 0.0)
    if gm_cur is not None and gm_prev is not None and gm_cur > gm_prev:
        score += 1

    # F8: 资产周转率 ↑（营收 / 期末总资产，两期）
    at_cur = _ratio(_f(rev_series[-1]) if rev_series else 0.0, ta_cur)
    at_prev = _ratio(_f(rev_series[-2]) if len(rev_series) >= 2 else 0.0, ta_prev)
    if at_cur is not None and at_prev is not None and at_cur > at_prev:
        score += 1

    # F9: 无稀释（股本同比不增）
    sc_series = bs.get("SHARE_CAPITAL", [])
    sc_cur = _f(sc_series[-1]) if sc_series else 0.0
    sc_prev = _f(sc_series[-2]) if len(sc_series) >= 2 else 0.0
    if sc_prev > 0 and sc_cur <= sc_prev:
        score += 1

    return score
