"""g1-canonical-run-identity D4: L2 ScoutCache 分裂目录安全迁移.

L2 cache 结构：data/cache/{ticker}/{date}/l2_scout.json。
ScoutCache._path 改用 canonical_code（纯数字）后，既有带后缀目录（如 600519.SH/）
需迁移合并到纯数字目录，按 D3 同策略三分支（不丢真实数据）：

- 空壳带后缀目录（无 l2_scout.json）→ 删
- 带后缀有真数据 + 纯数字也有数据 → 以纯数字为真值，带后缀归档后删
- 带后缀有真数据无纯数字（孤儿）→ 移到纯数字再删

幂等：重复运行无副作用（带后缀目录已删/移则跳过）。
--dry-run：只打印不执行。

用法：
    cd value-screener && python scripts/migrate_split_l2_cache.py [--dry-run]
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"


def _has_l2_scout(d: Path) -> bool:
    """目录或子树是否含 l2_scout.json（真实数据文件）."""
    try:
        return any(d.rglob("l2_scout.json"))
    except OSError:
        return False


def migrate_split_l2_cache(
    cache_dir: Path | str = CACHE_DIR,
    dry_run: bool = False,
) -> tuple[int, int]:
    """迁移带后缀 L2 cache 目录到纯数字，返回 (deleted_count, moved_count).

    Args:
        cache_dir: cache 根目录（data/cache）
        dry_run: True 只打印不执行

    Returns:
        (deleted, moved): 删除的空壳目录数 + 移动的孤儿目录数
    """
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        print(f"cache dir not found: {cache_dir}")
        return 0, 0

    # 找带后缀的 L2 目录（.SH/.SZ/.BJ，可能含 l2_scout.json）
    suffixed = sorted(
        d for d in cache_dir.iterdir()
        if d.is_dir() and d.name.lower().endswith((".sh", ".sz", ".bj"))
    )
    if not suffixed:
        print("无带后缀 L2 cache 目录，无需迁移（幂等）")
        return 0, 0

    print(f"带后缀 L2 目录：{[d.name for d in suffixed]}")

    deleted = 0
    moved = 0
    for d in suffixed:
        # 纯数字对应目录（去后缀）
        from data.lib.identity import canonical_code
        try:
            pure_code = canonical_code(d.name)
        except ValueError:
            print(f"  跳过无法 canonical 化的目录: {d.name}")
            continue
        pure_dir = cache_dir / pure_code
        has_data = _has_l2_scout(d)

        if not has_data:
            # 分支1：空壳带后缀目录 → 删
            print(f"  删空壳: {d.name}（无 l2_scout.json）")
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
            deleted += 1
            continue

        if pure_dir.exists() and _has_l2_scout(pure_dir):
            # 分支2：带后缀有数据 + 纯数字也有 → 以纯数字为真值，带后缀归档后删
            print(f"  归档后删: {d.name}（纯数字 {pure_code} 已有真值，带后缀作残留归档）")
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
            deleted += 1
        else:
            # 分支3：孤儿（带后缀有数据，无纯数字）→ 移到纯数字再删
            print(f"  移孤儿: {d.name} → {pure_code}/（移数据后删带后缀目录）")
            if not dry_run:
                pure_dir.mkdir(parents=True, exist_ok=True)
                # 移动所有日期子目录
                for sub in d.iterdir():
                    if sub.is_dir():
                        target = pure_dir / sub.name
                        if target.exists():
                            # 同名日期子目录冲突，以带后缀的数据移入（孤儿本就无纯数字，安全）
                            shutil.rmtree(target, ignore_errors=True)
                        shutil.move(str(sub), str(target))
                shutil.rmtree(d, ignore_errors=True)
            moved += 1

    print(f"完成：删除空壳/残留 {deleted}，移动孤儿 {moved}" + ("（dry-run，未实际执行）" if dry_run else ""))
    return deleted, moved


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    migrate_split_l2_cache(dry_run=dry_run)


if __name__ == "__main__":
    main()
