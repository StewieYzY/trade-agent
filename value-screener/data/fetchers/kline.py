"""K 线 fetcher · kline 维度.

契约（design.md §1.2, tasks 5.x）：
  fetch(ticker) -> {"dates":[...], "close":[...], "volume":[...]}  # 近 250 交易日

容错链（UZI _kline_a_share_chain 验证过 6 级）：
  主选 stock_zh_a_hist()（东财，前复权）
  → 兜底 1 stock_zh_a_daily()（新浪，列名归一化为东财格式）
  → 兜底 2 baostock query_history_k_data_plus（官方免登录）
  → 兜底 3-5 MVP 不实现，留接口（东财 push2his / 新浪 quotes / 腾讯 ifzq）
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import BaseFetcher

_DAYS = 250  # 近 250 交易日（1 年）


def _hist_range() -> tuple[str, str]:
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=_DAYS + 60)).strftime("%Y%m%d")  # 多取 60 自然日补足交易日
    return start, end


def _normalize_em(df) -> dict:
    """东财 stock_zh_a_hist 列名 → {dates, close, volume}."""
    date_col = next((c for c in df.columns if "日期" in str(c)), df.columns[0])
    close_col = next((c for c in df.columns if "收盘" in str(c)), None)
    vol_col = next((c for c in df.columns if "成交量" in str(c)), None)
    if close_col is None:
        raise KeyError("no close column")
    return {
        "dates": [str(d) for d in df[date_col].tolist()],
        "close": [float(v) for v in df[close_col].tolist()],
        "volume": [float(v) for v in df[vol_col].tolist()] if vol_col else [None] * len(df),
    }


def _normalize_daily(df) -> dict:
    """新浪 stock_zh_a_daily 列名归一化为东财格式."""
    date_col = next((c for c in df.columns if "date" in str(c).lower()), df.columns[0])
    close_col = next((c for c in df.columns if "close" in str(c).lower()), None)
    vol_col = next((c for c in df.columns if "volume" in str(c).lower() or "成交量" in str(c)), None)
    if close_col is None:
        raise KeyError("no close column (daily)")
    return {
        "dates": [str(d) for d in df[date_col].tolist()],
        "close": [float(v) for v in df[close_col].tolist()],
        "volume": [float(v) for v in df[vol_col].tolist()] if vol_col else [None] * len(df),
    }


class KlineFetcher(BaseFetcher):
    dim = "kline"

    def fetch(self, ticker: str) -> dict:
        """主选：ak.stock_zh_a_hist() 东财前复权."""
        import akshare as ak  # type: ignore
        start, end = _hist_range()
        df = ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start, end_date=end, adjust="qfq")
        if df is None or len(df) == 0:
            raise KeyError(f"stock_zh_a_hist empty for {ticker}")
        return _normalize_em(df)

    @staticmethod
    def _fallback_daily(ticker: str) -> dict:
        """兜底 1：ak.stock_zh_a_daily() 新浪（列名归一化）."""
        import akshare as ak  # type: ignore
        from ..lib.market_router import parse_ticker
        ti = parse_ticker(ticker)
        # sina 符号：sz000001 / sh600519
        sina_sym = f"{'sh' if ti.full.endswith('.SH') else 'sz'}{ticker}"
        start, end = _hist_range()
        df = ak.stock_zh_a_daily(symbol=sina_sym, start_date=start, end_date=end, adjust="qfq")
        if df is None or len(df) == 0:
            raise KeyError(f"stock_zh_a_daily empty for {ticker}")
        return _normalize_daily(df)

    @staticmethod
    def _fallback_baostock(ticker: str) -> dict:
        """兜底 2：baostock query_history_k_data_plus（官方免登录限流）."""
        try:
            import baostock as bs  # type: ignore
        except ImportError:
            raise KeyError("baostock not installed")
        from ..lib.market_router import parse_ticker
        ti = parse_ticker(ticker)
        bs_code = f"{'sh' if ti.full.endswith('.SH') else 'sz'}.{ticker}"
        start, end = _hist_range()
        lg = bs.login()
        if lg.error_code != "0":
            raise KeyError(f"baostock login failed: {lg.error_msg}")
        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,close,volume",
                start_date=start, end_date=end,
                frequency="d", adjustflag="2")  # 2=前复权
            if rs.error_code != "0":
                raise KeyError(f"baostock query failed: {rs.error_msg}")
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                raise KeyError(f"baostock empty for {ticker}")
            return {
                "dates": [r[0] for r in rows],
                "close": [float(r[1]) if r[1] else None for r in rows],
                "volume": [float(r[2]) if r[2] else None for r in rows],
            }
        finally:
            bs.logout()

    # 兜底 3-5 留接口（MVP 不实现）：push2his / 新浪 quotes / 腾讯 ifzq
    fallback_providers = [_fallback_daily, _fallback_baostock]
