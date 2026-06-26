"""财报 fetcher · financials 维度.

契约（design.md §1.1, §1.2, §2.2/§2.3 输入, tasks 4.x）：
  fetch(ticker) -> {
    "years": [str],               # 近 3 年年报，如 ["2022","2023","2024"]
    "income": {"revenue":[],"net_profit":[],"operating_cost":[],"operating_cash_flow":[],"goodwill":[]},
    "balance_sheet": {"TOTAL_ASSETS":[],"TOTAL_CURRENT_ASSETS":[],"TOTAL_CURRENT_LIAB":[],
                       "TOTAL_NONCURRENT_LIAB":[],"SHARE_CAPITAL":[],"GOODWILL":[]},
    "cash_flow": {"NETCASH_OPERATE":[],"CONSTRUCT_LONG_ASSET":[]},
  }

数据源：主选同花顺三表（stock_financial_{benefit|debt|cash}_ths, indicator="按年度"），
绕开东财 _by_report_em 的 hidctype 反爬缺陷（spec S4 风险，实测确认 em 系全挂）。
兜底 1：东财 stock_financial_abstract（利润表行，字段较全但仅 income）+ 新浪。
异常收窄：不 except Exception；分页/网络异常收窄为 KeyError/ValueError/AttributeError。
"""
from __future__ import annotations

import re

from .base import BaseFetcher
from ..lib.utils import to_float as _to_float

_YEARS = 3  # 近 3 年年报

# ths 利润表列名 → 输出键
_BENEFIT_COLS = {
    "revenue": "*营业总收入",
    "net_profit": "*归属于母公司所有者的净利润",
    "operating_cost": "其中：营业成本",
}
# ths 资产负债表列名 → 输出键（spec 命名）
_DEBT_COLS = {
    "TOTAL_ASSETS": "*资产合计",
    "TOTAL_CURRENT_ASSETS": "流动资产合计",
    "TOTAL_CURRENT_LIAB": "流动负债合计",
    "TOTAL_NONCURRENT_LIAB": "非流动负债合计",
    "SHARE_CAPITAL": "实收资本（或股本）",
}
# ths 现金流表列名 → 输出键
_CASH_COLS = {
    "NETCASH_OPERATE": "*经营活动产生的现金流量净额",
    "CONSTRUCT_LONG_ASSET": "购建固定资产、无形资产和其他长期资产支付的现金",
}



def _annual_years(df, year_col: str = "报告期") -> list[str]:
    """ths 报告期列（年度，如 2024）→ 近 N 年列表（旧→新）."""
    if df is None or len(df) == 0 or year_col not in df.columns:
        return []
    years = [str(int(float(y))) for y in df[year_col].tolist()
             if y is not None and str(y).strip() not in ("", "nan", "None")]
    years = sorted(set(years), key=lambda y: int(y))
    return years[-_YEARS:]


def _extract_ths(df, col_map: dict[str, str], years: list[str]) -> dict[str, list]:
    """从 ths 表按年份对齐提取列 → {out_key: [v_per_year]}."""
    out: dict[str, list] = {}
    if df is None or len(df) == 0 or "报告期" not in df.columns:
        for k in col_map:
            out[k] = [None] * len(years)
        return out
    # 按报告期年份建索引
    df = df.copy()
    df["_y"] = df["报告期"].map(lambda y: str(int(float(y))) if y is not None and str(y).strip() not in ("", "nan", "None") else None)
    idx = {y: i for i, y in enumerate(df["_y"].tolist()) if y}
    for out_key, ths_col in col_map.items():
        if ths_col not in df.columns:
            out[out_key] = [None] * len(years)
            continue
        out[out_key] = [_to_float(df.iloc[idx[y]][ths_col]) if y in idx else None for y in years]
    return out


