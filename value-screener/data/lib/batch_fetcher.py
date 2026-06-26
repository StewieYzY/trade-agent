"""批量采集 wrapper · BatchFetcher.

契约（design.md §4.1, §3.3, tasks 10.x）：
  BatchFetcher(max_workers=10).fetch_all(tickers, dimensions, dim_max_workers)
      -> {ticker: {dim: data}}

- Layer2 并发：max_workers=10（basic/kline/valuation/risk）；financials 维度 max_workers=4
  （分页接口，反爬压力大）。dim_max_workers 默认 {"financials":4} 覆盖全局。
- 集成 CacheManager：先查缓存，未过期跳过采集；采集成功后写缓存。
- Resume：某维度失败（fetch_with_fallback 返 error）不影响其他维度；下次只重试失败的
  （缓存里没写成功数据 → is_expired 返 True → 重采）。
- 反爬：同 provider 请求间随机延迟 0.5-2s。
- 同步接口（akshare 同步库），并发由 ThreadPoolExecutor 承担。
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..cache.manager import CacheManager
from ..fetchers.basic import BasicFetcher
from ..fetchers.financials import FinancialsFetcher
from ..fetchers.kline import KlineFetcher
from ..fetchers.valuation import ValuationFetcher
from ..fetchers.risk import RiskFetcher

_DIM_FETCHERS: dict[str, type] = {
    "basic": BasicFetcher,
    "financials": FinancialsFetcher,
    "kline": KlineFetcher,
    "valuation": ValuationFetcher,
    "risk": RiskFetcher,
}


class BatchFetcher:
    """批量采集 wrapper，封装并发控制."""

    def __init__(self, max_workers: int = 10, cache: CacheManager | None = None):
        self.max_workers = max_workers
        self.cache = cache or CacheManager()

    def fetch_all(
        self,
        tickers: list[str],
        dimensions: list[str] | None = None,
        dim_max_workers: dict[str, int] | None = None,
    ) -> dict[str, dict]:
        """对每只股票并行采集所有维度（同步接口）.

        dim_max_workers：按维度覆盖并发数，默认 {"financials": 4}。
        返回 {ticker: {dim: data_or_error}}。
        """
        dims = dimensions or list(_DIM_FETCHERS.keys())
        dim_workers = {"financials": 4}
        if dim_max_workers:
            dim_workers.update(dim_max_workers)

        results: dict[str, dict] = {t: {} for t in tickers}

        for dim in dims:
            fetcher_cls = _DIM_FETCHERS.get(dim)
            if fetcher_cls is None:
                continue
            fetcher = fetcher_cls()
            workers = min(self.max_workers, dim_workers.get(dim, self.max_workers))
            # financials 维度单独限流（分页接口，反爬压力大）
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(self._fetch_one, fetcher, t, dim): t for t in tickers}
                for fut in as_completed(futures):
                    t = futures[fut]
                    results[t][dim] = fut.result()

        return results

    def _fetch_one(self, fetcher, ticker: str, dim: str) -> dict:
        """单只单维度：查缓存→未过期复用→否则采集+写缓存。失败返 error 结构."""
        # Resume：缓存未过期直接复用（跳过采集，含上次成功的维度）
        cached = self.cache.get(ticker, dim)
        if cached is not None:
            return cached

        # 反爬：同 provider 请求间随机延迟 0.5-2s
        time.sleep(random.uniform(0.5, 2.0))

        data = fetcher.fetch_with_fallback(ticker)
        # fetch_with_fallback 全失败时返 {"error":...} → 不写缓存，下次 resume 重试
        if isinstance(data, dict) and "error" in data and len(data) <= 3:
            return data
        # 成功 → 写缓存
        self.cache.set(ticker, dim, data)
        return data
