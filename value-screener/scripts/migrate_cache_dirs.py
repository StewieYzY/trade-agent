"""Task 4.4b (f1-deviation-fix): cache 分裂目录安全迁移.

按 4.4a 审计结果迁移带后缀目录：
- 空壳目录（无真实数据文件）→ 直接删
- 有真实数据 + 纯数字已存在 → 以纯数字为真值，后缀目录归档后删
  （本仓库 4.4a 审计：000858.SZ / 600519.SH 仅含 valuation.json，纯数字目录已有完整数据集，
   valuation.json 是历史残留，被纯数字目录覆盖，安全删除）
- 孤儿目录（含真实数据，无纯数字对应）→ 创建纯数字目录移动数据后删后缀目录
  （本仓库无此情况）

幂等：重复运行无副作用（带后缀目录已删则跳过）。

用法：
    cd value-screener && python scripts/migrate_cache_dirs.py
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
REAL_DATA_FILES = ["basic.json", "financials.json", "kline.json", "risk.json", "valuation.json"]


def _has_real_data(d: Path) -> bool:
    return any((d / f).exists() for f in REAL_DATA_FILES)


def count_json(root: Path) -> int:
    return sum(1 for _ in root.rglob("*.json") if "__pycache__" not in _.parts)


def main() -> None:
    if not CACHE_DIR.exists():
        print(f"cache dir not found: {CACHE_DIR}")
        return

    before = count_json(CACHE_DIR)
    print(f"迁移前 json 文件数（含日期子目录）：{before}")

    suffixed = sorted(
        d for d in CACHE_DIR.iterdir()
        if d.is_dir() and d.name.lower().endswith((".sh", ".sz"))
    )
    print(f"带后缀目录：{[d.name for d in suffixed]}")

    deleted = []
    migrated = []
    skipped = []

    for d in suffixed:
        pure = d.name.split(".")[0]
        pure_dir = CACHE_DIR / pure
        has_pure = pure_dir.exists()
        has_data = _has_real_data(d)

        if not has_data:
            # 空壳（含空日期子目录）→ 直接删
            shutil.rmtree(d)
            deleted.append(d.name)
            print(f"  [删空壳] {d.name}")
        elif has_pure:
            # 纯数字已存在且有数据 → 以纯数字为真值，后缀目录归档后删
            # 归档方式：把后缀目录里的真实数据文件移到 pure_dir.__suffix_archive/ 仅当
            # pure_dir 不存在同名文件（防覆盖真值）；本仓库实际只剩 valuation.json，
            # pure_dir 已有 valuation.json（更新），故直接删后缀目录。
            archive = CACHE_DIR / f"{pure}__suffix_archive"
            moved = []
            for f in REAL_DATA_FILES:
                src = d / f
                dst = pure_dir / f
                if src.exists():
                    if not dst.exists():
                        # 纯数字目录缺该文件 → 从后缀目录补（保护数据）
                        shutil.move(str(src), str(dst))
                        moved.append(f)
                    # else: 纯数字已有同名（更新值），后缀的丢弃
            # 删除后缀目录（剩余的日期子目录 + 残留）
            shutil.rmtree(d)
            migrated.append(d.name)
            print(f"  [归档后删] {d.name}（补入纯数字目录：{moved or '无，纯数字已全'}）")
            # 若 archive 为空目录则清理
            if archive.exists() and not any(archive.iterdir()):
                archive.rmdir()
        else:
            # 孤儿：含真实数据但无纯数字目录 → 创建纯数字目录移入
            pure_dir.mkdir(parents=True, exist_ok=True)
            moved = []
            for f in REAL_DATA_FILES:
                src = d / f
                if src.exists():
                    shutil.move(str(src), str(pure_dir / f))
                    moved.append(f)
            shutil.rmtree(d)
            migrated.append(d.name)
            print(f"  [孤儿迁移] {d.name} → {pure}/（移入 {moved}）")

    after = count_json(CACHE_DIR)
    print(f"\n迁移后 json 文件数：{after}（差值 {before - after}，删除的孤儿/重复 valuation.json）")
    print(f"删除空壳：{deleted}")
    print(f"归档迁移：{migrated}")
    print(f"跳过：{skipped}")

    # 验证：无带后缀目录
    remaining = [d.name for d in CACHE_DIR.iterdir()
                 if d.is_dir() and d.name.lower().endswith((".sh", ".sz"))]
    if remaining:
        print(f"⚠️  仍存在带后缀目录：{remaining}")
    else:
        print("✓ 无带后缀目录")


if __name__ == "__main__":
    main()
