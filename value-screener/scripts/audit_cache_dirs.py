"""Task 4.4a (f1-deviation-fix): cache 目录分裂审计.

扫描 data/cache/ 下所有带后缀目录（.SH/.SZ/.sh/.sz），对每个检查是否含真实数据文件
（basic.json/financials.json/kline.json/risk.json/valuation.json），标记为"空壳"或"有真实数据"，
并标出孤儿目录（无纯数字对应的）。

输出：scripts/repro_out/cache_dir_audit.md

用法：
    cd value-screener && python scripts/audit_cache_dirs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
REAL_DATA_FILES = ["basic.json", "financials.json", "kline.json", "risk.json", "valuation.json"]
OUT = Path(__file__).resolve().parent / "repro_out" / "cache_dir_audit.md"


def _has_real_data(d: Path) -> tuple[bool, list[str]]:
    """目录是否含真实数据文件，返回 (has_data, files_present)."""
    present = [f for f in REAL_DATA_FILES if (d / f).exists()]
    return bool(present), present


def main() -> None:
    if not CACHE_DIR.exists():
        print(f"cache dir not found: {CACHE_DIR}")
        return

    # 所有带后缀目录
    suffixed = sorted(
        d for d in CACHE_DIR.iterdir()
        if d.is_dir() and d.name.lower().endswith((".sh", ".sz"))
    )

    lines = ["# Cache 目录分裂审计（f1-deviation-fix §4.4a）", ""]
    lines.append(f"扫描目录：`{CACHE_DIR}`")
    lines.append(f"带后缀目录数：{len(suffixed)}")
    lines.append("")

    if not suffixed:
        lines.append("无带后缀目录，无需迁移。")
        OUT.write_text("\n".join(lines), encoding="utf-8")
        print("无带后缀目录")
        return

    lines.append("| 带后缀目录 | 纯数字对应 | 含真实数据 | 数据文件 | 处置 |")
    lines.append("|---|---|---|---|---|")

    orphans = []
    shells = []
    real_with_pure = []
    real_orphan = []

    for d in suffixed:
        pure = d.name.split(".")[0]
        pure_dir = CACHE_DIR / pure
        has_pure = pure_dir.exists()
        has_data, files = _has_real_data(d)

        if not has_data:
            # 空壳（可能只有日期子目录或 valuation.json 但无其他真实数据——
            # 按 spec，basic/financials/kline/risk/valuation 才算真实数据）
            disposition = "空壳 → 直接删"
            shells.append(d.name)
        elif has_pure:
            pure_has, pure_files = _has_real_data(pure_dir)
            disposition = f"有真实数据 + 纯数字目录已存在（含 {pure_files}）→ 以纯数字为真值，后缀目录归档后删"
            real_with_pure.append(d.name)
        else:
            disposition = f"孤儿目录（无 {pure}/），含真实数据 → 创建 {pure}/ 移动数据后删后缀目录"
            orphans.append(d.name)
            real_orphan.append(d.name)

        lines.append(
            f"| `{d.name}` | `{pure}/` {'存在' if has_pure else '不存在（孤儿）'} | "
            f"{'是' if has_data else '否（空壳）'} | {', '.join(files) or '无'} | {disposition} |"
        )

    lines.append("")
    lines.append("## 汇总")
    lines.append(f"- 空壳目录（直接删）：{len(shells)} — {shells}")
    lines.append(f"- 有真实数据 + 纯数字已存在（归档后删）：{len(real_with_pure)} — {real_with_pure}")
    lines.append(f"- 孤儿目录（含真实数据，需迁移）：{len(orphans)} — {orphans}")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"审计完成，写入 {OUT}")
    print(f"  空壳：{len(shells)} {shells}")
    print(f"  有数据+纯数字存在：{len(real_with_pure)} {real_with_pure}")
    print(f"  孤儿（需迁移）：{len(orphans)} {orphans}")


if __name__ == "__main__":
    main()
