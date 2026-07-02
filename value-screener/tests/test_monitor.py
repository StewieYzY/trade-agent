"""L4 监控层单元测试."""
import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Test fixtures
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
def sample_l3_output():
    """Sample L3 council output."""
    return {
        "final_verdict": "bullish",
        "conviction": None,
        "consensus_summary": None,
        "key_variables": ["市场份额下降", "消费降级"],
        "dissent_points": None,
        "pending_verification": None,
    }


@pytest.fixture
def temp_watchlist_dir():
    """Temporary watchlist directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestAggregation:
    """Test monitor/aggregation.py."""

    def test_compute_stage_l1(self):
        """Test stage calculation for L1 only."""
        from monitor.aggregation import _compute_stage
        assert _compute_stage(None, None) == "l1"
        assert _compute_stage("pass", None) == "l1"
        assert _compute_stage("reject", None) == "l1"

    def test_compute_stage_l2(self):
        """Test stage calculation for L2 deep_dive."""
        from monitor.aggregation import _compute_stage
        assert _compute_stage("deep_dive", None) == "l2"

    def test_compute_stage_l3(self):
        """Test stage calculation for L3."""
        from monitor.aggregation import _compute_stage
        assert _compute_stage("deep_dive", "bullish") == "l3"
        assert _compute_stage(None, "bearish") == "l3"
        assert _compute_stage("pass", "neutral") == "l3"
        # unknown boundary: L3 verdict="unknown" should still be l3
        assert _compute_stage(None, "unknown") == "l3"
        assert _compute_stage("deep_dive", "unknown") == "l3"

    def test_check_l3_incomplete(self):
        """Test L3 health check."""
        from monitor.aggregation import _check_l3_incomplete

        # All null fields
        incomplete_data = {
            "l3_verdict": "bullish",
            "l3_conviction": None,
            "consensus_summary": None,
            "dissent_points": None,
            "pending_verification": None,
        }
        assert _check_l3_incomplete(incomplete_data) is True

        # At least one field present
        complete_data = {
            "l3_verdict": "bullish",
            "l3_conviction": 85,
            "consensus_summary": None,
            "dissent_points": None,
            "pending_verification": None,
        }
        assert _check_l3_incomplete(complete_data) is False

        # No data
        assert _check_l3_incomplete(None) is False

    def test_aggregate_watchlist_basic(self, sample_l1_output, temp_watchlist_dir):
        """Test basic watchlist aggregation."""
        from monitor.aggregation import aggregate_watchlist

        # Write L1 output to temp file
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))

        # Mock ScoutCache and ValuationFetcher
        with patch("monitor.aggregation.ScoutCache") as mock_cache_class, \
             patch("monitor.aggregation.ValuationFetcher") as mock_valuation_class:

            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_class.return_value = mock_cache

            mock_valuation = MagicMock()
            mock_valuation.fetch_with_fallback.return_value = {"pe_percentile_5y": 18.5}
            mock_valuation_class.return_value = mock_valuation

            # Run aggregation
            result = aggregate_watchlist(
                run_date="2026-06-30",
                l1_output_file=str(l1_file),
                watchlist_dir=temp_watchlist_dir,
            )

            # Verify structure
            assert "generated_at" in result
            assert result["l1_candidates"] == 2
            assert result["l2_shortlist"] == 0  # No L2 results
            assert len(result["candidates"]) == 2

            # Verify candidate fields
            cand = result["candidates"][0]
            assert cand["ticker"] == "600519.SH"
            assert cand["stage"] == "l1"
            assert cand["l1_score"] == 85.5
            assert cand["pe_percentile_5y"] is None  # L1 only, no fetch

    def test_aggregate_watchlist_with_l3(self, sample_l1_output, sample_l3_output, temp_watchlist_dir):
        """Test watchlist aggregation with L3 output."""
        from monitor.aggregation import aggregate_watchlist

        # Write L1 output
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))

        # Write L3 output
        l3_file = temp_watchlist_dir / "2026-06-30_600519.SH.json"
        l3_file.write_text(json.dumps(sample_l3_output))

        with patch("monitor.aggregation.ScoutCache") as mock_cache_class, \
             patch("monitor.aggregation.ValuationFetcher") as mock_valuation_class, \
             patch("monitor.aggregation.CacheManager") as mock_cm_class:

            mock_cache = MagicMock()
            mock_cache.get.return_value = {
                "verdict": "deep_dive",
                "confidence": 82,
            }
            mock_cache_class.return_value = mock_cache

            # CacheManager.get 返回 None（缓存未命中）→ 走 ValuationFetcher.fetch_with_fallback
            # （f1-deviation-fix §4：避免测试依赖真实 data/cache 状态，原测试漏 mock CacheManager）
            mock_cm = MagicMock()
            mock_cm.get.return_value = None
            mock_cm_class.return_value = mock_cm

            mock_valuation = MagicMock()
            mock_valuation.fetch_with_fallback.return_value = {"pe_percentile_5y": 18.5}
            mock_valuation_class.return_value = mock_valuation

            result = aggregate_watchlist(
                run_date="2026-06-30",
                l1_output_file=str(l1_file),
                watchlist_dir=temp_watchlist_dir,
            )

            # Verify L3 aggregation
            cand = result["candidates"][0]
            assert cand["stage"] == "l3"
            assert cand["l3_verdict"] == "bullish"
            assert cand["l3_conviction"] is None
            assert cand["key_variables"] == ["市场份额下降", "消费降级"]
            assert cand["pe_percentile_5y"] == 18.5  # Fetched for L3
            assert cand.get("l3_incomplete") is True  # Null fields


class TestDiff:
    """Test monitor/diff.py."""

    def test_compute_diff_first_run(self):
        """Test diff with no previous snapshot."""
        from monitor.diff import compute_diff

        current = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 85.5, "stage": "l1"},
            ]
        }

        result = compute_diff(current, None)

        assert result["first_run"] is True
        assert result["message"] == "首次运行，无历史对比"
        assert result["added"] == []
        assert result["removed"] == []

    def test_compute_diff_added_removed(self):
        """Test diff detection for added/removed candidates."""
        from monitor.diff import compute_diff

        previous = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 80.0, "stage": "l1"},
                {"ticker": "000858.SZ", "l1_score": 75.0, "stage": "l1"},
            ]
        }

        current = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 85.5, "stage": "l1"},
                {"ticker": "002594.SZ", "l1_score": 72.0, "stage": "l1"},
            ]
        }

        result = compute_diff(current, previous)

        assert result["first_run"] is False
        assert "002594.SZ" in result["added"]
        assert "000858.SZ" in result["removed"]

    def test_compute_diff_l1_score_changed(self):
        """Test diff detection for l1_score changes."""
        from monitor.diff import compute_diff

        previous = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 70.0, "stage": "l1"},
                {"ticker": "000858.SZ", "l1_score": 75.0, "stage": "l1"},
            ]
        }

        current = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 85.5, "stage": "l1"},  # +15.5
                {"ticker": "000858.SZ", "l1_score": 78.0, "stage": "l1"},  # +3.0 (below threshold)
            ]
        }

        result = compute_diff(current, previous)

        assert len(result["l1_score_changed"]) == 1
        assert result["l1_score_changed"][0]["ticker"] == "600519.SH"
        assert result["l1_score_changed"][0]["delta"] == 15.5

    def test_compute_diff_stage_changes(self):
        """Test diff detection for stage upgrades/downgrades."""
        from monitor.diff import compute_diff

        previous = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 85.5, "stage": "l1"},
                {"ticker": "000858.SZ", "l1_score": 78.0, "stage": "l3"},
            ]
        }

        current = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 85.5, "stage": "l2"},  # Upgrade
                {"ticker": "000858.SZ", "l1_score": 78.0, "stage": "l2"},  # Downgrade
            ]
        }

        result = compute_diff(current, previous)

        assert len(result["stage_upgraded"]) == 1
        assert result["stage_upgraded"][0]["ticker"] == "600519.SH"

        assert len(result["stage_downgraded"]) == 1
        assert result["stage_downgraded"][0]["ticker"] == "000858.SZ"

    def test_compute_diff_valuation_low(self):
        """Test diff detection for pe_percentile_5y hitting low threshold."""
        from monitor.diff import compute_diff

        previous = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 85.5, "stage": "l2", "pe_percentile_5y": 22.0},
            ]
        }

        current = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 85.5, "stage": "l2", "pe_percentile_5y": 18.5},
            ]
        }

        result = compute_diff(current, previous)

        assert len(result["valuation_low"]) == 1
        assert result["valuation_low"][0]["ticker"] == "600519.SH"

    def test_compute_diff_triggers(self):
        """Test L2/L3 trigger logic."""
        from monitor.diff import compute_diff

        previous = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 70.0, "stage": "l1", "l2_verdict": None},
                {"ticker": "000858.SZ", "l1_score": 75.0, "stage": "l1", "l2_verdict": "pass"},
            ]
        }

        current = {
            "candidates": [
                {"ticker": "600519.SH", "l1_score": 85.5, "stage": "l1", "l2_verdict": None},  # +15.5, trigger L2
                {"ticker": "000858.SZ", "l1_score": 78.0, "stage": "l2", "l2_verdict": "deep_dive"},  # Flip to deep_dive, trigger L3
                {"ticker": "002594.SZ", "l1_score": 72.0, "stage": "l1", "l2_verdict": None},  # New, trigger L2
            ]
        }

        result = compute_diff(current, previous)

        assert "600519.SH" in result["l2_triggers"]  # Score change > 15
        assert "002594.SZ" in result["l2_triggers"]  # New candidate
        assert "000858.SZ" in result["l3_triggers"]  # Verdict flip


class TestCatalyst:
    """Test monitor/catalyst.py."""

    def test_detect_catalysts_no_previous(self):
        """Test catalyst detection with no previous data."""
        from monitor.catalyst import detect_catalysts

        current = {"pledge_ratio": 15.0}
        result = detect_catalysts("600519.SH", current, None)

        assert result["ticker"] == "600519.SH"
        assert result["fundamental_catalysts"] == []
        assert result["risk_signals"] == []

    def test_detect_catalysts_pledge_spike(self):
        """Test pledge ratio spike detection."""
        from monitor.catalyst import detect_catalysts

        previous = {"pledge_ratio": 5.0}
        current = {"pledge_ratio": 12.0}  # +7.0 ppt

        result = detect_catalysts("600519.SH", current, previous)

        assert len(result["risk_signals"]) == 1
        signal = result["risk_signals"][0]
        assert signal["type"] == "pledge_ratio_spike"
        assert signal["delta"] == 7.0
        assert signal["severity"] == "high"

    def test_detect_catalysts_no_spike(self):
        """Test no spike when change is below threshold."""
        from monitor.catalyst import detect_catalysts

        previous = {"pledge_ratio": 5.0}
        current = {"pledge_ratio": 8.0}  # +3.0 ppt (below 5.0 threshold)

        result = detect_catalysts("600519.SH", current, previous)

        assert len(result["risk_signals"]) == 0


class TestAlert:
    """Test monitor/alert.py."""

    def test_generate_valuation_alerts_paused(self):
        """Test valuation alerts are paused in MVP."""
        from monitor.alert import generate_valuation_alerts

        candidates = [
            {"ticker": "600519.SH", "pe_percentile_5y": 18.5, "stage": "l3"},
        ]
        catalyst_reports = [
            {"ticker": "600519.SH", "fundamental_catalysts": []},
        ]

        result = generate_valuation_alerts(candidates, catalyst_reports)

        assert result["status"] == "paused"
        assert "⏸️" in result["placeholder"]
        assert result["alerts"] == []

    def test_generate_risk_alerts(self):
        """Test risk alert generation."""
        from monitor.alert import generate_risk_alerts

        catalyst_reports = [
            {
                "ticker": "600519.SH",
                "risk_signals": [
                    {
                        "type": "pledge_ratio_spike",
                        "severity": "high",
                        "message": "质押率急升 5.0% → 12.0%（+7.0ppt）",
                    }
                ],
            }
        ]

        result = generate_risk_alerts(catalyst_reports)

        assert len(result["alerts"]) == 1
        assert "🔴" in result["alerts"][0]["message"]
        assert "600519.SH" in result["alerts"][0]["ticker"]

    def test_generate_key_variable_alerts(self):
        """Test key_variable alert generation."""
        from monitor.alert import generate_key_variable_alerts

        candidates = [
            {
                "ticker": "600519.SH",
                "name": "贵州茅台",
                "stage": "l3",
                "key_variables": ["市场份额下降", "消费降级"],
            },
            {
                "ticker": "000858.SZ",
                "name": "五粮液",
                "stage": "l2",  # Not L3, should be skipped
                "key_variables": ["竞争加剧"],
            },
        ]

        result = generate_key_variable_alerts(candidates)

        assert len(result["alerts"]) == 1
        assert result["alerts"][0]["ticker"] == "600519.SH"
        assert "💡" in result["alerts"][0]["hint"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
