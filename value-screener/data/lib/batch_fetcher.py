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
from ..fetchers.fetch_main_business import MainBusinessFetcher
from ..fetchers.fetch_peers import PeersFetcher
from ..fetchers.fetch_research import ResearchFetcher

_DIM_FETCHERS: dict[str, type] = {
    "basic": BasicFetcher,
    "financials": FinancialsFetcher,
    "kline": KlineFetcher,
    "valuation": ValuationFetcher,
    "risk": RiskFetcher,
    # f3a §1.7：3 新建 fetcher（L3 dossier 定性维度）
    "main_business": MainBusinessFetcher,
    "peers": PeersFetcher,
    "research": ResearchFetcher,
}


class FetchTelemetry:
    """Optional per-run fetch boundary telemetry."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.provider_calls: list[dict] = []
        self.cache_hits: list[dict] = []
        self.failures: list[dict] = []

    def record_request(self, tickers: list[str], dimensions: tuple[str, ...]) -> None:
        self.requests.append({"tickers": list(tickers), "dimensions": tuple(dimensions)})

    def record_provider_call(self, ticker: str, dimension: str) -> None:
        self.provider_calls.append({"ticker": ticker, "dimension": dimension})

    def record_cache_hit(self, ticker: str, dimension: str) -> None:
        self.cache_hits.append({"ticker": ticker, "dimension": dimension})

    def record_failure(
        self,
        ticker: str,
        dimension: str,
        *,
        status: str,
        reason: str,
    ) -> None:
        self.failures.append(
            {
                "ticker": ticker,
                "dimension": dimension,
                "status": status,
                "reason": reason,
            }
        )


class BatchFetcher:
    """批量采集 wrapper，封装并发控制."""

    def __init__(
        self,
        max_workers: int = 10,
        cache: CacheManager | None = None,
        freshness_policy: str = "require_fresh",
    ):
        if freshness_policy not in {"require_fresh", "allow_stale"}:
            raise ValueError("freshness_policy must be require_fresh or allow_stale")
        self.max_workers = max_workers
        self.cache = cache or CacheManager()
        self.freshness_policy = freshness_policy

    def fetch_all(
        self,
        tickers: list[str],
        dimensions: list[str] | None = None,
        dim_max_workers: dict[str, int] | None = None,
        telemetry: FetchTelemetry | None = None,
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
            fetcher.cache = self.cache  # 注入缓存，供跨维度读取（risk goodwill 读 financials）
            workers = min(self.max_workers, dim_workers.get(dim, self.max_workers))
            if telemetry is not None:
                telemetry.record_request(list(tickers), (dim,))
            # financials 维度单独限流（分页接口，反爬压力大）
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(self._fetch_one, fetcher, t, dim, telemetry): t
                    for t in tickers
                }
                for fut in as_completed(futures):
                    t = futures[fut]
                    results[t][dim] = fut.result()

        return results

    def _fetch_one(
        self,
        fetcher,
        ticker: str,
        dim: str,
        telemetry: FetchTelemetry | None = None,
    ) -> dict:
        """单只单维度：查缓存→未过期复用→否则采集+写缓存。失败返 error 结构."""
        # Resume：缓存未过期直接复用（跳过采集，含上次成功的维度）
        cached = self.cache.get(
            ticker,
            dim,
            allow_stale=self.freshness_policy == "allow_stale",
            validate=True,
        )
        if cached is not None:
            if telemetry is not None:
                telemetry.record_cache_hit(ticker, dim)
            return cached

        # 反爬：同 provider 请求间随机延迟 0.5-2s
        time.sleep(random.uniform(0.5, 2.0))

        if telemetry is not None:
            telemetry.record_provider_call(ticker, dim)
        data = fetcher.fetch_with_fallback(ticker)
        # fetch_with_fallback 全失败时返带 __error__ 标记的结构 → 不写缓存，下次 resume 重试
        if isinstance(data, dict) and data.get("__error__") is True:
            if telemetry is not None:
                telemetry.record_failure(
                    ticker,
                    dim,
                    status="source_failed",
                    reason=str(data.get("error") or f"fetch failed: {dim}"),
                )
            return data
        # 成功 → 写缓存
        self.cache.set(ticker, dim, data)
        return data
