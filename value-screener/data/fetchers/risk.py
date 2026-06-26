"""风险/治理 fetcher · risk 维度.

契约（design.md §1.1, §1.2, tasks 7.x）：
  fetch(ticker) -> {"pledge_ratio": float, "goodwill": float|null, "audit_opinion": str|null}

- 质押率：ak.stock_gpzy_pledge_ratio_em()（全市场一次返回，必采）
- 商誉：从 financials balance_sheet GOODWILL 派生（最新期），financials fetcher 已采
- 审计意见：ak.stock_audit_report_em()（可选降级：接口缺失/无数据返 null，不阻塞；下游不得假设非空）

容错链：质押率东财单一渠道，无独立兜底；商誉派生自 financials；审计意见可选。

review 修复：
- 质押率/审计意见为全市场表，经 _LazyTable intra-batch 只取一次、全部 ticker 复用
  （原 per-ticker 重复拉全市场表 → 冗余 + 封禁风险）。
- 商誉优先读 CacheManager 缓存的 financials（batch 下 financials 已采），避免重采三表；
  缓存未命中（standalone --dim risk）才退回直采。
"""
from __future__ import annotations

from .base import BaseFetcher
from ..lib.snapshot import _LazyTable
from ..lib.utils import to_float as _to_float


# 全市场表 intra-batch 复用（_LazyTable 持有，首调用取回，余者复用）
_lazy_pledge = _LazyTable(lambda: __import__("akshare").stock_gpzy_pledge_ratio_em())
_lazy_audit = _LazyTable(lambda: __import__("akshare").stock_audit_report_em())


def _fetch_pledge_ratio(code: str) -> float | None:
    """全市场质押率表 → 本只最新质押率(%)。"""
    df = _lazy_pledge.get()
    if df is None or len(df) == 0:
        raise KeyError("stock_gpzy_pledge_ratio_em empty")
    code_col = next((c for c in df.columns if "代码" in str(c)), df.columns[1])
    rows = df[df[code_col].astype(str).str.zfill(6) == code]
    if rows.empty:
        return None  # 无质押记录视为 0
    ratio_col = next((c for c in df.columns if "质押" in str(c) and ("比例" in str(c) or "%" in str(c))), None)
    if ratio_col is None:
        ratio_col = next((c for c in df.columns if "比例" in str(c)), df.columns[-1])
    return _to_float(rows.iloc[0][ratio_col])


def _fetch_audit_opinion(code: str) -> str | None:
    """审计意见（可选降级）：接口缺失/无数据返 None，不阻塞."""
    df = _lazy_audit.get()
    if df is None or len(df) == 0:
        return None
    code_col = next((c for c in df.columns if "代码" in str(c)), None)
    op_col = next((c for c in df.columns if "意见" in str(c) or "审计" in str(c)), None)
    if code_col is None or op_col is None:
        return None
    rows = df[df[code_col].astype(str).str.zfill(6) == code]
    if rows.empty:
        return None
    return str(rows.iloc[0][op_col]) or None


class RiskFetcher(BaseFetcher):
    dim = "risk"

    def _fetch_goodwill_from_financials(self, code: str) -> float | None:
        """商誉：优先读已缓存的 financials（batch 下已采），miss 才退回直采."""
        fin = None
        if self.cache is not None:
            try:
                fin = self.cache.get(code, "financials")
            except Exception:
                fin = None
        if fin is None:  # 缓存未命中（standalone 或 financials 未采）→ 直采一次
            from .financials import FinancialsFetcher
            try:
                fin = FinancialsFetcher().fetch_with_fallback(code)
            except Exception:
                return None
        if not isinstance(fin, dict) or fin.get("__error__") is True or "error" in fin:
            return None
        gw = fin.get("balance_sheet", {}).get("GOODWILL", [])
        for v in reversed(gw):
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    return None
        return None

    def fetch(self, ticker: str) -> dict:
        pledge = _fetch_pledge_ratio(ticker)
        goodwill = self._fetch_goodwill_from_financials(ticker)
        audit = _fetch_audit_opinion(ticker)  # 可选降级，None 不阻塞
        return {
            "pledge_ratio": pledge,
            "goodwill": goodwill,
            "audit_opinion": audit,
        }

    # 质押率为东财单一渠道，无独立兜底 provider
    fallback_providers = []
