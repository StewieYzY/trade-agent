"""Tests for scout/batch.py (tasks 6.7, 6.8, 6.11)."""
import sys
from pathlib import Path
import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scout.batch import scout_batch, call_llm_snapshot

# f1-deviation-fix §7：call_llm（含 call_llm_light/call_llm_snapshot 别名）返回 (content, usage)
LLM_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


# ── P1 修复（review 反馈）：scout_batch 返回 (shortlist, usage_summary)，累加所有 LLM 调用 ──

def test_scout_batch_returns_tuple_with_usage_summary():
    """scout_batch 返回 (shortlist, usage_summary)，usage_summary 含所有调用的 token（非仅 deep_dive）."""
    candidates = [{"ticker": "600001"}, {"ticker": "600002"}, {"ticker": "600003"}]
    call_seq = ["deep_dive", "watch", "skip"]  # 第 1 次 deep_dive、第 2 次 watch、第 3 次 skip
    call_idx = {"i": 0}

    async def mock_call(snapshot, system):
        # 按调用次序返回不同 verdict，验证 watch/skip 的 usage 也被累加（非仅 deep_dive）
        verdict = call_seq[call_idx["i"] % len(call_seq)]
        call_idx["i"] += 1
        return (json.dumps({
            "verdict": verdict,
            "confidence": 80,
            "one_liner": "test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = {"name": "x", "market_cap": 1, "pe_ttm": 10,
                                          "roe_3y": [1, 2, 3], "net_margin": 5}
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache_cls.return_value.get.return_value = None
                result = asyncio.run(scout_batch(candidates, force=True))

    # 返回 tuple
    assert isinstance(result, tuple)
    assert len(result) == 2
    shortlist, usage = result
    # shortlist 只含 deep_dive（1 只）
    assert len(shortlist) == 1
    assert shortlist[0]["ticker"] == "600001"
    # usage_summary 累加了所有 3 次调用（deep_dive + watch + skip），不是只 1 次
    assert usage["call_count"] == 3
    assert usage["prompt_tokens"] == 300  # 3 × 100
    assert usage["completion_tokens"] == 150  # 3 × 50
    assert usage["total_tokens"] == 450  # 3 × 150


def test_scout_batch_usage_summary_counts_cache_hits_separately():
    """cache hit 不产生新 LLM 调用（不计入 call_count），但 cache_hits 单独计数."""
    candidates = [{"ticker": "600001"}, {"ticker": "600002"}]

    async def mock_call(snapshot, system):
        return (json.dumps({"verdict": "deep_dive", "confidence": 80, "one_liner": "t",
                            "red_flags": [], "green_flags": [], "anti_trap_flags": []}),
                {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot"):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                # 600001 cache hit（含 usage），600002 cache miss
                def cache_get(ticker, date_str):
                    if ticker == "600001":
                        return {"verdict": "deep_dive", "confidence": 80, "one_liner": "cached",
                                "red_flags": [], "green_flags": [], "anti_trap_flags": []}
                    return None
                mock_cache.get.side_effect = cache_get
                shortlist, usage = asyncio.run(scout_batch(candidates, force=False))

    # 600001 cache hit → 不调 LLM；600002 cache miss → 调 1 次
    assert usage["call_count"] == 1
    assert usage["cache_hits"] == 1
    assert usage["prompt_tokens"] == 100  # 仅 600002 的 1 次


def test_scout_batch_top20_cap():
    """验证 top-20 cap: 40 只 deep_dive 只返回前 20."""
    # 创建 40 只候选，全部返回 deep_dive（confidence 从 100 到 61）
    candidates = [{"ticker": f"600{i:03d}"} for i in range(40)]

    async def mock_call(snapshot, system):
        # 根据 ticker 生成不同的 confidence
        ticker = snapshot.split("(")[1].split(")")[0]
        idx = int(ticker[3:])
        confidence = 100 - idx
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": confidence,
            "one_liner": f"Stock {ticker}",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            # Mock assemble_snapshot 返回基本特征
            mock_assemble.return_value = {
                "ticker": "600000",
                "name": "测试股票",
                "industry": "测试行业",
                "market_cap": 1000,
                "pe_ttm": 20.0,
                "pb": 2.0,
                "pe_percentile_5y": 50.0,
                "roe_3y": [15.0, 16.0, 17.0],
                "roe_trend": "趋势上升",
                "net_margin": 10.0,
                "debt_ratio": 50.0,
                "goodwill_ratio": 5.0,
                "operating_cashflow": 100.0,
                "net_profit": 80.0,
                "cashflow_match": "匹配",
                "revenue_growth": 10.0,
                "pledge_ratio": 10.0,
                "price_change_60d": 5.0,
                "turnover_avg_percentile_60d": 50.0,
                "f_score": 7,
            }

            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None  # 缓存未命中

                result, _usage = asyncio.run(scout_batch(candidates, force=True))

                # 验证只返回 20 只
                assert len(result) == 20
                # 验证按 confidence 降序排序
                confidences = [r["confidence"] for r in result]
                assert confidences == sorted(confidences, reverse=True)


def test_scout_batch_error_handling():
    """验证 per-candidate error handling: LLM 调用失败不阻塞整批."""
    candidates = [
        {"ticker": "600001"},
        {"ticker": "600002"},
        {"ticker": "600003"},
    ]

    async def mock_call(snapshot, system):
        ticker = snapshot.split("(")[1].split(")")[0]
        if ticker == "600002":
            raise httpx.HTTPStatusError("LLM API error", request=None, response=None)
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": f"Stock {ticker}",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    def mock_assemble(ticker, cache_manager=None):
        return {
            "ticker": ticker,
            "name": "测试股票",
            "industry": "测试行业",
            "market_cap": 1000,
            "pe_ttm": 20.0,
            "pb": 2.0,
            "pe_percentile_5y": 50.0,
            "roe_3y": [15.0, 16.0, 17.0],
            "roe_trend": "趋势上升",
            "net_margin": 10.0,
            "debt_ratio": 50.0,
            "goodwill_ratio": 5.0,
            "operating_cashflow": 100.0,
            "net_profit": 80.0,
            "cashflow_match": "匹配",
            "revenue_growth": 10.0,
            "pledge_ratio": 10.0,
            "price_change_60d": 5.0,
            "turnover_avg_percentile_60d": 50.0,
            "f_score": 7,
        }

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None

                result, _usage = asyncio.run(scout_batch(candidates, force=True))

                # 验证只有 2 只成功（600002 失败）
                assert len(result) == 2
                tickers = [r["ticker"] for r in result]
                assert "600001" in tickers
                assert "600003" in tickers
                assert "600002" not in tickers


def test_scout_batch_insufficient_data():
    """验证 insufficient data handling: 数据不足的候选被跳过."""
    candidates = [
        {"ticker": "600001"},
        {"ticker": "600002"},  # 数据不足
        {"ticker": "600003"},
    ]

    def mock_assemble(ticker, cache_manager=None):
        if ticker == "600002":
            return {"error": "insufficient_data", "missing_fields": ["name", "industry"]}
        return {
            "ticker": ticker,
            "name": "测试股票",
            "industry": "测试行业",
            "market_cap": 1000,
            "pe_ttm": 20.0,
            "pb": 2.0,
            "pe_percentile_5y": 50.0,
            "roe_3y": [15.0, 16.0, 17.0],
            "roe_trend": "趋势上升",
            "net_margin": 10.0,
            "debt_ratio": 50.0,
            "goodwill_ratio": 5.0,
            "operating_cashflow": 100.0,
            "net_profit": 80.0,
            "cashflow_match": "匹配",
            "revenue_growth": 10.0,
            "pledge_ratio": 10.0,
            "price_change_60d": 5.0,
            "turnover_avg_percentile_60d": 50.0,
            "f_score": 7,
        }

    async def mock_call(snapshot, system):
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": "Test stock",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot", new=mock_assemble):
            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None

                result, _usage = asyncio.run(scout_batch(candidates, force=True))

                # 验证只有 2 只成功（600002 数据不足）
                assert len(result) == 2
                tickers = [r["ticker"] for r in result]
                assert "600001" in tickers
                assert "600003" in tickers
                assert "600002" not in tickers


def test_scout_batch_cache_hit():
    """验证缓存命中: 缓存有效的候选不调用 LLM."""
    candidates = [
        {"ticker": "600001"},
        {"ticker": "600002"},
    ]

    with patch("scout.batch.ScoutCache") as mock_cache_cls:
        mock_cache = mock_cache_cls.return_value

        # 600001 缓存命中，600002 缓存未命中
        def mock_get(ticker, date_str):
            if ticker == "600001":
                return {
                    "verdict": "deep_dive",
                    "confidence": 90,
                    "one_liner": "Cached result",
                    "red_flags": [],
                    "green_flags": [],
                    "anti_trap_flags": [],
                }
            return None

        mock_cache.get.side_effect = mock_get

        async def mock_call(snapshot, system):
            return (json.dumps({
                "verdict": "deep_dive",
                "confidence": 80,
                "one_liner": "Fresh result",
                "red_flags": [],
                "green_flags": [],
                "anti_trap_flags": [],
            }), LLM_USAGE)

        with patch("scout.batch.call_llm_snapshot", new=mock_call):
            with patch("scout.batch.assemble_snapshot") as mock_assemble:
                mock_assemble.return_value = {
                    "ticker": "600002",
                    "name": "测试股票",
                    "industry": "测试行业",
                    "market_cap": 1000,
                    "pe_ttm": 20.0,
                    "pb": 2.0,
                    "pe_percentile_5y": 50.0,
                    "roe_3y": [15.0, 16.0, 17.0],
                    "roe_trend": "趋势上升",
                    "net_margin": 10.0,
                    "debt_ratio": 50.0,
                    "goodwill_ratio": 5.0,
                    "operating_cashflow": 100.0,
                    "net_profit": 80.0,
                    "cashflow_match": "匹配",
                    "revenue_growth": 10.0,
                    "pledge_ratio": 10.0,
                    "price_change_60d": 5.0,
                    "turnover_avg_percentile_60d": 50.0,
                    "f_score": 7,
                }

                result, _usage = asyncio.run(scout_batch(candidates, force=False))

                # 验证 2 只都返回
                assert len(result) == 2
                # 验证 600001 来自缓存
                r_600001 = next(r for r in result if r["ticker"] == "600001")
                assert r_600001["confidence"] == 90
                assert r_600001.get("from_cache") is True
                # 验证 600002 是新调用
                r_600002 = next(r for r in result if r["ticker"] == "600002")
                assert r_600002["confidence"] == 80


def test_call_llm_snapshot_env_validation():
    """验证 call_llm_snapshot 环境变量校验（fail-fast）."""
    with patch.dict("os.environ", {}, clear=True):
        # 缺少所有环境变量
        try:
            asyncio.run(call_llm_snapshot("test snapshot", "test prompt"))
            assert False, "Should raise ValueError"
        except ValueError as e:
            assert "missing required env var" in str(e)


def test_scout_batch_cache_write_failure():
    """验证 cache.set OSError 不丢结果（LLM 已调用，结果应返回）."""
    candidates = [{"ticker": "600001"}]

    async def mock_call(snapshot, system):
        return (json.dumps({
            "verdict": "deep_dive",
            "confidence": 90,
            "one_liner": "Test",
            "red_flags": [],
            "green_flags": [],
            "anti_trap_flags": [],
        }), LLM_USAGE)

    with patch("scout.batch.call_llm_snapshot", new=mock_call):
        with patch("scout.batch.assemble_snapshot") as mock_assemble:
            mock_assemble.return_value = {
                "ticker": "600001",
                "name": "测试股票",
                "industry": "测试行业",
                "market_cap": 1000,
                "pe_ttm": 20.0,
                "pb": 2.0,
                "pe_percentile_5y": 50.0,
                "roe_3y": [15.0, 16.0, 17.0],
                "roe_trend": "趋势上升",
                "net_margin": 10.0,
                "debt_ratio": 50.0,
                "goodwill_ratio": 5.0,
                "operating_cashflow": 100.0,
                "net_profit": 80.0,
                "cashflow_match": "匹配",
                "revenue_growth": 10.0,
                "pledge_ratio": 10.0,
                "price_change_60d": 5.0,
                "turnover_avg_percentile_60d": 50.0,
                "f_score": 7,
            }

            with patch("scout.batch.ScoutCache") as mock_cache_cls:
                mock_cache = mock_cache_cls.return_value
                mock_cache.get.return_value = None
                mock_cache.set.side_effect = OSError("Disk full")

                result, _usage = asyncio.run(scout_batch(candidates, force=True))

                # 即使缓存写入失败，结果仍然返回
                assert len(result) == 1
                assert result[0]["ticker"] == "600001"
                assert result[0]["verdict"] == "deep_dive"
                assert result[0]["confidence"] == 90


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
