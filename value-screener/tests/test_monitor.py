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


# ============================================================
# g1-canonical-run-identity D5+D6: _read_l3_output 双向回退 + watchlist run-scoped
# ============================================================

class TestReadL3OutputCanonicalFallback:
    """_read_l3_output canonical 双向回退，优先读真数据非空壳."""

    def test_canonical_ticker_reads_suffixed_real_data(self, temp_watchlist_dir):
        """canonical ticker 600009.SH → 优先读 {date}_600009.SH.json（真数据）."""
        from monitor.aggregation import _read_l3_output
        # 真数据（带后缀）
        real = {"final_verdict": "bullish", "conviction": 75,
                "consensus_summary": "真数据", "key_variables": [],
                "dissent_points": None, "pending_verification": None}
        (temp_watchlist_dir / "2026-07-13_600009.SH.json").write_text(
            json.dumps(real), encoding="utf-8")
        # 空壳（纯数字，字段全 null）
        shell = {"final_verdict": "unknown", "conviction": None,
                 "consensus_summary": None, "key_variables": None,
                 "dissent_points": None, "pending_verification": None}
        (temp_watchlist_dir / "2026-07-13_600009.json").write_text(
            json.dumps(shell), encoding="utf-8")

        result = _read_l3_output("600009.SH", "2026-07-13", temp_watchlist_dir)
        assert result is not None
        assert result["l3_conviction"] == 75, "SHALL 读真数据（非空壳 conviction=None）"
        assert result["consensus_summary"] == "真数据"

    def test_pure_digit_ticker_falls_back_to_suffixed_real_data(self, temp_watchlist_dir):
        """纯数字 ticker 600009 → 回退也读 {date}_600009.SH.json（真数据），非空壳."""
        from monitor.aggregation import _read_l3_output
        real = {"final_verdict": "bullish", "conviction": 80,
                "consensus_summary": "真数据2", "key_variables": [],
                "dissent_points": None, "pending_verification": None}
        (temp_watchlist_dir / "2026-07-13_600009.SH.json").write_text(
            json.dumps(real), encoding="utf-8")
        shell = {"final_verdict": "unknown", "conviction": None,
                 "consensus_summary": None, "key_variables": None,
                 "dissent_points": None, "pending_verification": None}
        (temp_watchlist_dir / "2026-07-13_600009.json").write_text(
            json.dumps(shell), encoding="utf-8")

        result = _read_l3_output("600009", "2026-07-13", temp_watchlist_dir)
        assert result is not None
        assert result["l3_conviction"] == 80, "纯数字输入 SHALL 回退读真数据（非空壳）"


