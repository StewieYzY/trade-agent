"""基础信息 fetcher · basic 维度.

契约（design.md §1.1, §1.2, tasks 3.x）：
  fetch(ticker) -> {"code", "name", "price", "pe", "pb", "market_cap", "industry"}

容错链：
  主选 stock_zh_a_spot_em()（全市场快照 ~5000 只，一次取）→ 兜底 1 stock_info_a_code_name() + tencent qt 逐只
  兜底 2/3 雪球/baostock MVP 不实现（留接口）
指数退避 backoff=2 max_retries=3 + 随机延迟 0.5-2s；异常收窄（不 except Exception）。
"""
from __future__ import annotations

from .base import BaseFetcher
from ..lib.data_sources import fetch_price_tencent_qt, get_a_share_name_map
from ..lib.industry_mapper import build_industry_map
from ..lib.snapshot import _LazyTable
from ..lib.utils import to_float as _to_float


# 行业映射 intra-batch 只构建一次（~70 行业 × 2s ≈ 2-3 分钟，之后 STATIC 缓存复用 7d）
_lazy_industry = _LazyTable(build_industry_map)


class BasicFetcher(BaseFetcher):
    dim = "basic"

    _lazy_spot = _LazyTable(lambda: __import__("akshare").stock_zh_a_spot_em())

    def fetch(self, ticker: str) -> dict:
        """主选：ak.stock_zh_a_spot_em() 全市场快照，过滤本只.

        spot_em 为全市场表（~5000 行），intra-batch 经 _LazyTable 只取一次、
        全部 ticker 复用（review #3：避免 per-ticker 重复拉全市场快照）。
        """
        df = self._lazy_spot.get()
        if df is None or len(df) == 0:
            raise KeyError("stock_zh_a_spot_em empty")
        code_col = next((c for c in df.columns if "代码" in str(c)), df.columns[0])
        row = df[df[code_col].astype(str).str.zfill(6) == ticker]
        if row.empty:
            raise KeyError(f"{ticker} not in spot snapshot")
        r = row.iloc[0]

        def col(*kw):
            for c in df.columns:
                sc = str(c)
                if any(k in sc for k in kw):
                    return r[c]
            return None

        # 从行业映射表补 industry（spot_em 无行业列）
        industry_map = _lazy_industry.get()
        industry = industry_map.get(ticker) if industry_map else None

        return {
            "code": ticker,
            # col() 已返回单元格值，直接用；原 r.get(col("名称"),"") 把 name 值当 dict key 查恒空（pre-existing bug，f1-deviation-fix §5 修复）
            "name": str(col("名称") or "") or None,
            "price": _to_float(col("最新价", "现价")),
            "pe": _to_float(col("市盈率", "动态", "pe")),
            "pb": _to_float(col("市净率", "pb")),
            "market_cap": _to_float(col("总市值")),
            "industry": industry,
        }

    # ── 兜底 provider ──────────────────────────────────────────
    @staticmethod
    def _fallback_tencent_qt(ticker: str) -> dict:
        """兜底 1：tencent qt 逐只 + 名称映射补行业."""
        qt = fetch_price_tencent_qt(ticker, market="A")
        if not qt:
            raise KeyError(f"tencent qt empty for {ticker}")
        name_map = get_a_share_name_map()
        industry_map = _lazy_industry.get()
        return {
            "code": ticker,
            "name": qt.get("name") or name_map.get(ticker),
            "price": qt.get("price"),
            "pe": qt.get("pe"),
            "pb": qt.get("pb"),
            "market_cap": qt.get("market_cap"),
            "industry": industry_map.get(ticker) if industry_map else None,
        }

    @staticmethod
    def _fallback_em_individual(ticker: str) -> dict:
        """兜底 2（留接口，MVP 用 stock_individual_info_em 单只补名称/行业）."""
        import akshare as ak  # type: ignore
        df = ak.stock_individual_info_em(symbol=ticker)
        if df is None or len(df) == 0:
            raise KeyError(f"stock_individual_info_em empty for {ticker}")
        m = {str(r["item"]): r["value"] for _, r in df.iterrows()}
        return {
            "code": ticker,
            "name": m.get("股票简称"),
            "price": _to_float(m.get("最新价")),
            "pe": _to_float(m.get("市盈率(动态)")) or _to_float(m.get("市盈率")),
            "pb": _to_float(m.get("市净率")) or _to_float(m.get("市净率(动态)")),
            "market_cap": _to_float(m.get("总市值")),
            "industry": m.get("行业"),
        }

    fallback_providers = [_fallback_tencent_qt, _fallback_em_individual]
