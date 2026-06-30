"""CLI 集成测试 — monitor 子命令组."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli import app

runner = CliRunner()


@pytest.fixture
def isolated_watchlist(tmp_path, monkeypatch):
    """创建隔离的 watchlist 环境."""
    # 切换工作目录到临时目录
    monkeypatch.chdir(tmp_path)

    # 创建 watchlist 子目录
    wl_dir = tmp_path / "watchlist"
    wl_dir.mkdir()

    # 创建测试数据
    wl1 = {
        "generated_at": "2026-06-23T10:00:00",
        "l1_candidates": 2,
        "l2_shortlist": 1,
        "candidates": [
            {
                "ticker": "600519.SH",
                "name": "贵州茅台",
                "stage": "l2",
                "l1_score": 80.0,
                "f_score": 8,
                "pe_ttm": 28.5,
                "pe_percentile_5y": 22.0,
                "pb": 8.2,
                "pledge_ratio": 5.0,
                "l2_verdict": "deep_dive",
                "l2_confidence": 82,
                "l3_verdict": None,
                "l3_conviction": None,
                "key_variables": None,
                "last_updated": "2026-06-23",
            },
            {
                "ticker": "000858.SZ",
                "name": "五粮液",
                "stage": "l1",
                "l1_score": 75.0,
                "f_score": 7,
                "pe_ttm": 22.3,
                "pe_percentile_5y": None,
                "pb": 5.1,
                "pledge_ratio": 12.0,
                "l2_verdict": None,
                "l2_confidence": None,
                "l3_verdict": None,
                "l3_conviction": None,
                "key_variables": None,
                "last_updated": "2026-06-23",
            },
        ],
    }

    wl2 = {
        "generated_at": "2026-06-30T10:00:00",
        "l1_candidates": 2,
        "l2_shortlist": 1,
        "candidates": [
            {
                "ticker": "600519.SH",
                "name": "贵州茅台",
                "stage": "l3",
                "l1_score": 85.5,
                "f_score": 8,
                "pe_ttm": 28.5,
                "pe_percentile_5y": 18.5,
                "pb": 8.2,
                "pledge_ratio": 5.0,
                "l2_verdict": "deep_dive",
                "l2_confidence": 82,
                "l3_verdict": "bullish",
                "l3_conviction": None,
                "key_variables": ["市场份额下降"],
                "last_updated": "2026-06-30",
            },
            {
                "ticker": "002594.SZ",
                "name": "比亚迪",
                "stage": "l1",
                "l1_score": 72.0,
                "f_score": 6,
                "pe_ttm": 35.0,
                "pe_percentile_5y": None,
                "pb": 6.0,
                "pledge_ratio": 8.0,
                "l2_verdict": None,
                "l2_confidence": None,
                "l3_verdict": None,
                "l3_conviction": None,
                "key_variables": None,
                "last_updated": "2026-06-30",
            },
        ],
    }

    (wl_dir / "2026-06-23.json").write_text(json.dumps(wl1, ensure_ascii=False))
    (wl_dir / "2026-06-30.json").write_text(json.dumps(wl2, ensure_ascii=False))

    return wl_dir


class TestMonitorCLI:
    """Test monitor CLI subcommands."""

    def test_monitor_help(self):
        """Test monitor --help shows subcommands."""
        result = runner.invoke(app, ["monitor", "--help"])
        assert result.exit_code == 0
        assert "weekly" in result.output
        assert "watchlist" in result.output
        assert "diff" in result.output
        assert "history" in result.output

    def test_monitor_weekly_help(self):
        """Test monitor weekly --help shows options."""
        result = runner.invoke(app, ["monitor", "weekly", "--help"])
        assert result.exit_code == 0
        assert "--l1-file" in result.output
        assert "--output" in result.output
        assert "--force-l2" in result.output
        assert "--force-l3" in result.output

    def test_monitor_watchlist_latest(self, isolated_watchlist):
        """Test monitor watchlist shows latest."""
        result = runner.invoke(app, ["monitor", "watchlist"])
        assert result.exit_code == 0
        assert "Watchlist" in result.output
        assert "2026-06-30" in result.output

    def test_monitor_watchlist_specific_date(self, isolated_watchlist):
        """Test monitor watchlist --date shows specific date."""
        result = runner.invoke(app, ["monitor", "watchlist", "--date", "2026-06-23"])
        assert result.exit_code == 0
        assert "Watchlist" in result.output
        assert "2026-06-23" in result.output

    def test_monitor_watchlist_invalid_date(self, isolated_watchlist):
        """Test monitor watchlist with invalid date returns error."""
        result = runner.invoke(app, ["monitor", "watchlist", "--date", "2025-01-01"])
        assert result.exit_code != 0

    def test_monitor_diff_help(self):
        """Test monitor diff --help shows options."""
        result = runner.invoke(app, ["monitor", "diff", "--help"])
        assert result.exit_code == 0
        assert "--date" in result.output

    def test_monitor_diff_latest(self, isolated_watchlist):
        """Test monitor diff shows latest diff."""
        result = runner.invoke(app, ["monitor", "diff"])
        assert result.exit_code == 0
        assert "新增" in result.output or "移除" in result.output

    def test_monitor_diff_specific_date(self, isolated_watchlist):
        """Test monitor diff --date shows specific date diff."""
        result = runner.invoke(app, ["monitor", "diff", "--date", "2026-06-30"])
        assert result.exit_code == 0

    def test_monitor_history_help(self):
        """Test monitor history --help shows options."""
        result = runner.invoke(app, ["monitor", "history", "--help"])
        assert result.exit_code == 0
        assert "--from" in result.output
        assert "--to" in result.output

    def test_monitor_history_with_records(self, isolated_watchlist):
        """Test monitor history with existing records."""
        result = runner.invoke(app, ["monitor", "history", "600519.SH"])
        assert result.exit_code == 0
        assert "600519.SH" in result.output
        assert "l2" in result.output
        assert "l3" in result.output

    def test_monitor_history_no_records(self, isolated_watchlist):
        """Test monitor history with no records for ticker."""
        result = runner.invoke(app, ["monitor", "history", "999999.SH"])
        assert result.exit_code == 0
        assert "无历史记录" in result.output

    def test_monitor_history_date_range(self, isolated_watchlist):
        """Test monitor history with date range filter."""
        result = runner.invoke(app, [
            "monitor", "history", "600519.SH",
            "--from", "2026-06-25",
            "--to", "2026-06-30"
        ])
        assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