class TestWatchlistRunScoped:
    """watchlist 输出 run-scoped 命名（D6：同日不同 run_id 不覆盖）."""

    def test_aggregate_writes_run_scoped_when_l1_has_run_id(self, sample_l1_output, temp_watchlist_dir):
        """L1 含 run_id → aggregate_watchlist 输出 {date}_{run_id[:8]}.json（run-scoped）."""
        from monitor.aggregation import aggregate_watchlist
        l1_with_run = dict(sample_l1_output)
        l1_with_run["run_id"] = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
        l1_with_run["profile_version"] = "g1-2026-07-21"
        l1_with_run["input_ticker_set_hash"] = "hash1234"
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(l1_with_run))

        with patch("monitor.aggregation.ScoutCache") as mock_cache_class, \
             patch("monitor.aggregation.ValuationFetcher") as mock_val_class:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None  # 无 L2 cache 命中，candidate 字段干净
            mock_cache_class.return_value = mock_cache
            mock_val = MagicMock()
            mock_val.fetch_with_fallback.return_value = {"pe_percentile_5y": 18.5}
            mock_val_class.return_value = mock_val
            aggregate_watchlist("2026-06-30", l1_output_file=str(l1_file),
                                watchlist_dir=temp_watchlist_dir)
        # run-scoped 文件名（前 8 hex of uuid4）
        run_scoped = temp_watchlist_dir / "2026-06-30_aaaaaaaa.json"
        assert run_scoped.exists(), "SHALL 写 run-scoped {date}_{run_id[:8]}.json"

    def test_aggregate_falls_back_to_date_only_when_no_run_id(self, sample_l1_output, temp_watchlist_dir):
        """旧 L1 无 run_id → aggregate_watchlist fallback {date}.json（向后兼容）."""
        from monitor.aggregation import aggregate_watchlist
        l1_file = temp_watchlist_dir / "l1_output.json"
        l1_file.write_text(json.dumps(sample_l1_output))  # 无 run_id

        with patch("monitor.aggregation.ScoutCache") as mock_cache_class, \
             patch("monitor.aggregation.ValuationFetcher") as mock_val_class:
            mock_cache = MagicMock()
            mock_cache.get.return_value = None
            mock_cache_class.return_value = mock_cache
            mock_val = MagicMock()
            mock_val.fetch_with_fallback.return_value = {"pe_percentile_5y": 18.5}
            mock_val_class.return_value = mock_val
            aggregate_watchlist("2026-06-30", l1_output_file=str(l1_file),
                                watchlist_dir=temp_watchlist_dir)
        legacy = temp_watchlist_dir / "2026-06-30.json"
        assert legacy.exists(), "旧 L1 无 run_id SHALL fallback {date}.json"

    def test_get_latest_watchlist_reads_run_scoped(self, temp_watchlist_dir):
        """get_latest_watchlist SHALL 读 run-scoped 聚合文件（非 per-ticker L3）."""
        from monitor.diff import get_latest_watchlist
        # run-scoped 聚合（应读，generated_at 最新）
        (temp_watchlist_dir / "2026-07-13_aaaaaaaa.json").write_text(
            json.dumps({"l1_candidates": 10, "generated_at": "2026-07-13T18:00:00+08:00"}),
            encoding="utf-8")
        # per-ticker L3（应跳过）
        (temp_watchlist_dir / "2026-07-13_600519.SH.json").write_text(
            json.dumps({"final_verdict": "bullish"}), encoding="utf-8")
        # 旧纯日期聚合（应读，generated_at 较早）
        (temp_watchlist_dir / "2026-07-12.json").write_text(
            json.dumps({"l1_candidates": 8, "generated_at": "2026-07-12T08:00:00+08:00"}),
            encoding="utf-8")

        result = get_latest_watchlist(temp_watchlist_dir)
        assert result is not None
        date_str, data = result
        assert date_str == "2026-07-13", "SHALL 优先读最新 run-scoped 聚合（2026-07-13）"
        assert data.get("l1_candidates") == 10


    def test_get_latest_watchlist_uses_generated_at_not_uuid_lexorder(self, temp_watchlist_dir):
        """g1-canonical-run-identity-repair: latest 按 generated_at 选，非 UUID 字典序.

        对应 watchlist-diff MODIFIED: #### Scenario: latest/previous 按 generated_at 选定。
        字典序小的 run_id（aaaaaaaa）但 generated_at 更晚（后生成）SHALL 被选为 latest；
        字典序大的 run_id（zzzzzzzz 是非 hex，改用 ffffffff）generated_at 更早 SHALL 不被选。
        """
        import os
        from monitor.diff import get_latest_watchlist
        # 两个 run-scoped 文件，同日（2026-07-13）
        # aaaaaaaa：字典序小，但 generated_at 更晚（后生成）
        (temp_watchlist_dir / "2026-07-13_aaaaaaaa.json").write_text(json.dumps({
            "l1_candidates": 10, "generated_at": "2026-07-13T18:00:00+08:00",
        }), encoding="utf-8")
        # ffffffff：字典序大，但 generated_at 更早（先生成）
        (temp_watchlist_dir / "2026-07-13_ffffffff.json").write_text(json.dumps({
            "l1_candidates": 8, "generated_at": "2026-07-13T09:00:00+08:00",
        }), encoding="utf-8")
        # 控制 mtime 相反（避免 mtime 干扰）：让 ffffffff mtime 更晚
        f_late = temp_watchlist_dir / "2026-07-13_aaaaaaaa.json"
        f_early = temp_watchlist_dir / "2026-07-13_ffffffff.json"
        os.utime(f_late, (1_700_000_000, 1_700_000_000))   # 较早 mtime
        os.utime(f_early, (1_700_000_100, 1_700_000_100))  # 较晚 mtime（与 generated_at 相反）

        result = get_latest_watchlist(temp_watchlist_dir)
        assert result is not None
        date_str, data = result
        assert date_str == "2026-07-13"
        assert data.get("l1_candidates") == 10, \
            "SHALL 按 generated_at 选 aaaaaaaa（晚），MUST NOT 按字典序/mtime 选 ffffffff"

    def test_get_previous_watchlist_returns_second_latest_by_generated_at(self, temp_watchlist_dir):
        """g1-canonical-run-identity-repair: previous 按 generated_at 取次新."""
        import os
        from monitor.diff import get_previous_watchlist
        # 3 个文件 generated_at 依次递增
        (temp_watchlist_dir / "2026-07-10_aaaaaaaa.json").write_text(json.dumps({
            "generated_at": "2026-07-10T08:00:00+08:00", "l1_candidates": 1}), encoding="utf-8")
        (temp_watchlist_dir / "2026-07-11_bbbbbbbb.json").write_text(json.dumps({
            "generated_at": "2026-07-11T08:00:00+08:00", "l1_candidates": 2}), encoding="utf-8")
        (temp_watchlist_dir / "2026-07-12_cccccccc.json").write_text(json.dumps({
            "generated_at": "2026-07-12T08:00:00+08:00", "l1_candidates": 3}), encoding="utf-8")

        # current = 2026-07-13，previous SHALL 是 07-12（次新，最新是 07-13 不存在所以取 07-12）
        result = get_previous_watchlist("2026-07-13", watchlist_dir=temp_watchlist_dir)
        assert result is not None
        assert result.get("l1_candidates") == 3, "previous SHALL 取 generated_at 次新（07-12）"

        # 只剩 0 个历史（current 早于所有）→ None
        assert get_previous_watchlist("2026-07-09", watchlist_dir=temp_watchlist_dir) is None

    def test_get_latest_watchlist_falls_back_to_mtime_when_no_generated_at(self, temp_watchlist_dir):
        """g1-canonical-run-identity-repair: 旧文件无 generated_at → fallback mtime."""
        import os
        from monitor.diff import get_latest_watchlist
        # 旧纯日期聚合文件无 generated_at（G1-3 前格式）
        f_old = temp_watchlist_dir / "2026-07-12.json"
        f_new = temp_watchlist_dir / "2026-07-13.json"
        f_old.write_text(json.dumps({"l1_candidates": 8}), encoding="utf-8")
        f_new.write_text(json.dumps({"l1_candidates": 10}), encoding="utf-8")
        # 控制 mtime：07-13 更晚
        os.utime(f_old, (1_700_000_000, 1_700_000_000))
        os.utime(f_new, (1_700_000_100, 1_700_000_100))

        result = get_latest_watchlist(temp_watchlist_dir)
        assert result is not None
        _, data = result
        assert data.get("l1_candidates") == 10, "无 generated_at 时 SHALL fallback mtime 选最新（07-13）"


