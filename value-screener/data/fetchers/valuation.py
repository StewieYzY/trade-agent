"""估值 fetcher · valuation 维度.

契约（design.md §1.2, tasks 6.x）：
  fetch(ticker) -> {"pe_ttm","pb","pe_percentile_5y","pb_percentile_5y",
                    "pe_history":[...],"pb_history":[...],"graham_number"}

容错链：
  主选 stock_zh_valuation_baidu()（PE/PB 近 5 年历史序列，算分位）
  → 兜底 1 stock_industry_pe_ratio_cninfo()（行业 PE 均值，绕开东财 push2）
  港股兜底 hk_valuation_comparison_em MVP 不实现。
格雷厄姆数：sqrt(22.5 * EPS * BVPS)；EPS=price/PE, BVPS=price/PB（从主选 PE/PB+股价派生）。
"""
from __future__ import annotations

import math

from .base import BaseFetcher

_YEARS = 5


def _to_float(v) -> float | None:
    try:
        if v in (None, "", "-", "--"):
            return None
        return float(str(v).replace(",", "").replace("%", ""))
    except (TypeError, ValueError):
        return None


def _percentile(value: float | None, series: list[float | None]) -> float | None:
    """value 在 series 中的历史分位（0-100）。None→None."""
    if value is None:
        return None
    clean = sorted(v for v in series if v is not None)
    if not clean:
        return None
    below = sum(1 for v in clean if v <= value)
    return round(below / len(clean) * 100, 2)


def _fetch_baidu_series(code: str, indicator: str) -> tuple[list[float | None], float | None]:
    """stock_zh_valuation_baidu → (历史序列, 最新值)."""
    import akshare as ak  # type: ignore
    df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period=f"近{_YEARS}年")
    if df is None or len(df) == 0:
        raise KeyError(f"baidu {indicator} empty for {code}")
    val_col = next((c for c in df.columns if "值" in str(c) or "估值" in str(c) or indicator in str(c)),
                   df.columns[-1])
    series = [_to_float(v) for v in df[val_col].tolist()]
    latest = series[-1] if series else None
    return series, latest


def _graham_number(pe: float | None, pb: float | None, price: float | None) -> float | None:
    """sqrt(22.5 * EPS * BVPS)；EPS=price/PE, BVPS=price/PB → price*sqrt(22.5/(PE*PB))."""
    if pe in (None, 0) or pb in (None, 0) or price is None:
        return None
    try:
        return round(price * math.sqrt(22.5 / (pe * pb)), 2)
    except (ValueError, ZeroDivisionError):
        return None


def _fetch_price(code: str) -> float | None:
    """最新股价（从 tencent qt 取，供 graham 数派生）."""
    from ..lib.data_sources import fetch_price_tencent_qt
    qt = fetch_price_tencent_qt(code, market="A")
    return qt.get("price")


class ValuationFetcher(BaseFetcher):
    dim = "valuation"

    def fetch(self, ticker: str) -> dict:
        """主选：baidu PE/PB 5 年历史序列 + 分位 + graham 数."""
        pe_history, pe_latest = _fetch_baidu_series(ticker, "市盈率(TTM)")
        pb_history, pb_latest = _fetch_baidu_series(ticker, "市净率")
        price = _fetch_price(ticker)
        return {
            "pe_ttm": pe_latest,
            "pb": pb_latest,
            "pe_percentile_5y": _percentile(pe_latest, pe_history),
            "pb_percentile_5y": _percentile(pb_latest, pb_history),
            "pe_history": pe_history,
            "pb_history": pb_history,
            "graham_number": _graham_number(pe_latest, pb_latest, price),
        }

    @staticmethod
    def _fallback_cninfo(ticker: str) -> dict:
        """兜底 1：行业 PE 均值（cninfo，绕开东财 push2）。分位无法算，仅返回行业均值."""
        import akshare as ak  # type: ignore
        df = ak.stock_industry_pe_ratio_cninfo()
        if df is None or len(df) == 0:
            raise KeyError(f"cninfo industry pe empty for {ticker}")
        # 行业匹配较复杂，MVP 返回全市场均值作为兜底估值锚
        pe_col = next((c for c in df.columns if "市盈率" in str(c) or "PE" in str(c).upper()), None)
        vals = [_to_float(v) for v in df[pe_col].tolist()] if pe_col else []
        vals = [v for v in vals if v is not None]
        industry_pe = round(sum(vals) / len(vals), 2) if vals else None
        return {
            "pe_ttm": industry_pe,
            "pb": None,
            "pe_percentile_5y": None,
            "pb_percentile_5y": None,
            "pe_history": [],
            "pb_history": [],
            "graham_number": None,
        }

    fallback_providers = [_fallback_cninfo]
