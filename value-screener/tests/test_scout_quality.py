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


# ============================================================
# g1-canonical-run-identity: ScoutCache 路径 canonical.code + run identity 绑定
# ============================================================

def _basic_result():
    """构造一份基本 L2 result."""
    return {
        "verdict": "deep_dive", "confidence": 75,
        "one_liner": "test", "red_flags": [], "green_flags": [],
        "anti_trap_flags": [], "low_confidence_anomaly": False,
    }


def _basic_snapshot():
    """构造一份 input_snapshot（21 字段特征值的子集）."""
    return {
        "ticker": "600519", "name": "贵州茅台", "industry": "白酒",
        "market_cap": 14887.97, "pe_ttm": 17.92, "pb": 5.47,
        "roe_3y": [28.5, 25.3, 22.1],
    }


def test_scout_cache_path_uses_canonical_code():
    """_path("600519.SH") 与 _path("600519") 返回相同路径（纯数字 600519）.

    对应 scout-agent MODIFIED: Cache path uses canonical code not raw ticker。
    消除 600519/600519.SH 双目录分裂。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        p1 = cache._path("600519.SH", "2026-07-21")
        p2 = cache._path("600519", "2026-07-21")
        p3 = cache._path("600519.sh", "2026-07-21")  # 小写后缀
        assert p1 == p2 == p3, "同证券不同形式 MUST 返回相同 cache 路径"
        assert "600519" in str(p1), "路径 SHALL 含纯数字 canonical code"
        assert "600519.SH" not in str(p1), "MUST NOT 用带后缀形式建目录"
        assert "600519.sh" not in str(p1)
        assert p1.name == "l2_scout.json"


def test_scout_cache_no_split_dir_created():
    """写 600519.SH 不创建 600519.SH/ 目录，只创建 600519/."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        cache.set("600519.SH", "2026-07-21", _basic_result(), _basic_snapshot())
        base = Path(tmpdir)
        assert (base / "600519" / "2026-07-21" / "l2_scout.json").exists(), \
            "SHALL 用纯数字 600519 建目录"
        assert not (base / "600519.SH").exists(), "MUST NOT 创建 600519.SH/ 目录"


def test_scout_cache_entry_binds_run_identity():
    """set() 写入的 cache entry 含 run_id/profile_version/input_ticker_set_hash.

    对应 scout-agent MODIFIED: Cache structure SHALL include run identity fields.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        cache.set(
            "600519.SH", "2026-07-21", _basic_result(), _basic_snapshot(),
            run_id="abc123def456",
            profile_version="g1-2026-07-21",
            input_ticker_set_hash="hash78901234",
        )
        cached = cache.get("600519.SH", "2026-07-21")
        assert cached is not None
        assert cached.get("run_id") == "abc123def456"
        assert cached.get("profile_version") == "g1-2026-07-21"
        assert cached.get("input_ticker_set_hash") == "hash78901234"


def test_scout_cache_existing_21_fields_preserved():
    """cache entry 仍含既有 input_snapshot + timestamp + verdict，run identity 是补充.

    对应 scout-agent MODIFIED: 既有 input_snapshot 保留作诊断用途不动。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        cache.set(
            "600519", "2026-07-21", _basic_result(), _basic_snapshot(),
            run_id="rid", profile_version="pv", input_ticker_set_hash="ih",
        )
        cached = cache.get("600519", "2026-07-21")
        assert cached is not None
        assert cached.get("verdict") == "deep_dive"
        assert cached.get("confidence") == 75
        assert cached.get("input_snapshot") == _basic_snapshot(), "input_snapshot MUST 保留"
        assert cached.get("timestamp"), "timestamp MUST 保留（ISO 格式）"
        assert cached.get("run_id") == "rid"


