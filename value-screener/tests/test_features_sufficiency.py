"""Tests for financials_floor guard (f1-deviation-fix §2, D2).

构造 features dict，name/market_cap 有值但 pe_ttm/roe_3y/net_margin 全 None 的场景，
断言 assemble_snapshot 返回 insufficient_data + missing_fields 含财务三件套。

背景（spec council-debate: R1 features 充分性门）：原 guard 的漏洞是
critical_fields=["name","market_cap"] + missing_ratio>0.5——basic 维命中时
critical 通过，financials 维全空时缺失率可能才 ~40%，guard 放行，模型拿
无财务数据的 dict 靠 system prompt 案例锚定编造（600519 幻觉触发路径）。
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.cache.manager import CacheManager
from council.debate import run_debate
from scout.input_assembly import assemble_snapshot


def _create_mock_cache(ticker: str, cache_dir: Path, data: dict):
    for dim, dim_data in data.items():
        cache_path = cache_dir / ticker / f"{dim}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(dim_data, ensure_ascii=False), encoding="utf-8")


def test_financials_floor_all_none_triggers_insufficient_data():
    """核心漏洞修复：basic 命中但 financials 三件套全 None → fail-fast.

    复现 design 假设的幻觉触发路径——name/market_cap 有值（critical_fields 通过），
    但 pe_ttm/roe_3y/net_margin 全 None。原 guard 因缺失率 <50% 放行；新 guard
    因 financials_floor 不齐而拦截。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        ticker = "600519"

        # basic 命中（name/market_cap 有值）——满足 critical_fields
        # valuation 有 pe_ttm，但 financials 维全空 → roe_3y/net_margin 为 None
        # 注意：pe_ttm 来自 valuation，这里故意不给，模拟 valuation 缺 pe_ttm
        mock_data = {
            "basic": {
                "name": "贵州茅台",
                "industry": "白酒",
                "market_cap": 2e12,
            },
            # valuation 缺 pe_ttm → pe_ttm 为 None
            "valuation": {"pb": 8.2, "pe_percentile_5y": 45.0},
            # financials 全空 → roe_3y / net_margin 为 None
            "financials": {},
            "kline": {"close": [1800.0] * 250, "turnover_rate": [0.5] * 250},
            "risk": {"pledge_ratio": 5.0, "audit_opinion": "标准无保留意见"},
        }

        _create_mock_cache(ticker, cache_dir, mock_data)
        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot(ticker, cache_manager=cm)

        # 新 guard：financials_floor 不齐 → insufficient_data
        assert "error" in result, f"期望 insufficient_data，实际返回 {list(result.keys())}"
        assert result["error"] == "insufficient_data"
        assert "missing_fields" in result
        # 财务三件套必须在 missing_fields 中
        assert "pe_ttm" in result["missing_fields"]
        assert "roe_3y" in result["missing_fields"]
        assert "net_margin" in result["missing_fields"]


