"""Tests for cli.py scout subcommand (task 6.12)."""
import sys
from pathlib import Path
import tempfile
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typer.testing import CliRunner
from cli import app


runner = CliRunner()


def test_scout_command_basic():
    """验证 scout 命令基本流程."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 创建模拟 L1 输出
        l1_output = {
            "run_date": "2026-06-29",
            "candidates": [
                {"ticker": "600519", "name": "贵州茅台", "adjusted_composite": 85.0},
                {"ticker": "000858", "name": "五粮液", "adjusted_composite": 80.0},
            ],
            "stats": {"total": 100, "after_hard_gates": 50, "after_factors": 30, "after_heat_filter": 2},
        }
        l1_path = Path(tmpdir) / "l1_output.json"
        l1_path.write_text(json.dumps(l1_output, ensure_ascii=False), encoding="utf-8")

        l2_path = Path(tmpdir) / "l2_shortlist.json"

        # Mock scout_batch（g1-l2-full-result-contract：返回三元组）
        from unittest.mock import patch
        import asyncio

        async def mock_scout_batch(candidates, force=False, run_identity=None):
            # 三元组 (full_results, usage_summary, failure_summary)
            full_results = [
                {
                    "ticker": "600519",
                    "verdict": "deep_dive",
                    "confidence": 90,
                    "one_liner": "优质白酒企业",
                    "red_flags": [],
                    "green_flags": ["ROE > 25%"],
                    "anti_trap_flags": [],
                },
                {
                    "ticker": "000858",
                    "verdict": "watch",
                    "confidence": 55,
                    "one_liner": "观察",
                    "red_flags": [],
                    "green_flags": [],
                    "anti_trap_flags": [],
                },
            ]
            usage = {"call_count": 2, "cache_hits": 0, "prompt_tokens": 20,
                     "completion_tokens": 10, "total_tokens": 30}
            failure = {"errors": [], "skips": 0, "watches": 1, "degraded": 0,
                       "unhandled_exceptions": 0}
            return full_results, usage, failure

        with patch("scout.batch.scout_batch", new=mock_scout_batch):
            result = runner.invoke(app, [
                "scout",
                "--input", str(l1_path),
                "--output", str(l2_path),
            ])

            # 验证命令成功
            assert result.exit_code == 0
            assert "L2 筛选完成" in result.stdout

            # 验证输出文件（g1-l2-full-result-contract：四字段 payload）
            assert l2_path.exists()
            l2_data = json.loads(l2_path.read_text(encoding="utf-8"))
            # full_results 含全量（deep_dive + watch）
            assert len(l2_data["full_results"]) == 2
            assert l2_data["full_results"][0]["ticker"] == "600519"
            # shortlist 由 full_results 派生（只 deep_dive）
            shortlist = l2_data["shortlist"]
            assert len(shortlist) == 1
            assert shortlist[0]["ticker"] == "600519"
            assert shortlist[0]["verdict"] == "deep_dive"
            # usage_summary 存在
            assert l2_data["usage_summary"]["call_count"] == 2
            # failure_summary 存在且结构完整
            assert l2_data["failure_summary"]["watches"] == 1
            assert l2_data["failure_summary"]["unhandled_exceptions"] == 0


def test_scout_command_missing_input():
    """验证 scout 命令缺少输入文件时抛出错误."""
    result = runner.invoke(app, [
        "scout",
        "--input", "/nonexistent/path.json",
    ])

    assert result.exit_code != 0
    assert "not found" in result.stdout or "not found" in result.stderr


def test_scout_command_empty_candidates():
    """验证 scout 命令 L1 输出无候选时抛出错误."""
    with tempfile.TemporaryDirectory() as tmpdir:
        l1_output = {
            "run_date": "2026-06-29",
            "candidates": [],  # 空候选列表
            "stats": {"total": 100},
        }
        l1_path = Path(tmpdir) / "l1_output.json"
        l1_path.write_text(json.dumps(l1_output, ensure_ascii=False), encoding="utf-8")

        result = runner.invoke(app, [
            "scout",
            "--input", str(l1_path),
        ])

        assert result.exit_code != 0
        assert "no candidates" in result.stdout or "no candidates" in result.stderr


def test_scout_payload_carries_run_identity():
    """g1-canonical-run-identity: scout 输出 payload 顶层含 run identity（从 L1 文件继承）.

    对应 scout-agent MODIFIED CLI Integration: payload SHALL inherit run_id/
    profile_version/input_ticker_set_hash from L1 input file.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # L1 输出含 run identity 四字段（g1-canonical-run-identity L1 生成）
        l1_output = {
            "run_id": "l1_runid_abc123",
            "run_date": "2026-07-21",
            "profile_version": "g1-2026-07-21",
            "input_ticker_set_hash": "l1_input_hash",
            "candidates": [{"ticker": "600519", "name": "茅台", "adjusted_composite": 85.0}],
            "stats": {"total": 1, "after_hard_gates": 1, "after_factors": 1, "after_heat_filter": 1},
        }
        l1_path = Path(tmpdir) / "l1_output.json"
        l1_path.write_text(json.dumps(l1_output, ensure_ascii=False), encoding="utf-8")
        l2_path = Path(tmpdir) / "l2_shortlist.json"

        from unittest.mock import patch
        async def mock_scout_batch(candidates, force=False, run_identity=None):
            # run_identity SHALL 从 L1 文件继承（非 None）
            assert run_identity is not None, "scout_batch SHALL 收到从 L1 继承的 run_identity"
            assert run_identity.get("run_id") == "l1_runid_abc123"
            full_results = [{
                "ticker": "600519", "verdict": "deep_dive", "confidence": 90,
                "one_liner": "x", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
                # 模拟 scout_batch 注入的 run identity（继承自 L1）
                "run_id": run_identity["run_id"],
                "profile_version": run_identity["profile_version"],
                "input_ticker_set_hash": run_identity["input_ticker_set_hash"],
            }]
            usage = {"call_count": 1, "cache_hits": 0, "prompt_tokens": 10,
                     "completion_tokens": 5, "total_tokens": 15}
            failure = {"errors": [], "skips": 0, "watches": 0, "degraded": 0,
                       "unhandled_exceptions": 0}
            return full_results, usage, failure

        with patch("scout.batch.scout_batch", new=mock_scout_batch):
            result = runner.invoke(app, ["scout", "--input", str(l1_path), "--output", str(l2_path)])
            assert result.exit_code == 0, result.stdout

        l2_data = json.loads(l2_path.read_text(encoding="utf-8"))
        # payload 顶层含 run identity（从 L1 继承）
        assert l2_data.get("run_id") == "l1_runid_abc123", "payload SHALL 继承 L1 run_id"
        assert l2_data.get("profile_version") == "g1-2026-07-21"
        assert l2_data.get("input_ticker_set_hash") == "l1_input_hash"


