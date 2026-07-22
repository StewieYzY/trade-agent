"""ScreeningProfile Version + 规则源码 hash 守护（g1-canonical-run-identity, design D3）.

提供规则版本的显式可审计标识 + 「规则变 MUST bump version」的测试守护。

实现方式（design D3 更新）：
- PROFILE_VERSION 是模块级代码常量字符串（零依赖，不引入配置文件层）
- compute_rules_hash() 对规则源码文件内容算 sha256——规则常量是函数体内联字面量
  （H1-H8 阈值/composite 权重/A1-A7 扣分/HF1-HF2），非模块级常量，抽常量会违反
  「screener/hard_gates/factor_scores/anti_trap/heat_filter 零改动」review 约束，故外挂
  观测源码内容
- 落盘 .rules_hash 存 {hash, profile_version} 基准，check_rules_in_sync 比对当前值与基准：
  - hash 相同 → 同步（规则未变）
  - hash 不同但 version 不同 → 同步（规则变且已 bump）
  - hash 不同但 version 相同 → 不同步（规则变但未 bump → 守护红测）
- .rules_hash 进 git（团队共享 version 守护基准，类似 lock 文件）

trade-off：源码文本变化（加注释、改格式）也触发 hash 变 → 保守误报，要求 review 是否 bump。
这正是「规则源码任何改动都该触发 version review」的保守语义。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

# 显式可审计的规则版本。规则常量任一变化 MUST bump 此值（守护测试强制）。
PROFILE_VERSION = "g1-2026-07-21"

# 规则源码文件列表（design D3：hash 这些文件内容，覆盖 H1-H8/composite 权重/A1-A7/HF1-HF2/
# G1_QUANT_DIMENSIONS/SCOUT_SYSTEM_PROMPT）。
# 路径相对 value-screener/（screener/ 与 scout/ 同层）。
_SCREENER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCREENER_DIR.parent  # value-screener/

RULE_FILES = [
    _SCREENER_DIR / "hard_gates.py",
    _SCREENER_DIR / "factor_scores.py",
    _SCREENER_DIR / "anti_trap.py",
    _SCREENER_DIR / "heat_filter.py",
    _SCREENER_DIR / "main.py",  # G1_QUANT_DIMENSIONS 所在
    _PROJECT_ROOT / "scout" / "prompt.py",  # SCOUT_SYSTEM_PROMPT
]

# 落盘基准文件（git 跟踪）。test 通过 monkeypatch RULES_HASH_FILE 指向临时文件模拟场景。
RULES_HASH_FILE = _SCREENER_DIR / ".rules_hash"


def compute_rules_hash() -> str:
    """对规则源码文件内容算 sha256，作规则版本变化的稳定指纹.

    源码文件任一字节变化（含注释/格式）→ hash 变 → 触发 bump review。
    返回 sha256 摘要前 16 字符（足够防碰撞，可读）。
    """
    h = hashlib.sha256()
    for f in RULE_FILES:
        # 文件路径 + 内容一起 hash，避免文件增删被忽略
        rel = str(f.relative_to(_PROJECT_ROOT))
        h.update(rel.encode("utf-8"))
        h.update(b"\x00")
        content = f.read_bytes()
        h.update(content)
        h.update(b"\x00")
    return h.hexdigest()[:16]


def _read_baseline() -> tuple[str, str] | None:
    """读落盘基准 {hash, profile_version}；不存在/损坏返回 None."""
    if not RULES_HASH_FILE.exists():
        return None
    try:
        data = json.loads(RULES_HASH_FILE.read_text(encoding="utf-8"))
        return data.get("hash", ""), data.get("profile_version", "")
    except (json.JSONDecodeError, OSError):
        return None


def check_rules_in_sync() -> tuple[bool, str]:
    """检查当前规则 hash + version 是否与落盘基准同步.

    Returns:
        (in_sync, reason):
        - (True, "ok")：规则未变（hash 相同），或规则变且 version 已 bump
        - (False, "规则变化但 PROFILE_VERSION 未 bump，请 bump PROFILE_VERSION 后运行
          `python -m screener.profile --refresh` 刷新基准")：规则变但 version 未 bump
        - (False, "未找到 .rules_hash 基准，请运行 `python -m screener.profile --refresh`")：
          无落盘基准（首次或基准丢失）
    """
    baseline = _read_baseline()
    if baseline is None:
        return False, "未找到 .rules_hash 基准，请运行 `python -m screener.profile --refresh`"
    baseline_hash, baseline_version = baseline

    current_hash = compute_rules_hash()
    current_version = PROFILE_VERSION

    if current_hash == baseline_hash:
        return True, "ok"  # 规则未变
    # hash 不同 → 规则变了，要求 version 也 bump
    if current_version != baseline_version:
        return True, "ok"  # 规则变且 version 已 bump
    return False, (
        "规则源码变化但 PROFILE_VERSION 未 bump（baseline hash 与当前不同，"
        "但 version 仍为 baseline 值）。请先 bump PROFILE_VERSION，"
        "再运行 `python -m screener.profile --refresh` 刷新落盘基准"
    )


def _refresh_baseline() -> None:
    """刷新落盘基准 = 当前 hash + 当前 version（用于开发者改规则 + bump 后重新落盘）."""
    baseline = {"hash": compute_rules_hash(), "profile_version": PROFILE_VERSION}
    RULES_HASH_FILE.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已刷新 {RULES_HASH_FILE}: hash={baseline['hash'][:8]}... "
          f"version={baseline['profile_version']}")


def main() -> None:
    """脚本入口：`python -m screener.profile [--refresh]`.

    无参数：检查当前规则是否与基准同步（exit 0 同步 / 1 不同步）。
    --refresh：用当前 hash + version 刷新落盘基准（开发者改规则 + bump version 后执行）。
    """
    if len(sys.argv) > 1 and sys.argv[1] == "--refresh":
        _refresh_baseline()
        return
    in_sync, reason = check_rules_in_sync()
    if in_sync:
        print(f"✓ 规则版本同步: {reason}")
        sys.exit(0)
    else:
        print(f"✗ 规则版本不同步: {reason}")
        sys.exit(1)


if __name__ == "__main__":
    main()