def test_financials_floor_one_none_triggers_insufficient_data():
    """financials_floor 任一为 None 即 fail-fast（spec: 任一缺失则 features 不足以支撑质性判断）."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        ticker = "600900"

        mock_data = {
            "basic": {"name": "长江电力", "industry": "电力", "market_cap": 6e11},
            "valuation": {"pe_ttm": 18.2, "pb": 2.88, "pe_percentile_5y": 50.0},
            # financials 只能给 roe_3y，net_margin 缺（revenue 为空）
            "financials": {
                "income": {"net_profit": [100e8, 110e8, 120e8]},  # 无 revenue → net_margin None
                "balance_sheet": {
                    "TOTAL_ASSETS": [2000e8, 2200e8, 2400e8],
                    "TOTAL_CURRENT_LIAB": [200e8, 220e8, 240e8],
                    "TOTAL_NONCURRENT_LIAB": [100e8, 110e8, 120e8],
                    "GOODWILL": [0, 0, 0],
                },
                "cash_flow": {"NETCASH_OPERATE": [120e8, 130e8, 140e8]},
            },
            "kline": {"close": [20.0] * 250, "turnover_rate": [0.3] * 250},
            "risk": {"pledge_ratio": 1.0},
        }

        _create_mock_cache(ticker, cache_dir, mock_data)
        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot(ticker, cache_manager=cm)

        assert "error" in result
        assert result["error"] == "insufficient_data"
        # net_margin 缺失
        assert "net_margin" in result["missing_fields"]


def test_financials_floor_complete_passes_guard():
    """财务三件套齐全 + critical 齐全 → 通过 guard，返回正常 features dict."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        ticker = "600009"

        mock_data = {
            "basic": {"name": "上海机场", "industry": "机场", "market_cap": 6e10},
            "valuation": {"pe_ttm": 26.42, "pb": 1.33, "pe_percentile_5y": 40.0},
            "financials": {
                "income": {"net_profit": [20e8, 22e8, 25e8], "revenue": [50e8, 55e8, 60e8]},
                "balance_sheet": {
                    "TOTAL_ASSETS": [400e8, 420e8, 440e8],
                    "TOTAL_CURRENT_LIAB": [60e8, 65e8, 70e8],
                    "TOTAL_NONCURRENT_LIAB": [80e8, 85e8, 90e8],
                    "GOODWILL": [0, 0, 0],
                },
                "cash_flow": {"NETCASH_OPERATE": [30e8, 33e8, 36e8]},
            },
            "kline": {"close": [40.0] * 250, "turnover_rate": [0.4] * 250},
            "risk": {"pledge_ratio": 2.0, "audit_opinion": "标准无保留意见"},
        }

        _create_mock_cache(ticker, cache_dir, mock_data)
        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot(ticker, cache_manager=cm)

        # 通过 guard，返回正常 features
        assert "error" not in result
        assert result["name"] == "上海机场"
        assert result["pe_ttm"] == 26.42
        assert result["roe_3y"] is not None
        assert result["net_margin"] is not None


def test_financials_floor_error_message_actionable():
    """spec council-debate Scenario: 错误信息含缺失字段列表，提示用户先跑 batch（review-notes #1 联动）.

    verify_quality_gate / debate 消费 error 时，missing_fields 需可读，便于
    错误消息提示"先跑 batch 重采"。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        ticker = "600519"
        mock_data = {
            "basic": {"name": "贵州茅台", "market_cap": 2e12},
            "valuation": {"pb": 8.2},  # 缺 pe_ttm
            "financials": {},  # 缺 roe_3y / net_margin
        }
        _create_mock_cache(ticker, cache_dir, mock_data)
        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot(ticker, cache_manager=cm)

        assert result["error"] == "insufficient_data"
        missing = result["missing_fields"]
        # 三件套都在
        assert set(["pe_ttm", "roe_3y", "net_margin"]).issubset(set(missing))
        # missing_fields 是 list[str]，可拼成可操作错误消息
        assert isinstance(missing, list)
        assert all(isinstance(f, str) for f in missing)


# ── P4 修复：guard 区分三种触发路径 ──────────────────────────────


def test_guard_distinguishes_critical_fields_path():
    """P4: basic 维度缺失（name/market_cap）→ guard='critical_fields'."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        mock_data = {
            "basic": {},  # name/market_cap 都缺
            "valuation": {"pe_ttm": 20.0, "pb": 2.0},
            "financials": {"income": {"net_profit": [100e8], "revenue": [500e8]},
                           "balance_sheet": {"TOTAL_ASSETS": [1000e8], "TOTAL_CURRENT_LIAB": [500e8],
                                             "TOTAL_NONCURRENT_LIAB": [200e8], "GOODWILL": [0]}},
        }
        _create_mock_cache("999999", cache_dir, mock_data)
        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot("999999", cache_manager=cm)
        assert result["guard"] == "critical_fields"
        assert "name" in result["guard_detail"] or "market_cap" in result["guard_detail"]


