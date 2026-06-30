"""L4 weekly 主循环测试."""
import asyncio
import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from monitor.weekly import run_weekly


@pytest.fixture
def sample_l1_output():
    """Sample L1 screening output."""
    return {
        "run_date": "2026-06-30",
        "candidates": [
            {
                "ticker": "600519.SH",
                "name": "贵州茅台",
                "industry": "白酒",
                "adjusted_composite": 85.5,
                "f_score": 8,
                "pe_ttm": 28.5,
                "pb": 8.2,
                "pledge_ratio": 5.0,
            },
            {
                "ticker": "000858.SZ",
                "name": "五粮液",
                "industry": "白酒",
                "adjusted_composite": 78.2,
                "f_score": 7,
                "pe_ttm": 22.3,
                "pb": 5.1,
                "pledge_ratio": 12.0,
            },
        ],
        "stats": {"total": 5000, "passed": 2},
    }


@pytest.fixture
def temp_watchlist_dir():
    """Temporary watchlist directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestWeekly:
    """Test monitor/weekly.py — 主循环编排、触发阈值、成本日志、错误处理."""

    def test_run_weekly_basic_flow(self, sample_l1_output, temp_watchlist_dir):
        """Test basic weekly flow without L2/L3 triggers."""
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))

        with patch("monitor.weekly.aggregate_watchlist") as mock_agg, \
             patch("monitor.weekly.get_previous_watchlist") as mock_prev, \
             patch("monitor.weekly.compute_diff") as mock_diff, \
             patch("monitor.weekly.detect_catalysts_batch") as mock_cat, \
             patch("monitor.weekly.generate_alerts") as mock_alert:

            mock_agg.return_value = {
                "candidates": [
                    {"ticker": "600519.SH", "stage": "l1", "l1_score": 85.5},
                ],
                "l1_candidates": 1,
                "l2_shortlist": 0,
            }
            mock_prev.return_value = None
            mock_diff.return_value = {
                "first_run": True, "added": [], "removed": [],
                "l1_score_changed": [], "stage_upgraded": [], "stage_downgraded": [],
                "verdict_changed": [], "valuation_low": [],
                "l2_triggers": [], "l3_triggers": [],
            }
            mock_cat.return_value = []
            mock_alert.return_value = {
                "valuation_alerts": {"status": "paused", "alerts": []},
                "risk_alerts": {"alerts": []},
                "key_variable_alerts": {"alerts": []},
            }

            report = asyncio.run(run_weekly(
                l1_output_file=str(l1_file),
                watchlist_dir=temp_watchlist_dir,
            ))

            # Verify basic structure
            assert "run_date" in report
            assert "watchlist" in report
            assert "diff" in report
            assert "cost_log" in report

            # Verify no triggers
            assert report["l2_triggered"] == []
            assert report["l3_triggered"] == []

            # Verify cost log
            assert report["cost_log"]["l2_calls"] == 0
            assert report["cost_log"]["l3_calls"] == 0
            assert report["cost_log"]["estimated_cost_yuan"] == 0.0

    def test_run_weekly_l2_trigger_then_l3_flip(self, sample_l1_output, temp_watchlist_dir):
        """P0 验证：L2 重跑后 verdict 翻转为 deep_dive → 触发 L3."""
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))

        with patch("monitor.weekly.aggregate_watchlist") as mock_agg, \
             patch("monitor.weekly.get_previous_watchlist") as mock_prev, \
             patch("monitor.weekly.compute_diff") as mock_diff, \
             patch("monitor.weekly.detect_catalysts_batch") as mock_cat, \
             patch("monitor.weekly.generate_alerts") as mock_alert, \
             patch("scout.batch.scout_batch", new_callable=AsyncMock) as mock_scout, \
             patch("council.debate.run_debate", new_callable=AsyncMock) as mock_debate:

            # Old verdict is "pass" → L2 rerun returns "deep_dive" → should trigger L3
            mock_agg.return_value = {
                "candidates": [
                    {"ticker": "600519.SH", "stage": "l1", "l1_score": 85.5, "l2_verdict": "pass"},
                ],
                "l1_candidates": 1,
                "l2_shortlist": 0,
            }
            mock_prev.return_value = None
            mock_diff.return_value = {
                "first_run": False, "added": [], "removed": [],
                "l1_score_changed": [{"ticker": "600519.SH", "delta": 16.0}],
                "stage_upgraded": [], "stage_downgraded": [],
                "verdict_changed": [], "valuation_low": [],
                "l2_triggers": ["600519.SH"],
                "l3_triggers": [],  # Old diff says no L3 trigger
            }
            # L2 rerun returns deep_dive
            mock_scout.return_value = [
                {"ticker": "600519.SH", "verdict": "deep_dive", "confidence": 85}
            ]
            mock_cat.return_value = []
            mock_alert.return_value = {
                "valuation_alerts": {"status": "paused", "alerts": []},
                "risk_alerts": {"alerts": []},
                "key_variable_alerts": {"alerts": []},
            }

            report = asyncio.run(run_weekly(
                l1_output_file=str(l1_file),
                watchlist_dir=temp_watchlist_dir,
            ))

            # L2 should be triggered
            assert "600519.SH" in report["l2_triggered"]

            # P0 fix: L3 should be triggered based on NEW verdict flip
            assert "600519.SH" in report["l3_triggered"]
            mock_debate.assert_called_once()

    def test_run_weekly_l2_no_flip_no_l3(self, sample_l1_output, temp_watchlist_dir):
        """L2 重跑后 verdict 仍为 pass → 不触发 L3."""
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))

        with patch("monitor.weekly.aggregate_watchlist") as mock_agg, \
             patch("monitor.weekly.get_previous_watchlist") as mock_prev, \
             patch("monitor.weekly.compute_diff") as mock_diff, \
             patch("monitor.weekly.detect_catalysts_batch") as mock_cat, \
             patch("monitor.weekly.generate_alerts") as mock_alert, \
             patch("scout.batch.scout_batch", new_callable=AsyncMock) as mock_scout:

            mock_agg.return_value = {
                "candidates": [
                    {"ticker": "600519.SH", "stage": "l1", "l1_score": 85.5, "l2_verdict": "pass"},
                ],
                "l1_candidates": 1,
                "l2_shortlist": 0,
            }
            mock_prev.return_value = None
            mock_diff.return_value = {
                "first_run": False, "added": [], "removed": [],
                "l1_score_changed": [{"ticker": "600519.SH", "delta": 16.0}],
                "stage_upgraded": [], "stage_downgraded": [],
                "verdict_changed": [], "valuation_low": [],
                "l2_triggers": ["600519.SH"],
                "l3_triggers": [],
            }
            # L2 rerun still returns pass (no flip)
            mock_scout.return_value = [
                {"ticker": "600519.SH", "verdict": "pass", "confidence": 55}
            ]
            mock_cat.return_value = []
            mock_alert.return_value = {
                "valuation_alerts": {"status": "paused", "alerts": []},
                "risk_alerts": {"alerts": []},
                "key_variable_alerts": {"alerts": []},
            }

            report = asyncio.run(run_weekly(
                l1_output_file=str(l1_file),
                watchlist_dir=temp_watchlist_dir,
            ))

            # L2 triggered, but L3 NOT triggered (no flip)
            assert "600519.SH" in report["l2_triggered"]
            assert report["l3_triggered"] == []

    def test_run_weekly_l2_failure_skips_l3(self, sample_l1_output, temp_watchlist_dir):
        """L2 失败时跳过该 ticker，不触发 L3."""
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))

        with patch("monitor.weekly.aggregate_watchlist") as mock_agg, \
             patch("monitor.weekly.get_previous_watchlist") as mock_prev, \
             patch("monitor.weekly.compute_diff") as mock_diff, \
             patch("monitor.weekly.detect_catalysts_batch") as mock_cat, \
             patch("monitor.weekly.generate_alerts") as mock_alert, \
             patch("scout.batch.scout_batch", new_callable=AsyncMock) as mock_scout:

            mock_agg.return_value = {
                "candidates": [
                    {"ticker": "600519.SH", "stage": "l1", "l1_score": 85.5, "l2_verdict": None},
                ],
                "l1_candidates": 1,
                "l2_shortlist": 0,
            }
            mock_prev.return_value = None
            mock_diff.return_value = {
                "first_run": False, "added": ["600519.SH"], "removed": [],
                "l1_score_changed": [], "stage_upgraded": [], "stage_downgraded": [],
                "verdict_changed": [], "valuation_low": [],
                "l2_triggers": ["600519.SH"],
                "l3_triggers": [],
            }
            # L2 returns error
            mock_scout.return_value = [
                {"ticker": "600519.SH", "error": "LLM API failure"}
            ]
            mock_cat.return_value = []
            mock_alert.return_value = {
                "valuation_alerts": {"status": "paused", "alerts": []},
                "risk_alerts": {"alerts": []},
                "key_variable_alerts": {"alerts": []},
            }

            report = asyncio.run(run_weekly(
                l1_output_file=str(l1_file),
                watchlist_dir=temp_watchlist_dir,
            ))

            # L2 failure tracked
            assert "600519.SH" in report["l2_failed"]
            assert "600519.SH" not in report["l2_triggered"]

            # No L3 trigger for failed L2
            assert report["l3_triggered"] == []
            assert report["cost_log"]["l2_failed"] == 1

    def test_run_weekly_cost_log_l3_price(self, sample_l1_output, temp_watchlist_dir):
        """P2 验证：L3 单价 ¥40（不是 ¥2）."""
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))

        with patch("monitor.weekly.aggregate_watchlist") as mock_agg, \
             patch("monitor.weekly.get_previous_watchlist") as mock_prev, \
             patch("monitor.weekly.compute_diff") as mock_diff, \
             patch("monitor.weekly.detect_catalysts_batch") as mock_cat, \
             patch("monitor.weekly.generate_alerts") as mock_alert, \
             patch("scout.batch.scout_batch", new_callable=AsyncMock) as mock_scout, \
             patch("council.debate.run_debate", new_callable=AsyncMock) as mock_debate:

            mock_agg.return_value = {
                "candidates": [
                    {"ticker": "600519.SH", "stage": "l1", "l1_score": 85.5, "l2_verdict": "pass"},
                    {"ticker": "000858.SZ", "stage": "l1", "l1_score": 78.2, "l2_verdict": None},
                ],
                "l1_candidates": 2,
                "l2_shortlist": 0,
            }
            mock_prev.return_value = None
            mock_diff.return_value = {
                "first_run": False, "added": [], "removed": [],
                "l1_score_changed": [
                    {"ticker": "600519.SH", "delta": 16.0},
                    {"ticker": "000858.SZ", "delta": 20.0},
                ],
                "stage_upgraded": [], "stage_downgraded": [],
                "verdict_changed": [], "valuation_low": [],
                "l2_triggers": ["600519.SH", "000858.SZ"],
                "l3_triggers": [],
            }
            # Both L2 reruns return deep_dive → 2 L3 triggers
            mock_scout.return_value = [
                {"ticker": "600519.SH", "verdict": "deep_dive", "confidence": 85},
                {"ticker": "000858.SZ", "verdict": "deep_dive", "confidence": 72},
            ]
            mock_cat.return_value = []
            mock_alert.return_value = {
                "valuation_alerts": {"status": "paused", "alerts": []},
                "risk_alerts": {"alerts": []},
                "key_variable_alerts": {"alerts": []},
            }

            report = asyncio.run(run_weekly(
                l1_output_file=str(l1_file),
                watchlist_dir=temp_watchlist_dir,
            ))

            # 2 L2 calls × ¥0.01 + 2 L3 calls × ¥40 = ¥80.02
            cost = report["cost_log"]["estimated_cost_yuan"]
            assert cost == pytest.approx(2 * 0.01 + 2 * 40.0)
            assert cost > 70  # Definitely not ¥4 (old ¥2 price)

    def test_run_weekly_report_file_written(self, sample_l1_output, temp_watchlist_dir):
        """Test weekly report file is written."""
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))

        with patch("monitor.weekly.aggregate_watchlist") as mock_agg, \
             patch("monitor.weekly.get_previous_watchlist") as mock_prev, \
             patch("monitor.weekly.compute_diff") as mock_diff, \
             patch("monitor.weekly.detect_catalysts_batch") as mock_cat, \
             patch("monitor.weekly.generate_alerts") as mock_alert:

            mock_agg.return_value = {
                "candidates": [],
                "l1_candidates": 0,
                "l2_shortlist": 0,
            }
            mock_prev.return_value = None
            mock_diff.return_value = {
                "first_run": True, "added": [], "removed": [],
                "l1_score_changed": [], "stage_upgraded": [], "stage_downgraded": [],
                "verdict_changed": [], "valuation_low": [],
                "l2_triggers": [], "l3_triggers": [],
            }
            mock_cat.return_value = []
            mock_alert.return_value = {
                "valuation_alerts": {"status": "paused", "alerts": []},
                "risk_alerts": {"alerts": []},
                "key_variable_alerts": {"alerts": []},
            }

            asyncio.run(run_weekly(
                l1_output_file=str(l1_file),
                watchlist_dir=temp_watchlist_dir,
            ))

            # Verify report file was written
            today = date.today().isoformat()
            report_file = temp_watchlist_dir / f"{today}_weekly_report.json"
            assert report_file.exists()

            with report_file.open() as f:
                saved_report = json.load(f)
            assert saved_report["run_date"] == today


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