def test_scout_payload_fallback_run_identity_when_l1_missing_identity():
    """g1-canonical-run-identity: L1 文件无 run identity → scout fallback 生成.

    旧 L1 文件（G1-2 前的格式）可能不含 run identity 字段，scout SHALL fallback 生成
    而非报错（向后兼容旧 L1）。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # 旧 L1 格式（无 run_id/profile_version/input_ticker_set_hash）
        l1_output = {
            "run_date": "2026-06-29",  # 旧格式只有 run_date
            "candidates": [{"ticker": "600519", "adjusted_composite": 85.0}],
            "stats": {"total": 1},
        }
        l1_path = Path(tmpdir) / "l1_output.json"
        l1_path.write_text(json.dumps(l1_output, ensure_ascii=False), encoding="utf-8")
        l2_path = Path(tmpdir) / "l2_shortlist.json"

        from unittest.mock import patch
        async def mock_scout_batch(candidates, force=False, run_identity=None):
            # L1 无 run_identity → cli 传 None（或不含），scout_batch fallback
            full_results = [{
                "ticker": "600519", "verdict": "deep_dive", "confidence": 90,
                "one_liner": "x", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
                "run_id": "fallback_rid", "profile_version": "g1-2026-07-21",
                "run_id_source": "scout_fallback",
            }]
            usage = {"call_count": 1, "cache_hits": 0, "prompt_tokens": 10,
                     "completion_tokens": 5, "total_tokens": 15}
            failure = {"errors": [], "skips": 0, "watches": 0, "degraded": 0,
                       "unhandled_exceptions": 0}
            return full_results, usage, failure

        with patch("scout.batch.scout_batch", new=mock_scout_batch):
            result = runner.invoke(app, ["scout", "--input", str(l1_path), "--output", str(l2_path)])
            assert result.exit_code == 0, result.stdout  # 不报错


def test_scout_output_run_scoped_same_day_not_overwrite():
    """g1-canonical-run-identity: 同日多次 scout 运行 SHALL 不互相覆盖（run-scoped 命名）.

    对应 scout-agent MODIFIED CLI Integration / 运行隔离:
    #### Scenario: Same-day multiple runs do not overwrite.
    同一 --output 路径，两次运行 run_id 不同（继承不同 L1 run_id），第二次 SHALL 改写
    run-scoped 文件名（{stem}.{run_id[:8]}.json），旧 run 输出 SHALL 仍可读，MUST NOT 被覆盖。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        l2_path = Path(tmpdir) / "l2_shortlist.json"
        from unittest.mock import patch

        def make_l1(run_id):
            return {
                "run_id": run_id, "run_date": "2026-07-21",
                "profile_version": "g1-2026-07-21",
                "input_ticker_set_hash": "h",
                "candidates": [{"ticker": "600519", "adjusted_composite": 85.0}],
                "stats": {"total": 1},
            }

        async def mock_scout_batch(candidates, force=False, run_identity=None):
            full_results = [{
                "ticker": "600519", "verdict": "deep_dive", "confidence": 90,
                "one_liner": "x", "red_flags": [], "green_flags": [], "anti_trap_flags": [],
                "run_id": run_identity["run_id"],
                "profile_version": run_identity["profile_version"],
                "input_ticker_set_hash": run_identity["input_ticker_set_hash"],
            }]
            usage = {"call_count": 1, "cache_hits": 0, "prompt_tokens": 10,
                     "completion_tokens": 5, "total_tokens": 15}
            failure = {"errors": [], "skips": 0, "degraded": 0, "unhandled_exceptions": 0}
            return full_results, usage, failure

        with patch("scout.batch.scout_batch", new=mock_scout_batch):
            # 第一次运行（L1 run_id = rid_alpha_001）
            l1a = Path(tmpdir) / "l1a.json"
            l1a.write_text(json.dumps(make_l1("rid_alpha_001"), ensure_ascii=False), encoding="utf-8")
            r1 = runner.invoke(app, ["scout", "--input", str(l1a), "--output", str(l2_path)])
            assert r1.exit_code == 0, r1.stdout
            first_rid = json.loads(l2_path.read_text(encoding="utf-8"))["run_id"]

            # 第二次运行（不同 L1 run_id = rid_beta_002，同 --output）
            l1b = Path(tmpdir) / "l1b.json"
            l1b.write_text(json.dumps(make_l1("rid_beta_002"), ensure_ascii=False), encoding="utf-8")
            r2 = runner.invoke(app, ["scout", "--input", str(l1b), "--output", str(l2_path)])
            assert r2.exit_code == 0, r2.stdout

        # 旧 run 输出 SHALL 仍存在（未被覆盖）
        first_data = json.loads(l2_path.read_text(encoding="utf-8"))
        assert first_data["run_id"] == first_rid, "旧 run 输出 SHALL 不被第二次运行覆盖"

        # 第二次 SHALL 写 run-scoped 分流文件，run_id 不同
        scoped = list(l2_path.parent.glob("l2_shortlist.*.json"))
        assert len(scoped) >= 1, "第二次运行 SHALL 产生 run-scoped 分流文件"
        second_data = json.loads(scoped[0].read_text(encoding="utf-8"))
        assert second_data["run_id"] != first_rid, "两次运行 run_id SHALL 不同"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