def test_guard_distinguishes_financials_floor_path():
    """P4: basic 齐全但 financials 三件套缺 → guard='financials_floor'（核心漏洞路径）."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        mock_data = {
            "basic": {"name": "测试", "market_cap": 1e10},  # critical 齐全
            "valuation": {"pb": 2.0},  # 缺 pe_ttm
            "financials": {},  # 缺 roe_3y / net_margin
        }
        _create_mock_cache("600519", cache_dir, mock_data)
        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot("600519", cache_manager=cm)
        assert result["guard"] == "financials_floor"
        assert "财务三件套" in result["guard_detail"]


def test_guard_distinguishes_missing_ratio_path():
    """P4: critical 齐全 + financials_floor 齐全但整体缺失 >50% → guard='missing_ratio'.

    构造：basic 齐全、financials 三件套齐全（pe_ttm/roe_3y/net_margin 有值），
    但其他维度（kline/risk/pb/pe_percentile_5y/operating_cashflow/revenue_growth/
    pledge_ratio/price_change_60d/turnover_avg_percentile_60d 等）缺失 >50%。
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        mock_data = {
            "basic": {"name": "测试", "market_cap": 1e10},
            "valuation": {"pe_ttm": 20.0},  # pe_ttm 有；pb/pe_percentile_5y 缺
            "financials": {
                # 只给算 roe_3y + net_margin 的最小字段；不给 cash_flow/goodwill/revenue[-2]
                "income": {"net_profit": [100e8], "revenue": [500e8]},  # net_margin 可算、revenue_growth 缺（需 2 期）
                "balance_sheet": {"TOTAL_ASSETS": [1000e8], "TOTAL_CURRENT_LIAB": [500e8],
                                  "TOTAL_NONCURRENT_LIAB": [200e8]},  # 无 GOODWILL → goodwill_ratio=None
                # 无 cash_flow → operating_cashflow=None
            },
            # 不给 kline / risk → price_change_60d/turnover_avg_percentile_60d/pledge_ratio=None
        }
        _create_mock_cache("888888", cache_dir, mock_data)
        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot("888888", cache_manager=cm)
        # critical 齐全、financials_floor 齐全 → 走到 missing_ratio
        assert result["guard"] == "missing_ratio"
        assert "整体缺失率" in result["guard_detail"]


# ── 端到端透传：assemble_council_features → run_debate fail-fast（task 2.3 / 2.4）──


@pytest.mark.anyio
async def test_run_debate_fail_fast_on_insufficient_features(tmp_path, monkeypatch):
    """task 2.3: assemble_council_features 返回 insufficient_data → run_debate 透传 raise ValueError.

    spec council-debate Scenario: features 返回 insufficient_data 错误时 R1 fail-fast。
    验证：不调用任何 LLM（mock call_llm 应未被触达），错误信息含缺失字段 + 可操作下一步。
    """
    # 让 assemble_council_features 返回 insufficient_data（模拟 cache 过期 / financials 缺）
    # P4 修复后 guard 返回含 guard + guard_detail
    insufficient = {
        "error": "insufficient_data",
        "missing_fields": ["pe_ttm", "roe_3y", "net_margin"],
        "guard": "financials_floor",
        "guard_detail": "财务三件套缺失（financials TTL 24h 可能过期，先跑 batch 重采）",
    }
    monkeypatch.setattr(
        "council.research_dossier.assemble_council_features",
        lambda t: insufficient,
    )
    # LLM 绝不应被调用——fail-fast 必须在 R1 入口前
    mock_llm = AsyncMock()
    monkeypatch.setattr("council.debate.call_llm", mock_llm)

    with pytest.raises(ValueError) as exc_info:
        await run_debate("600519", agents=["buffett"])

    msg = str(exc_info.value)
    # 含缺失字段
    assert "pe_ttm" in msg and "roe_3y" in msg and "net_margin" in msg
    # P4: 含 guard 标识 + guard_detail
    assert "financials_floor" in msg
    # 可操作的下一步指引——提示先跑 batch 重采
    assert "batch" in msg
    # LLM 未被触达
    mock_llm.assert_not_called()


@pytest.mark.anyio
async def test_run_debate_fail_fast_message_mentions_ttl(tmp_path, monkeypatch):
    """task 2.4 / P4: 错误消息含 guard_detail，提示 TTL 过期原因，便于用户判断重采."""
    insufficient = {
        "error": "insufficient_data",
        "missing_fields": ["name", "market_cap"],
        "guard": "critical_fields",
        "guard_detail": "basic 维度缺失（basic TTL 2h 可能过期，先跑 batch 重采 basic 维度）",
    }
    monkeypatch.setattr(
        "council.research_dossier.assemble_council_features",
        lambda t: insufficient,
    )
    monkeypatch.setattr("council.debate.call_llm", AsyncMock())

    with pytest.raises(ValueError) as exc_info:
        await run_debate("600900", agents=["buffett"])

    msg = str(exc_info.value)
    # P4: 含 guard 标识
    assert "critical_fields" in msg
    # 消息含 TTL 信息提示（basic 2h）
    assert "TTL" in msg
    assert "batch" in msg
