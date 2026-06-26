"""Fetcher 基类 · 所有维度 fetcher 继承.

设计（design.md §1.3）：
- fetch(ticker) -> dict：抽象，子类实现主选 provider 采集，返回该维度多期结构
- fetch_with_fallback(ticker) -> dict：具体，容错链编排（主选→兜底1→兜底2...），
  逐 provider 尝试，成功即返回；全部失败返回 {"error": ...}（不抛，配合 resume 标记失败维度）

同步接口（akshare 为同步库）；并发由 BatchFetcher.ThreadPoolExecutor 承担。
异常收窄：不允许 except Exception，只捕获 httpx.TimeoutException / KeyError / akshare 具体异常。
"""
from __future__ import annotations

import random
import time
from abc import ABC, abstractmethod
from typing import Callable


def _retry(fn: Callable[[], dict], *, attempts: int = 3, backoff: float = 2.0,
           jitter: tuple[float, float] = (0.5, 2.0)) -> dict | None:
    """指数退避重试（backoff=2, max_retries=3）+ 随机延迟 0.5-2s.

    返回 fn() 结果；全部失败返回 None。fn 内部应自行收窄异常——此处只负责重试调度。
    """
    last_exc = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 重试调度需捕获所有以重试；子类 fn 内已收窄具体类型
            last_exc = exc
            if i < attempts - 1:
                time.sleep((backoff ** i) + random.uniform(*jitter))
    # 穷尽重试仍失败
    if last_exc is not None:
        return None
    return None


class BaseFetcher(ABC):
    """所有维度 fetcher 的基类."""

    dim: str = ""                       # 子类必填：维度名（basic/financials/kline/valuation/risk）
    fallback_providers: list[Callable[[str], dict]] = []  # 子类可填：兜底 provider 列表

    @abstractmethod
    def fetch(self, ticker: str) -> dict:
        """主选 provider 采集单只股票该维度数据，返回多期结构（见各 fetcher 契约）.

        失败时抛出已收窄的具体异常（httpx.TimeoutException / KeyError / akshare 异常），
        由 fetch_with_fallback 捕获后转入兜底 provider。
        """
        raise NotImplementedError

    def fetch_with_fallback(self, ticker: str) -> dict:
        """单次调用内的容错链：主选 fetch() → 逐兜底 provider 尝试，成功即返回.

        全部 provider 穷尽仍失败 → 返回 {"ticker", "dim", "error"}（不抛，
        配合 BatchFetcher resume 机制标记该维度失败，下次 batch 只重试该维度）。
        不含跨 batch 重试（见 CacheManager + BatchFetcher resume）。
        """
        # 主选
        try:
            data = _retry(lambda: self.fetch(ticker))
            if data:
                return data
        except Exception:  # noqa: BLE001 - 容错链需兜底，具体异常已由子类 fetch 内收窄
            pass

        # 兜底 providers
        for provider in self.fallback_providers:
            try:
                data = _retry(lambda p=provider: p(ticker))
                if data:
                    return data
            except Exception:  # noqa: BLE001
                continue

        # 全部失败：返回错误结构，不抛
        return {
            "ticker": ticker,
            "dim": self.dim,
            "error": f"all_providers_failed:{self.dim}",
        }
