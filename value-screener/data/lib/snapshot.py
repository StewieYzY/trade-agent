"""全市场快照表 intra-batch 复用 · _LazyTable.

背景（review #3 + risk pledge/audit）：
  spot_em / stock_gpzy_pledge_ratio_em / stock_audit_report_em 均为全市场表
  （~5000 行）。原实现把它们塞进 per-ticker fetch(ticker)，batch 下每只股票
  各拉一次全市场表 → 冗余请求 + 反爬封禁风险。

设计：
  _LazyTable 持有 loader，首个调用者取回并缓存 DataFrame，后续同 batch 内
  全部复用（线程安全，双检锁）。成功永久缓存（生命周期 = fetcher 实例）；
  失败进入冷却期（_FAIL_COOLDOWN 秒内直接返 None 不重试），避免对坏 endpoint
  反复重试放大请求（_retry 3 次 × N 股 → 否则 3N 次冗余命中）。
  跨 batch 的新鲜度由 CacheManager 的 per-ticker TTL 兜底。
"""
from __future__ import annotations

import threading
import time
from typing import Callable


class _LazyTable:
    """线程安全的惰性全市场表加载器."""

    _FAIL_COOLDOWN = 300.0  # 失败后 5 分钟内不重试同一全市场表

    def __init__(self, loader: Callable):
        self._loader = loader
        self._df = None
        self._failed_at: float | None = None
        self._lock = threading.Lock()

    def get(self):
        # 快路径：已缓存成功结果（无锁读，benign race）
        if self._df is not None:
            return self._df
        with self._lock:
            # 双检：拿锁后可能已被其他线程加载成功
            if self._df is not None:
                return self._df
            # 失败冷却期内直接返 None，不重试（避免对坏 endpoint 放大请求）
            if self._failed_at is not None and time.time() - self._failed_at < self._FAIL_COOLDOWN:
                return None
            try:
                self._df = self._loader()
                self._failed_at = None
                return self._df
            except Exception:
                # 失败：记冷却起点，返 None；冷却期内后续 get 不再触网
                self._failed_at = time.time()
                return None

    def reset(self) -> None:
        """清缓存与冷却（测试 / 强制刷新用）."""
        with self._lock:
            self._df = None
            self._failed_at = None
