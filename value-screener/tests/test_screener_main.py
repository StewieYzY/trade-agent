"""g1-canonical-run-identity: L1 主入口生成 run_id 测试.

对应 run-identity spec / Run ID L1 生成（design D2 + Migration 3）。
验证 screen_a_shares 返回结构顶层含 run_id/run_date/profile_version/input_ticker_set_hash
四字段，且 run_id 对相同输入稳定（非随机）。

复用 test_screener_stats.py 的 BatchFetcher mock 模式（patch screener.main.BatchFetcher）。
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from screener.main import screen_a_shares
from screener.profile import PROFILE_VERSION


def _make_ticker_data(industry="白酒", pe=25.0):
    """构造一份能过 hard gates 的最小 ticker_data（复用 test_screener_stats 约定）."""
    return {
        "basic": {
            "code": "600519", "name": "贵州茅台", "industry": industry,
            "pe": pe, "pb": 2.0, "price": 10.0, "market_cap": 100e8,
        },
        "financials": {
            "years": ["2020", "2021", "2022"],
            "income": {"net_profit": [100, 120, 150]},
            "balance_sheet": {
                "TOTAL_ASSETS": [1000, 1100, 1200],
                "TOTAL_CURRENT_LIAB": [300, 330, 360],
                "TOTAL_NONCURRENT_LIAB": [200, 220, 240],
            },
            "cash_flow": {"NETCASH_OPERATE": [80, 90, 100]},
        },
        "valuation": {"pe_percentile_5y": 40, "pb": 2.0, "pe_ttm": pe, "graham_number": 100},
        "risk": {"pledge_ratio": 30, "audit_opinion": "标准无保留意见"},
        "kline": {"turnover_rate": [0.3] * 60, "close": [10.0] * 60},
    }


def test_screen_a_shares_returns_run_identity():
    """screen_a_shares 返回结构顶层含 run_id/run_date/profile_version/input_ticker_set_hash.

    对应 run-identity spec: L1 生成 run_id 并写入输出。
    """
    tickers = ["600519"]
    fake_all_data = {"600519": _make_ticker_data()}
    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        result = screen_a_shares(tickers)

    assert "run_id" in result, "返回结构 MUST 含 run_id"
    assert "run_date" in result, "MUST 含 run_date"
    assert "profile_version" in result, "MUST 含 profile_version"
    assert "input_ticker_set_hash" in result, "MUST 含 input_ticker_set_hash"
    assert result["run_id"], "run_id MUST 非空"
    assert result["run_date"], "run_date MUST 非空"
    assert result["profile_version"] == PROFILE_VERSION, \
        "profile_version MUST 等于当前 PROFILE_VERSION 常量"
    assert result["input_ticker_set_hash"], "input_ticker_set_hash MUST 非空"


def test_screen_a_shares_run_id_unique_per_call():
    """相同 tickers + 相同日两次调用返回不同 run_id（uuid4 每次唯一，D2 纠正）.

    原 test_screen_a_shares_run_id_stable_for_same_input 断言「相同 run_id」失效——
    D2 纠正：run_id 改 uuid4，每次执行唯一，与 D6「同日不同 run 不覆盖」一致。
    mock date.today 固定日期，消除日期波动；即使日期固定 run_id 仍不同（uuid4 随机）。
    """
    tickers = ["600519", "000001"]
    fake_all_data = {
        "600519": _make_ticker_data(),
        "000001": _make_ticker_data(industry="银行"),
    }
    fixed_date_str = "2026-07-21"

    results = []
    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        with patch("screener.main.date") as mock_d:
            mock_d.today.return_value.isoformat.return_value = fixed_date_str
            r1 = screen_a_shares(tickers)
            r2 = screen_a_shares(tickers)
            results = [r1, r2]

    assert results[0]["run_id"] != results[1]["run_id"], \
        "uuid4 run_id MUST 每次唯一（即使相同输入 + 相同日，D2 纠正 + D6 同日不覆盖）"
    # input_hash 仍确定（相同集合相同 hash，与 run_id 解耦）
    assert results[0]["input_ticker_set_hash"] == results[1]["input_ticker_set_hash"], \
        "input_ticker_set_hash 确定性不变（与 run_id 解耦）"


def test_screen_a_shares_run_id_is_uuid4_format():
    """run_id SHALL 是 uuid4 标准格式（uuid.UUID 解析不抛错 + version==4）."""
    import uuid
    tickers = ["600519"]
    fake_all_data = {"600519": _make_ticker_data()}
    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        result = screen_a_shares(tickers)
    parsed = uuid.UUID(result["run_id"])
    assert parsed.version == 4, "run_id MUST 是 uuid4"


def test_screen_a_shares_candidates_use_canonical_ticker():
    """L1 candidate ticker SHALL canonical 化（问题2：candidate/L2/watchlist 统一 canonical）.

    screen_a_shares 用原始输入构造 candidate（CLI 全市场输入常纯数字 600519），
    若原样透传纯数字，L2 full result / watchlist 会与 canonical 形式分裂。
    candidate["ticker"] SHALL 是 canonical（600519.SH），非原样纯数字。
    """
    tickers = ["600519"]  # 纯数字输入（CLI 全市场快照常见形式）
    fake_all_data = {"600519": _make_ticker_data()}  # all_data key 是原始 ticker
    with patch("screener.main.BatchFetcher") as MockBF:
        MockBF.return_value.fetch_all.return_value = fake_all_data
        result = screen_a_shares(tickers)

    candidates = result.get("candidates", [])
    assert len(candidates) >= 1
    assert candidates[0]["ticker"] == "600519.SH", \
        "candidate ticker SHALL canonical 化（600519 → 600519.SH），MUST NOT 原样透传纯数字"


def test_screen_a_shares_run_id_differs_for_different_input():
    """不同 ticker 集合 → run_id 不同（定位「输入变了」）."""
    fake_a = {"600519": _make_ticker_data()}
    fake_b = {"000001": _make_ticker_data(industry="银行")}
    from unittest.mock import MagicMock
    fixed_date_str = "2026-07-21"
    results = []
    with patch("screener.main.BatchFetcher") as MockBF, \
         patch("screener.main.date") as mock_d:
        mock_d.today.return_value.isoformat.return_value = fixed_date_str
        MockBF.return_value.fetch_all.return_value = fake_a
        results.append(screen_a_shares(["600519"]))
        MockBF.return_value.fetch_all.return_value = fake_b
        results.append(screen_a_shares(["000001"]))
    assert results[0]["run_id"] != results[1]["run_id"], \
        "输入变化 run_id MUST 可区分"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
