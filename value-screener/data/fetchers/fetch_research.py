"""研报共识 fetcher · research 维度（f3a §1，D2 决策 (c)，纯数据层零 LLM）.

契约：
  fetch(ticker) -> {
    "code": "600009",
    "consensus_eps": float | None,     # 各研报远期 EPS 均值（无有效研报 → None，降级不抛）
    "target_price": float | None,      # consensus_eps × consensus_pe（远期 EPS × 远期 PE）
    "buy_rating_pct": float,           # 买入/增持 评级占比（看多比例）
    "coverage_count": int,             # 研报总数
    "rating_distribution": dict,       # 各评级计数 {买入:N, 增持:N, 中性:N, 减持:N, 卖出:N}
  }

数据源：stock_research_report_em(symbol=code)，per-symbol（非全市场表，无需 _LazyTable）。
小票常返 0 条研报 → coverage_count=0 + consensus_eps=None（降级不阻断，由 dossier 标 degraded）。

异常收窄：不 except Exception，只捕获 KeyError/ValueError/AttributeError。
fetch_with_fallback 全失败返 {__error__: True} 不抛。

注：研报的 EPS/PE/评级是「市场预期」不是公司事实（design Risks：研报不当事实，
prompt 物理分区时单独成段，引用须写明「市场预期认为……」）。
"""
from __future__ import annotations

import akshare as ak  # type: ignore

from .base import BaseFetcher
from ..lib.market_router import parse_ticker
from ..lib.utils import to_float as _to_float


# 看多评级集合（买入+增持视为看多）
_BULLISH_RATINGS = {"买入", "增持", "强烈推荐", "推荐"}


def _latest_year_eps_pe_cols(df) -> tuple[str | None, str | None]:
    """从研报 df 找最近年份的 盈利预测-收益 / 盈利预测-市盈率 列.

    列名形如 '2026-盈利预测-收益' / '2026-盈利预测-市盈率'，取年份最大的那组。
    """
    eps_cols = [c for c in df.columns if "盈利预测" in str(c) and "收益" in str(c)]
    pe_cols = [c for c in df.columns if "盈利预测" in str(c) and "市盈率" in str(c)]
    # 按年份排序取最新
    eps_cols.sort(reverse=True)
    pe_cols.sort(reverse=True)
    return (eps_cols[0] if eps_cols else None, pe_cols[0] if pe_cols else None)


def _parse_research(df) -> dict:
    """研报 DataFrame → consensus_eps/target_price/buy_rating_pct/coverage_count."""
    if df is None or len(df) == 0:
        return {
            "consensus_eps": None,
            "target_price": None,
            "buy_rating_pct": 0.0,
            "coverage_count": 0,
            "rating_distribution": {},
        }

    coverage_count = len(df)

    # 评级分布 + 看多占比
    rating_col = next((c for c in df.columns if "评级" in str(c)), None)
    rating_dist: dict[str, int] = {}
    bullish_count = 0
    if rating_col is not None:
        for r in df[rating_col].dropna().astype(str):
            rating_dist[r] = rating_dist.get(r, 0) + 1
            if r in _BULLISH_RATINGS:
                bullish_count += 1
    buy_rating_pct = bullish_count / coverage_count if coverage_count else 0.0

    # consensus_eps：最新年份 EPS 均值（过滤 None/无效）
    eps_col, pe_col = _latest_year_eps_pe_cols(df)
    consensus_eps = None
    consensus_pe = None
    if eps_col is not None:
        eps_vals = [_to_float(v) for v in df[eps_col].tolist()]
        valid_eps = [v for v in eps_vals if v is not None]
        if valid_eps:
            consensus_eps = sum(valid_eps) / len(valid_eps)
    if pe_col is not None:
        pe_vals = [_to_float(v) for v in df[pe_col].tolist()]
        valid_pe = [v for v in pe_vals if v is not None]
        if valid_pe:
            consensus_pe = sum(valid_pe) / len(valid_pe)

    # target_price = consensus_eps × consensus_pe
    target_price = None
    if consensus_eps is not None and consensus_pe is not None:
        target_price = consensus_eps * consensus_pe

    return {
        "consensus_eps": consensus_eps,
        "target_price": target_price,
        "buy_rating_pct": buy_rating_pct,
        "coverage_count": coverage_count,
        "rating_distribution": rating_dist,
    }


class ResearchFetcher(BaseFetcher):
    dim = "research"

    def fetch(self, ticker: str) -> dict:
        """主选 stock_research_report_em，per-symbol 研报共识."""
        code = parse_ticker(ticker).code
        df = ak.stock_research_report_em(symbol=code)
        parsed = _parse_research(df)
        return {"code": code, **parsed}

    # 研报共识为东财单一渠道，无独立兜底 provider
    fallback_providers = []
