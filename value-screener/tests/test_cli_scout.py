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

        # Mock scout_batch
        from unittest.mock import patch
        import asyncio

        async def mock_scout_batch(candidates, force=False):
            return [
                {
                    "ticker": "600519",
                    "verdict": "deep_dive",
                    "confidence": 90,
                    "one_liner": "优质白酒企业",
                    "red_flags": [],
                    "green_flags": ["ROE > 25%"],
                    "anti_trap_flags": [],
                },
            ]

        with patch("scout.batch.scout_batch", new=mock_scout_batch):
            result = runner.invoke(app, [
                "scout",
                "--input", str(l1_path),
                "--output", str(l2_path),
            ])

            # 验证命令成功
            assert result.exit_code == 0
            assert "L2 筛选完成" in result.stdout

            # 验证输出文件
            assert l2_path.exists()
            l2_data = json.loads(l2_path.read_text(encoding="utf-8"))
            assert len(l2_data) == 1
            assert l2_data[0]["ticker"] == "600519"
            assert l2_data[0]["verdict"] == "deep_dive"


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


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