class TestHistoryRunScoped:
    """g1-canonical-run-identity D6: history() 读 run-scoped 聚合，不误跳 per-ticker L3."""

    def test_history_reads_run_scoped_aggregate_not_per_ticker(self, temp_watchlist_dir):
        """history(ticker) 读 run-scoped 聚合 {date}_{run_id[:8]}.json，跳过 per-ticker L3.

        run-scoped 文件名含 `_` 但第二段是 hex run_id（非 ticker），SHALL 被读；
        per-ticker {date}_{ticker}.json（ticker 含 . 或字母）SHALL 被跳。
        """
        from monitor.diff import history
        # run-scoped 聚合（含该 ticker 的 stage/l1_score，应读）
        (temp_watchlist_dir / "2026-07-13_aaaaaaaa.json").write_text(json.dumps({
            "candidates": [{"ticker": "600519.SH", "stage": "l1", "l1_score": 85.5,
                            "l3_verdict": None, "pe_percentile_5y": None}],
        }), encoding="utf-8")
        # per-ticker L3（应跳过，非聚合 watchlist）
        (temp_watchlist_dir / "2026-07-13_600519.SH.json").write_text(json.dumps({
            "final_verdict": "bullish"}), encoding="utf-8")
        # 旧纯日期聚合（应读，回退）
        (temp_watchlist_dir / "2026-07-12.json").write_text(json.dumps({
            "candidates": [{"ticker": "600519.SH", "stage": "l1", "l1_score": 80.0,
                           "l3_verdict": None, "pe_percentile_5y": None}],
        }), encoding="utf-8")

        records = history("600519.SH", watchlist_dir=temp_watchlist_dir)
        # SHALL 读到 run-scoped (07-13) + 旧纯日期 (07-12) 两条聚合记录，非 per-ticker L3
        dates = [r.get("date") for r in records]
        assert "2026-07-13" in dates, "SHALL 读 run-scoped 聚合（07-13）"
        assert "2026-07-12" in dates, "SHALL 读旧纯日期聚合（07-12）"
        # per-ticker L3 不应作为独立 record（它不是聚合 watchlist）


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
