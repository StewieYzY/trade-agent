"""g1-l2-full-result-contract P2：analyze_full_funnel 读 failure_summary 测试.

验证 record_l2_distribution 读 L2 输出的 full_results + failure_summary，
输出 deep_dive/watch/skip/error/degraded 分布 + error ticker/stage/reason 明细，
而非只读 shortlist 掩盖失败分布（spec「不允许用 shortlist 掩盖」）。
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.analyze_full_funnel import record_l2_distribution


def _make_l2_output():
    """构造含 full_results + failure_summary 的 L2 输出（g1-l2-full-result-contract 四字段 payload）."""
    return {
        "full_results": [
            {"ticker": "600001", "verdict": "deep_dive", "confidence": 85,
             "one_liner": "a", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
             "low_confidence_anomaly": False},
            {"ticker": "600002", "verdict": "watch", "confidence": 55,
             "one_liner": "b", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
             "low_confidence_anomaly": False},
            {"ticker": "600003", "verdict": "skip", "confidence": 40,
             "one_liner": "c", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
             "low_confidence_anomaly": False},
            {"ticker": "600004", "verdict": "error", "confidence": 0,
             "one_liner": "LLM 调用失败", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
             "low_confidence_anomaly": False, "error": "httpx.HTTPStatusError", "stage": "scout"},
            {"ticker": None, "input_index": 4, "verdict": "error",
             "one_liner": "输入缺 ticker", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
             "low_confidence_anomaly": False, "error": "missing ticker", "stage": "input_validation"},
        ],
        "shortlist": [  # deep_dive 派生（top-20 cap）
            {"ticker": "600001", "verdict": "deep_dive", "confidence": 85},
        ],
        "usage_summary": {"call_count": 3, "cache_hits": 0, "prompt_tokens": 30,
                          "completion_tokens": 15, "total_tokens": 45},
        "failure_summary": {
            "errors": [
                {"ticker": "600004", "input_index": 3, "reason": "httpx.HTTPStatusError", "stage": "scout"},
                {"ticker": None, "input_index": 4, "reason": "missing ticker", "stage": "input_validation"},
            ],
            "skips": 1, "watches": 1, "degraded": 0, "unhandled_exceptions": 0,
        },
    }


def test_record_l2_distribution_reads_failure_summary(tmp_path, monkeypatch):
    """record_l2_distribution SHALL 输出 watch/skip/error/degraded 分布 + error 明细.

    对应 review P2：analyze_full_funnel 原 only 读 shortlist + usage_summary，
    升级后读 failure_summary，输出完整漏斗分布 + error ticker/stage/reason。
    """
    # mock L2_FILE 指向临时文件，OUT_DIR 指向临时目录
    l2_file = tmp_path / "l2_full.json"
    l2_file.write_text(json.dumps(_make_l2_output()), encoding="utf-8")
    out_dir = tmp_path / "repro_out"
    out_dir.mkdir()
    monkeypatch.setattr("scripts.analyze_full_funnel.L2_FILE", l2_file)
    monkeypatch.setattr("scripts.analyze_full_funnel.OUT_DIR", out_dir)

    stats = record_l2_distribution()

    assert stats is not None, "应返回 stats（非 None 表示读到 L2 输出）"
    out_md = (out_dir / "l2_full_distribution.md").read_text(encoding="utf-8")

    # 分布段：deep_dive/watch/skip/error/degraded 全可见
    assert "watch: 1 只" in out_md, "应输出 watch 分布"
    assert "skip: 1 只" in out_md, "应输出 skip 分布"
    assert "error: 2 只" in out_md, "应输出 error 分布（2 条：600004 + 缺 ticker）"
    assert "degraded（watch 子集，单独计）: 0 只" in out_md, "应输出 degraded 分布"
    assert "unhandled_exceptions: 0" in out_md, "应输出 unhandled_exceptions（MUST 为 0）"
    assert "deep_dive（shortlist 派生）: 1 只" in out_md, "应输出 deep_dive（从 shortlist 派生）"

    # error 明细段：可定位 ticker/stage/reason
    assert "## error 明细" in out_md, "应有 error 明细段"
    assert "ticker=600004" in out_md, "应定位 error ticker 600004"
    assert "stage=scout" in out_md, "应输出 error stage"
    assert "httpx.HTTPStatusError" in out_md, "应输出 error reason"
    # 缺 ticker 的 error 用 input_index 定位（不伪造 ticker）
    assert "input_index=4" in out_md, "缺 ticker 的 error 应用 input_index 定位"
    assert "missing ticker" in out_md
    assert "stage=input_validation" in out_md

    # 输入总数来自 full_results（N=5），非只 shortlist 的 1
    assert "L1 candidates 输入：5 只" in out_md, "输入总数应来自 full_results（N=5），非 shortlist 的 1"


def test_record_l2_distribution_legacy_format_compat(tmp_path, monkeypatch):
    """兼容旧格式（纯 list 或缺 full_results/failure_summary）不崩.

    旧 L2 输出可能只有 shortlist（纯 list）或 {shortlist, usage_summary} 无 failure_summary。
    分析脚本应不崩，分布段 error/watch/skip 为 0（无 failure_summary 时）。
    """
    legacy = [  # 纯 list 旧格式
        {"ticker": "600001", "verdict": "deep_dive", "confidence": 85},
    ]
    l2_file = tmp_path / "l2_full.json"
    l2_file.write_text(json.dumps(legacy), encoding="utf-8")
    out_dir = tmp_path / "repro_out"
    out_dir.mkdir()
    monkeypatch.setattr("scripts.analyze_full_funnel.L2_FILE", l2_file)
    monkeypatch.setattr("scripts.analyze_full_funnel.OUT_DIR", out_dir)

    stats = record_l2_distribution()
    assert stats is not None
    out_md = (out_dir / "l2_full_distribution.md").read_text(encoding="utf-8")
    # 旧格式无 failure_summary → 分布为 0，但不崩
    assert "watch: 0 只" in out_md
    assert "error: 0 只" in out_md
    assert "deep_dive（shortlist 派生）: 1 只" in out_md


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
