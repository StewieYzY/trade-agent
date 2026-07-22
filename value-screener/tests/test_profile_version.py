"""g1-canonical-run-identity: ScreeningProfile version + 规则源码 hash 守护测试.

对应 run-identity spec / ScreeningProfile Version 显式审计与 bump 约束（design D3）。
规则常量是函数体内联字面量非模块级，抽常量会违反「规则模块零改动」约束，
故 compute_rules_hash() 对规则源码文件内容算 sha256（design D3 更新）。
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from screener.profile import (
    PROFILE_VERSION,
    compute_rules_hash,
    check_rules_in_sync,
)


# ============================================================
# Task 2.1: PROFILE_VERSION 模块常量
# ============================================================

def test_profile_version_is_module_constant():
    """PROFILE_VERSION 存在且为非空字符串（显式可审计规则版本）."""
    assert isinstance(PROFILE_VERSION, str)
    assert PROFILE_VERSION, "PROFILE_VERSION MUST 非空"
    assert PROFILE_VERSION != "0.0.0", "MUST NOT 用占位版本号"


# ============================================================
# Task 2.3: compute_rules_hash 确定性
# ============================================================

def test_rules_hash_stable_across_runs():
    """相同规则源码文件多次计算 compute_rules_hash 返回相同 hash（确定性）."""
    h1 = compute_rules_hash()
    h2 = compute_rules_hash()
    assert h1 == h2, "相同源码 compute_rules_hash MUST 确定（非随机）"
    assert len(h1) > 0


# ============================================================
# Task 2.2: 规则变但 version 未 bump → 守护测试红
# ============================================================

def test_rules_hash_guard_fails_when_rules_change_without_bump(tmp_path, monkeypatch):
    """规则源码变了（hash 变）但 PROFILE_VERSION 未 bump → check_rules_in_sync SHALL False.

    design D3：守护逻辑——当前 hash != 落盘 hash 且当前 version == 落盘 version → 红。
    用 monkeypatch compute_rules_hash 返回新 hash 模拟「规则变了」，不改真源码（避免 fragile）。
    bump PROFILE_VERSION 后 SHALL 通过。
    """
    # 构造落盘基准：规则旧 hash + 旧 version（假设当时同步）
    baseline_hash = "old_rules_hash_aaaa"
    baseline_version = PROFILE_VERSION  # 当前 version 作为基准
    baseline_file = tmp_path / ".rules_hash"
    baseline_file.write_text(
        f'{{"hash": "{baseline_hash}", "profile_version": "{baseline_version}"}}',
        encoding="utf-8",
    )
    # monkeypatch 落盘路径指向临时文件
    monkeypatch.setattr("screener.profile.RULES_HASH_FILE", baseline_file)
    # monkeypatch compute_rules_hash 返回新 hash（模拟规则源码变了）
    monkeypatch.setattr("screener.profile.compute_rules_hash", lambda: "new_rules_hash_bbbb")

    # 规则变（new hash != baseline hash）但 version 未 bump（== baseline version）→ 不同步
    in_sync, reason = check_rules_in_sync()
    assert in_sync is False, "规则变但 version 未 bump MUST 检测为不同步"
    assert "bump" in reason.lower() or "version" in reason.lower(), \
        f"提示应说明需 bump version，实际: {reason}"


def test_rules_hash_guard_passes_when_rules_change_with_bump(tmp_path, monkeypatch):
    """规则源码变了且 PROFILE_VERSION 已 bump → check_rules_in_sync SHALL True."""
    baseline_hash = "old_rules_hash_aaaa"
    baseline_version = "g1-old-version"
    baseline_file = tmp_path / ".rules_hash"
    baseline_file.write_text(
        f'{{"hash": "{baseline_hash}", "profile_version": "{baseline_version}"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("screener.profile.RULES_HASH_FILE", baseline_file)
    monkeypatch.setattr("screener.profile.compute_rules_hash", lambda: "new_rules_hash_bbbb")
    # PROFILE_VERSION 已 bump（当前 version != baseline version）

    in_sync, _ = check_rules_in_sync()
    assert in_sync is True, "规则变且 version 已 bump SHALL 同步"


def test_rules_hash_guard_passes_when_unchanged(tmp_path, monkeypatch):
    """规则源码未变（hash 相同）→ 不管 version 是否 bump 都同步."""
    baseline_hash = "same_hash_xxxx"
    baseline_version = PROFILE_VERSION
    baseline_file = tmp_path / ".rules_hash"
    baseline_file.write_text(
        f'{{"hash": "{baseline_hash}", "profile_version": "{baseline_version}"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("screener.profile.RULES_HASH_FILE", baseline_file)
    monkeypatch.setattr("screener.profile.compute_rules_hash", lambda: "same_hash_xxxx")

    in_sync, _ = check_rules_in_sync()
    assert in_sync is True, "规则未变 SHALL 同步"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
