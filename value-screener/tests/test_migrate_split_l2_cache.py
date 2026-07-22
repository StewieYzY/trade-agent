"""g1-canonical-run-identity D4: L2 ScoutCache 分裂目录安全迁移测试.

迁移带后缀的 L2 cache 目录到纯数字（canonical.code），D3 同策略三分支：
- 空壳带后缀目录（无 l2_scout.json）→ 删
- 带后缀有真数据 + 纯数字也有数据 → 以纯数字为真值，带后缀归档后删
- 带后缀有真数据无纯数字（孤儿）→ 移到纯数字再删
不丢真实数据；幂等；--dry-run 只打印不执行。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.migrate_split_l2_cache import migrate_split_l2_cache


def _write_l2(cache_dir: Path, ticker_dir: str, date_str: str, verdict="deep_dive", confidence=75):
    """写一份 L2 cache entry 到 cache_dir/{ticker_dir}/{date}/l2_scout.json."""
    p = cache_dir / ticker_dir / date_str / "l2_scout.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "verdict": verdict, "confidence": confidence,
        "one_liner": "x", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
        "input_snapshot": {"pe_ttm": 20}, "timestamp": "2026-07-21T10:00:00",
    }), encoding="utf-8")
    return p


class TestMigrateSplitL2Cache:
    def test_empty_shell_suffixed_dir_deleted(self, tmp_path):
        """空壳带后缀目录（无 l2_scout.json）→ 删."""
        cache = tmp_path / "cache"
        (cache / "600519.SH" / "2026-07-21").mkdir(parents=True)  # 空目录（无 l2_scout.json）

        deleted, moved = migrate_split_l2_cache(cache_dir=cache, dry_run=False)

        assert not (cache / "600519.SH").exists(), "空壳带后缀目录 SHALL 删"
        assert deleted >= 1

    def test_suffixed_with_data_and_pure_digit_exists_pure_digit_wins(self, tmp_path):
        """带后缀有真数据 + 纯数字也有 → 以纯数字为真值，带后缀归档后删."""
        cache = tmp_path / "cache"
        _write_l2(cache, "600519", "2026-07-21", verdict="deep_dive", confidence=90)  # 纯数字真值
        _write_l2(cache, "600519.SH", "2026-07-21", verdict="watch", confidence=50)  # 带后缀残留

        deleted, moved = migrate_split_l2_cache(cache_dir=cache, dry_run=False)

        # 纯数字保留（真值）
        pure = cache / "600519" / "2026-07-21" / "l2_scout.json"
        assert pure.exists(), "纯数字目录 SHALL 保留（真值）"
        pure_data = json.loads(pure.read_text(encoding="utf-8"))
        assert pure_data["confidence"] == 90, "纯数字为真值（confidence=90），MUST NOT 被带后缀覆盖"
        # 带后缀删
        assert not (cache / "600519.SH").exists(), "带后缀目录 SHALL 归档后删"

    def test_orphan_suffixed_with_data_moved_to_pure_digit(self, tmp_path):
        """带后缀有真数据无纯数字（孤儿）→ 移到纯数字再删，不丢数据."""
        cache = tmp_path / "cache"
        orphan = _write_l2(cache, "600519.SH", "2026-07-21", verdict="deep_dive", confidence=85)
        assert not (cache / "600519").exists()  # 无纯数字对应（孤儿）

        deleted, moved = migrate_split_l2_cache(cache_dir=cache, dry_run=False)

        # 数据移到纯数字目录
        moved_to = cache / "600519" / "2026-07-21" / "l2_scout.json"
        assert moved_to.exists(), "孤儿数据 SHALL 移到纯数字目录"
        moved_data = json.loads(moved_to.read_text(encoding="utf-8"))
        assert moved_data["confidence"] == 85, "孤儿真实数据 MUST NOT 丢失"
        assert not (cache / "600519.SH").exists(), "带后缀孤儿目录移后删"

    def test_migrate_idempotent(self, tmp_path):
        """迁移幂等，二次运行无操作."""
        cache = tmp_path / "cache"
        _write_l2(cache, "600519.SH", "2026-07-21")  # 孤儿，第一次会移走

        d1, m1 = migrate_split_l2_cache(cache_dir=cache, dry_run=False)
        d2, m2 = migrate_split_l2_cache(cache_dir=cache, dry_run=False)  # 二次无带后缀目录

        assert d2 == 0 and m2 == 0, "二次运行幂等，无操作"

    def test_dry_run_does_not_execute(self, tmp_path):
        """--dry-run 模式只打印不执行."""
        cache = tmp_path / "cache"
        (cache / "600519.SH" / "2026-07-21").mkdir(parents=True)  # 空壳

        deleted, moved = migrate_split_l2_cache(cache_dir=cache, dry_run=True)

        # dry-run 不删
        assert (cache / "600519.SH").exists(), "dry-run SHALL 不执行删除"
        # 但报告了会删的数量
        assert deleted >= 1, "dry-run SHALL 报告待删数量"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
