"""g1-staged-fetch-boundary：BatchFetcher 单股/单维度失败隔离测试（spec item 3 修复）.

spec `staged-fetch-boundary` 的「单股失败隔离不回归」requirement 要求：
某 ticker 的某量化维度 fetch_with_fallback 返回 __error__ 时，其他 ticker 与
其他维度继续采集，且失败维度不写缓存（下次 resume 重试）。

本测试**不 mock 整个 BatchFetcher**，而是 mock 单个 fetcher 实例的
fetch_with_fallback，用真实 BatchFetcher().fetch_all 验证 _fetch_one / cache / resume
路径的真实失败隔离行为——补齐 screen 层 mock 无法覆盖的 fetcher 层证据。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.batch_fetcher import BatchFetcher


def test_batch_fetcher_failure_isolation_single_ticker_dim(tmp_path):
    """t1 的 basic 维度 fetch_with_fallback 返回 __error__，t2 正常 → 互不影响.

    - t1 basic: __error__（不写缓存，下次 resume 重试）
    - t2 basic: 正常数据（写缓存）
    - 断言：t1 t2 都出现在结果里；t1 结果含 __error__；t2 结果正常；
      cache.set 只对 t2 调用（t1 失败不写缓存）。
    """
    cache = MagicMock()
    cache.get.return_value = None  # 全 miss，强制走采集路径

    bf = BatchFetcher(max_workers=2, cache=cache)

    good_data = {"ticker": "600002", "name": "正常股", "market_cap": 100e8}

    def fake_fetch_with_fallback(self, ticker):
        if ticker == "600001":
            return {"ticker": ticker, "dim": "basic", "error": "all_providers_failed:basic", "__error__": True}
        return good_data

    # patch sleep 避免 _fetch_one 的 0.5-2s 反爬延迟拖慢测试
    with patch("data.lib.batch_fetcher.time") as mock_time:
        mock_time.sleep = lambda *_: None
        # patch BasicFetcher.fetch_with_fallback（实例方法）→ 真实 _fetch_one 会调它
        with patch("data.fetchers.basic.BasicFetcher.fetch_with_fallback", fake_fetch_with_fallback):
            results = bf.fetch_all(["600001", "600002"], dimensions=["basic"])

    # 两只都出现，互不阻断
    assert set(results.keys()) == {"600001", "600002"}, f"失败 ticker 不应阻断其他 ticker，got {set(results.keys())}"

    # t1 basic 失败：结果含 __error__
    t1_basic = results["600001"]["basic"]
    assert isinstance(t1_basic, dict) and t1_basic.get("__error__") is True, (
        f"失败维度应返回 __error__ 结构，got {t1_basic}"
    )

    # t2 basic 正常
    t2_basic = results["600002"]["basic"]
    assert t2_basic == good_data, f"正常 ticker 应拿到正常数据，got {t2_basic}"

    # cache.set 只对 t2 调用（t1 __error__ 不写缓存，下次 resume 重试）
    set_calls = [c for c in cache.set.call_args_list]
    set_tickers = [c.args[0] for c in set_calls if len(c.args) >= 1]
    assert "600001" not in set_tickers, "失败维度不应写缓存（破坏 resume 重试）"
    assert "600002" in set_tickers, "成功维度应写缓存"


def test_batch_fetcher_failure_in_one_dim_does_not_block_other_dim(tmp_path):
    """同一 ticker 的 basic 失败，其 financials 维度仍正常采集（跨维度隔离）.

    单只 ticker，两维度：basic 返 __error__，financials 返正常数据。
    断言两维度互不阻断，basic 失败不写缓存、financials 写缓存。
    """
    cache = MagicMock()
    cache.get.return_value = None

    bf = BatchFetcher(max_workers=2, cache=cache)

    fin_data = {"years": ["2022"], "income": {"net_profit": [100]}}

    def fake_basic(self, ticker):
        return {"ticker": ticker, "dim": "basic", "error": "failed", "__error__": True}

    def fake_financials(self, ticker):
        return fin_data

    with patch("data.lib.batch_fetcher.time") as mock_time:
        mock_time.sleep = lambda *_: None
        with patch("data.fetchers.basic.BasicFetcher.fetch_with_fallback", fake_basic), \
             patch("data.fetchers.financials.FinancialsFetcher.fetch_with_fallback", fake_financials):
            results = bf.fetch_all(["600001"], dimensions=["basic", "financials"])

    t = results["600001"]
    assert t["basic"].get("__error__") is True
    assert t["financials"] == fin_data

    # basic 失败不写缓存，financials 成功写缓存
    set_dims = [c.args[1] for c in cache.set.call_args_list if len(c.args) >= 2]
    assert "basic" not in set_dims, "失败维度不应写缓存"
    assert "financials" in set_dims, "成功维度应写缓存"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
