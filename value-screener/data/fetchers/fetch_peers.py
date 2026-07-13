"""竞品对比 fetcher · peers 维度（f3a §1，D2 决策 (c)，纯数据层零 LLM）.

契约：
  fetch(ticker) -> {
    "code": "600009",
    "industry": "航空机场",
    "peer_avg_pe": float,           # 同行业其他成分股 PE 均值（排除自身 + 亏损股）
    "industry_pe_rank": int,        # 自身在行业内的 PE 排名（1=最高）
    "peer_count": int,              # 行业成分股总数（含自身）
    "peer_pe_list": list[float],    # 全部成分股 PE（含自身，供 DA 回查）
  }

数据源：stock_board_industry_cons_em(symbol=industry)，per-industry（非 per-symbol）。
  industry 字段从 basic cache 读（data/cache/{ticker}/basic.json 的 industry 字段，
  由 BasicFetcher 已采）。industry 缺失 → 抛 KeyError，fetch_with_fallback 无兜底 → __error__。

_LazyTable：行业→成分股映射 intra-batch 只取一次（同行业多只股票复用，防封禁）。
异常收窄：不 except Exception，只捕获 KeyError/ValueError/AttributeError。
"""
from __future__ import annotations

import akshare as ak  # type: ignore

from .base import BaseFetcher
from ..lib.market_router import parse_ticker
from ..lib.snapshot import _LazyTable
from ..lib.utils import to_float as _to_float


# 行业→成分股 intra-batch 复用（同行业多只股票只取一次全行业表）
_lazy_industry_cons: dict[str, _LazyTable] = {}


def _get_industry_cons(industry: str):
    """取某行业的成分股 DataFrame（intra-batch 缓存，300s 失败冷却）."""
    if industry not in _lazy_industry_cons:
        _lazy_industry_cons[industry] = _LazyTable(
            lambda ind=industry: ak.stock_board_industry_cons_em(symbol=ind)
        )
    return _lazy_industry_cons[industry].get()


def _read_industry_from_cache(code: str) -> str | None:
    """从 basic cache 读 industry 字段（BasicFetcher 已采）.

    cache 路径 data/cache/{code}/basic.json。industry 缺失/缓存损坏 → None。
    """
    try:
        from ..cache.manager import CacheManager
        cache = CacheManager()
        basic = cache.get(code, "basic")
        if isinstance(basic, dict) and basic.get("industry"):
            return str(basic["industry"])
    except (KeyError, ValueError, OSError, AttributeError):
        pass
    return None


def _parse_cons(df, self_code: str) -> dict:
    """成分股 DataFrame → peer_avg_pe + 行业排名."""
    if df is None or len(df) == 0:
        raise KeyError("stock_board_industry_cons_em empty")

    code_col = next((c for c in df.columns if "代码" in str(c)), None)
    pe_col = next((c for c in df.columns if "市盈率" in str(c)), None)
    if code_col is None:
        raise KeyError("cons_em missing 代码 column")

    # 逐行收集：全成分股 PE（亏损/None 标 None），记录自身 index
    all_pes: list[float | None] = []
    self_idx: int | None = None
    for i, (_, row) in enumerate(df.iterrows()):
        code = str(row[code_col]).zfill(6)
        pe = _to_float(row[pe_col]) if pe_col in df.columns else None
        if pe is not None and pe <= 0:
            pe = None  # 亏损股 PE 无比较意义
        all_pes.append(pe)
        if code == self_code:
            self_idx = i

    # peer_avg_pe：排除自身 + 排除 None/亏损 → 取均值
    other_valid = [p for i, p in enumerate(all_pes)
                   if p is not None and i != self_idx]
    peer_avg_pe = sum(other_valid) / len(other_valid) if other_valid else None

    # 行业排名：按 PE 升序排（1=PE 最低=最便宜），自身排名（自身 PE 为 None 则不排）
    valid_sorted = sorted(
        (i for i, p in enumerate(all_pes) if p is not None),
        key=lambda i: all_pes[i],
    )
    industry_pe_rank = None
    if self_idx is not None and all_pes[self_idx] is not None:
        industry_pe_rank = next(
            (rank for rank, i in enumerate(valid_sorted, start=1) if i == self_idx),
            None,
        )

    return {
        "peer_avg_pe": peer_avg_pe,
        "industry_pe_rank": industry_pe_rank,
        "peer_count": len(all_pes),
        "peer_pe_list": [p for p in all_pes],
    }


class PeersFetcher(BaseFetcher):
    dim = "peers"

    # 测试注入点：覆盖 industry 来源（生产路径走 basic cache）
    _test_industry_override: str | None = None

    def _resolve_industry(self, code: str) -> str | None:
        """取本股票 industry（basic cache 读；测试可 override）."""
        if getattr(self, "_test_industry_override", None) is not None:
            return self._test_industry_override
        return _read_industry_from_cache(code)

    def fetch(self, ticker: str) -> dict:
        code = parse_ticker(ticker).code
        industry = self._resolve_industry(code)
        if not industry:
            # industry 缺失 → 抛 KeyError，fetch_with_fallback 无兜底 → __error__
            raise KeyError(f"industry unknown for {code}（basic cache 未采或缺失）")

        df = _get_industry_cons(industry)
        if df is None or len(df) == 0:
            raise KeyError(f"stock_board_industry_cons_em empty for industry={industry}")

        parsed = _parse_cons(df, code)
        return {
            "code": code,
            "industry": industry,
            **parsed,
        }

    # peers 依赖 industry 字段 + 全行业表，无独立兜底 provider（缺失即降级）
    fallback_providers = []
