"""Tests for scout/quality.py (tasks 6.9, 6.10)."""
import sys
from pathlib import Path
import tempfile
import time
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scout.quality import ScoutCache


def test_scout_cache_set_get():
    """验证 ScoutCache set/get 基本功能."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        ticker = "600519"
        date_str = "2026-06-29"

        result = {
            "verdict": "deep_dive",
            "confidence": 85,
            "one_liner": "优质白酒企业",
            "red_flags": [],
            "green_flags": ["ROE > 25%"],
            "anti_trap_flags": [],
        }

        input_snapshot = {
            "pe_ttm": 38.5,
            "pb": 8.2,
            "roe_3y": [28.5, 25.3, 22.1],
            "market_cap": 20000,
        }

        cache.set(ticker, date_str, result, input_snapshot)

        # 验证缓存可以读取
        cached = cache.get(ticker, date_str)
        assert cached is not None
        assert cached["verdict"] == "deep_dive"
        assert cached["confidence"] == 85
        assert cached["one_liner"] == "优质白酒企业"
        assert cached["input_snapshot"]["pe_ttm"] == 38.5
        assert cached["input_snapshot"]["market_cap"] == 20000
        assert "timestamp" in cached


def test_scout_cache_ttl():
    """验证 ScoutCache TTL=24h 过期."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        ticker = "000001"
        date_str = "2026-06-29"

        result = {"verdict": "watch", "confidence": 50}
        input_snapshot = {"pe_ttm": 20.0}

        cache.set(ticker, date_str, result, input_snapshot)

        # 验证缓存可以读取
        cached = cache.get(ticker, date_str)
        assert cached is not None

        # 模拟过期：修改文件 mtime 到 25 小时前
        cache_path = cache._path(ticker, date_str)
        old_time = time.time() - 25 * 3600  # 25 小时前
        cache_path.touch()
        import os
        os.utime(cache_path, (old_time, old_time))

        # 验证过期后返回 None
        cached = cache.get(ticker, date_str)
        assert cached is None


def test_scout_cache_date_isolation():
    """验证不同日期的缓存互不影响（跨日隔离）."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        ticker = "600519"

        # 写入 2026-06-29 的缓存
        result_0629 = {"verdict": "deep_dive", "confidence": 85}
        snapshot_0629 = {"pe_ttm": 38.5}
        cache.set(ticker, "2026-06-29", result_0629, snapshot_0629)

        # 写入 2026-06-30 的缓存
        result_0630 = {"verdict": "watch", "confidence": 55}
        snapshot_0630 = {"pe_ttm": 42.0}
        cache.set(ticker, "2026-06-30", result_0630, snapshot_0630)

        # 验证两个日期的缓存独立存在
        cached_0629 = cache.get(ticker, "2026-06-29")
        cached_0630 = cache.get(ticker, "2026-06-30")

        assert cached_0629 is not None
        assert cached_0630 is not None
        assert cached_0629["verdict"] == "deep_dive"
        assert cached_0630["verdict"] == "watch"
        assert cached_0629["input_snapshot"]["pe_ttm"] == 38.5
        assert cached_0630["input_snapshot"]["pe_ttm"] == 42.0


def test_scout_cache_missing():
    """验证 ScoutCache 读取不存在的缓存返回 None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        cached = cache.get("999999", "2026-06-29")
        assert cached is None


def test_scout_cache_corrupted():
    """验证 ScoutCache 读取损坏的缓存返回 None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        ticker = "600519"
        date_str = "2026-06-29"

        # 写入损坏的 JSON
        cache_path = cache._path(ticker, date_str)
        cache_path.write_text('{"verdict": "deep_dive"', encoding="utf-8")  # 缺少闭合

        # 验证损坏的缓存返回 None
        cached = cache.get(ticker, date_str)
        assert cached is None


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