def _fetch_ths_three_tables(code: str) -> dict:
    """主选：同花顺三表合并为多期结构."""
    import akshare as ak  # type: ignore
    benefit = ak.stock_financial_benefit_ths(symbol=code, indicator="按年度")
    debt = ak.stock_financial_debt_ths(symbol=code, indicator="按年度")
    cash = ak.stock_financial_cash_ths(symbol=code, indicator="按年度")

    years = _annual_years(benefit) or _annual_years(debt) or _annual_years(cash)
    if not years:
        raise KeyError(f"no annual periods (ths) for {code}")

    income = _extract_ths(benefit, _BENEFIT_COLS, years)
    # operating_cash_flow 从现金流传入 income（F-Score F2 用）
    cash_flow = _extract_ths(cash, _CASH_COLS, years)
    income["operating_cash_flow"] = cash_flow.get("NETCASH_OPERATE", [None] * len(years))
    # goodwill：ths 三表无商誉列，从东财 abstract 补（失败置 None，不影响 F-Score）
    income["goodwill"] = _fetch_goodwill_abstract(code, years)
    balance_sheet = _extract_ths(debt, _DEBT_COLS, years)
    balance_sheet["GOODWILL"] = income["goodwill"]
    return {"years": years, "income": income, "balance_sheet": balance_sheet, "cash_flow": cash_flow}


def _fetch_goodwill_abstract(code: str, years: list[str]) -> list[float | None]:
    """东财 stock_financial_abstract 商誉行（多期），失败返全 None."""
    try:
        import akshare as ak  # type: ignore
        df = ak.stock_financial_abstract(symbol=code)
        if df is None or len(df) == 0 or "指标" not in df.columns:
            return [None] * len(years)
        row = df[df["指标"].astype(str).str.contains("商誉", na=False, regex=False)]
        if row.empty:
            return [None] * len(years)
        # abstract 列名为报告期（如 2024-12-31），取年报期对齐
        period_cols = [c for c in df.columns if c not in ("选项", "指标") and str(c).endswith("1231")]
        period_years = {str(c)[:4]: c for c in period_cols}
        return [_to_float(row[period_years[y]].iloc[0]) if y in period_years else None for y in years]
    except (KeyError, ValueError, AttributeError):
        return [None] * len(years)


def _fallback_sina(code: str) -> dict:
    """兜底 1：新浪财报接口（UZI 验证过稳定性，字段可能不全）."""
    import akshare as ak  # type: ignore
    years: list[str] = []
    income: dict[str, list] = {}
    try:
        df = ak.stock_financial_report_sina(stock=code, symbol="利润表")
    except (KeyError, AttributeError, ValueError):
        raise KeyError(f"sina financials empty for {code}")
    if df is None or len(df) == 0:
        raise KeyError(f"sina financials empty for {code}")
    date_col = next((c for c in df.columns if "报告日" in str(c) or "日期" in str(c)), df.columns[0])
    df["_y"] = df[date_col].map(lambda d: str(d)[:4] if str(d).endswith("1231") else None)
    ar = df[df["_y"].notna()].sort_values(date_col)
    years = ar["_y"].tolist()[-_YEARS:]
    income["revenue"] = [_to_float(v) for v in ar.get("营业收入", [None] * len(years)).tolist()] if "营业收入" in ar else [None] * len(years)
    income["net_profit"] = [_to_float(v) for v in ar.get("净利润", [None] * len(years)).tolist()] if "净利润" in ar else [None] * len(years)
    income["operating_cost"] = [None] * len(years)
    income["operating_cash_flow"] = [None] * len(years)
    income["goodwill"] = [None] * len(years)
    return {
        "years": years,
        "income": income,
        "balance_sheet": {c: [None] * len(years) for c in list(_DEBT_COLS.keys()) + ["GOODWILL"]},
        "cash_flow": {c: [None] * len(years) for c in _CASH_COLS},
    }


class FinancialsFetcher(BaseFetcher):
    dim = "financials"

    def fetch(self, ticker: str) -> dict:
        return _fetch_ths_three_tables(ticker)

    fallback_providers = [_fallback_sina]