def test_scout_cache_clear_uses_canonical_code():
    """clear(ticker=...) 用 canonical_code 定位目录，传 600519.SH SHALL 清掉 600519/ 目录.

    对应 scout-agent MODIFIED: Cache path uses canonical code not raw ticker。
    修复 clear() 的 canonical bug——原用原始 ticker 拼目录，传带后缀形式清不到
    canonical 化后的纯数字目录。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        # 用纯数字写入（canonical 目录 600519/）
        cache.set("600519", "2026-07-21", _basic_result(), _basic_snapshot(),
                  run_id="rid", profile_version="pv", input_ticker_set_hash="ih")
        base = Path(tmpdir)
        assert (base / "600519" / "2026-07-21" / "l2_scout.json").exists()

        # 用带后缀 ticker 调 clear —— SHALL 命中纯数字 600519/ 目录
        deleted = cache.clear(ticker="600519.SH", date_str="2026-07-21")
        assert deleted == 1, "clear(600519.SH) SHALL 命中 canonical 化的 600519/ 目录"
        assert not (base / "600519" / "2026-07-21" / "l2_scout.json").exists(), \
            "clear 后文件 SHALL 被删除"


def test_scout_cache_hit_across_different_runs_same_profile():
    """不同 run_id 同 profile_version 同 ticker 同日 SHALL cache hit（run_id 不参与 hit 判定）.

    对应 scout-agent MODIFIED 24h Cache: #### Scenario: Cross-run cache hit when profile_version unchanged。
    G1-3 误把 run_id 用作 hit 判定（不同 run_id → miss）破坏 24h 复用，本测试验证修复后语义：
    run_id 降级为 provenance，cache hit 只校验 TTL + profile_version。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        # run A 写入（run_id=run_a_rid, profile_version=V）
        cache.set("600519", "2026-07-21", _basic_result(), _basic_snapshot(),
                  run_id="run_a_rid", profile_version="g1-2026-07-21",
                  input_ticker_set_hash="ih_a")

        # run B（不同 run_id）同 profile_version 调 get → SHALL cache hit（不传 run_id）
        cached_b = cache.get("600519", "2026-07-21",
                            profile_version="g1-2026-07-21")
        assert cached_b is not None, "不同 run_id 同 profile_version SHALL cache hit（run_id 不参与判定）"
        assert cached_b.get("run_id") == "run_a_rid", "hit 返回的 entry 保留 source run_id（provenance）"


def test_scout_cache_miss_when_profile_version_changed():
    """profile_version 不同（规则 bump）SHALL cache miss，不复用旧规则 verdict.

    对应 scout-agent MODIFIED: #### Scenario: Cache miss when profile_version changed。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        cache.set("600519", "2026-07-21", _basic_result(), _basic_snapshot(),
                  run_id="rid", profile_version="g1-2026-07-21",
                  input_ticker_set_hash="ih")
        # profile_version 不同（规则 bump）
        cached = cache.get("600519", "2026-07-21",
                           profile_version="g1-2026-08-01")
        assert cached is None, "profile_version 不匹配 SHALL miss（规则变了不复用旧 verdict）"


def test_scout_cache_legacy_without_profile_version_misses():
    """legacy cache 无 profile_version 字段，当前 run 传 profile_version → SHALL miss.

    对应 scout-agent MODIFIED: #### Scenario: Legacy cache without profile_version misses。
    无法证明规则版本兼容，避免新规则 run 静默复用规则版本不明的旧 verdict。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        # 手写一个 legacy cache entry（无 profile_version 字段，模拟 G1-3 前的 cache）
        legacy_p = cache._path("600519", "2026-07-21")
        legacy_p.parent.mkdir(parents=True, exist_ok=True)
        legacy_p.write_text(json.dumps({
            **_basic_result(), "input_snapshot": _basic_snapshot(),
            "timestamp": "2026-07-21T10:00:00",
            # 无 profile_version 字段（legacy）
        }), encoding="utf-8")

        # 当前 run 传 profile_version → SHALL miss（无法证明兼容）
        cached = cache.get("600519", "2026-07-21",
                           profile_version="g1-2026-07-21")
        assert cached is None, "legacy cache 无 profile_version SHALL miss（无法证明规则版本兼容）"


def test_scout_cache_hit_preserves_source_run_id():
    """cache hit 返回 run A 的 entry（run_id=rid_a），cache 文件 SHALL NOT 被改写.

    对应 scout-agent MODIFIED: #### Scenario: Cache hit preserves source run_id。
    source run_id 保留作 provenance，cache hit 不改写 cache 文件。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = ScoutCache(base_dir=tmpdir)
        cache.set("600519", "2026-07-21", _basic_result(), _basic_snapshot(),
                  run_id="run_a_rid", profile_version="g1-2026-07-21",
                  input_ticker_set_hash="ih_a")
        cache_p = cache._path("600519", "2026-07-21")
        content_before = cache_p.read_text(encoding="utf-8")

        # run B cache hit（不同 run_id，同 profile_version）
        cached_b = cache.get("600519", "2026-07-21",
                            profile_version="g1-2026-07-21")
        assert cached_b is not None
        assert cached_b.get("run_id") == "run_a_rid", "source run_id 保留不改写"

        # cache 文件内容 SHALL NOT 被改写（hit 不重写文件）
        content_after = cache_p.read_text(encoding="utf-8")
        assert content_before == content_after, "cache hit SHALL NOT 改写 cache 文件（保留 source provenance）"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
