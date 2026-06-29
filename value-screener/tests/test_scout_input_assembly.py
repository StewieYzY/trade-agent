"""Tests for scout/input_assembly.py (tasks 6.2, 6.3, 6.4)."""
import sys
from pathlib import Path
import tempfile
import json

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scout.input_assembly import assemble_snapshot
from data.cache.manager import CacheManager


def _create_mock_cache(ticker: str, cache_dir: Path, data: dict):
    """创建模拟缓存数据."""
    for dim, dim_data in data.items():
        cache_path = cache_dir / ticker / f"{dim}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(dim_data, ensure_ascii=False), encoding="utf-8")


def test_assemble_snapshot_basic():
    """验证 assemble_snapshot 组装基本特征."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        ticker = "600519"

        # 创建模拟数据
        mock_data = {
            "basic": {
                "name": "贵州茅台",
                "industry": "白酒",
                "market_cap": 2e12,  # 2 万亿
            },
            "valuation": {
                "pe_ttm": 38.5,
                "pb": 8.2,
                "pe_percentile_5y": 45.0,
            },
            "financials": {
                "income": {
                    "net_profit": [400e8, 450e8, 500e8],  # 近 3 年净利润
                    "revenue": [800e8, 900e8, 1000e8],  # 近 3 年营收
                },
                "balance_sheet": {
                    "TOTAL_ASSETS": [2000e8, 2200e8, 2400e8],
                    "TOTAL_CURRENT_LIAB": [200e8, 220e8, 240e8],
                    "TOTAL_NONCURRENT_LIAB": [100e8, 110e8, 120e8],
                    "GOODWILL": [0, 0, 0],
                },
                "cash_flow": {
                    "NETCASH_OPERATE": [450e8, 500e8, 550e8],
                },
            },
            "kline": {
                "close": [1800.0] * 250,  # 近 250 日收盘价
                "turnover_rate": [0.5] * 250,  # 换手率
            },
            "risk": {
                "pledge_ratio": 5.0,
                "audit_opinion": "标准无保留意见",
            },
        }

        _create_mock_cache(ticker, cache_dir, mock_data)

        cm = CacheManager(base_dir=str(cache_dir))
        features = assemble_snapshot(ticker, cache_manager=cm)

        # 验证基本字段
        assert features["ticker"] == ticker
        assert features["name"] == "贵州茅台"
        assert features["industry"] == "白酒"
        assert features["market_cap"] == 20000.0  # 2 万亿 / 1e8 = 20000 亿
        assert features["pe_ttm"] == 38.5
        assert features["pb"] == 8.2
        assert features["pe_percentile_5y"] == 45.0
        assert features["pledge_ratio"] == 5.0

        # 验证派生指标
        assert features["roe_3y"] is not None
        assert len(features["roe_3y"]) == 3
        assert features["roe_trend"] in ["趋势上升", "趋势下降", "趋势平稳", "数据不足"]
        assert features["net_margin"] is not None
        assert features["debt_ratio"] is not None
        assert features["goodwill_ratio"] is not None
        assert features["operating_cashflow"] is not None
        assert features["net_profit"] is not None
        assert features["cashflow_match"] in ["匹配", "不匹配", "部分匹配", "数据缺失"]
        assert features["revenue_growth"] is not None
        assert features["price_change_60d"] is not None
        assert features["turnover_percentile"] is not None


def test_assemble_snapshot_contract_pe_ttm_source():
    """验证 pe_ttm 从 valuation dim 取（不是 basic）."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        ticker = "000001"

        mock_data = {
            "basic": {
                "name": "平安银行",
                "industry": "银行",
                "market_cap": 3e11,
                "pe": 10.0,  # basic 中的 pe（不应被使用）
            },
            "valuation": {
                "pe_ttm": 12.5,  # valuation 中的 pe_ttm（应被使用）
                "pb": 0.8,
                "pe_percentile_5y": 30.0,
            },
            "financials": {
                "income": {"net_profit": [300e8, 320e8, 340e8], "revenue": [1500e8, 1600e8, 1700e8]},
                "balance_sheet": {
                    "TOTAL_ASSETS": [5e12, 5.2e12, 5.4e12],
                    "TOTAL_CURRENT_LIAB": [4e12, 4.2e12, 4.4e12],
                    "TOTAL_NONCURRENT_LIAB": [0.5e12, 0.52e12, 0.54e12],
                    "GOODWILL": [0, 0, 0],
                },
                "cash_flow": {"NETCASH_OPERATE": [400e8, 420e8, 440e8]},
            },
            "kline": {"close": [12.0] * 250, "turnover_rate": [1.0] * 250},
            "risk": {"pledge_ratio": 10.0},
        }

        _create_mock_cache(ticker, cache_dir, mock_data)

        cm = CacheManager(base_dir=str(cache_dir))
        features = assemble_snapshot(ticker, cache_manager=cm)

        # 验证 pe_ttm 来自 valuation（12.5），不是 basic（10.0）
        assert features["pe_ttm"] == 12.5


def test_assemble_snapshot_insufficient_data_critical_missing():
    """验证 insufficient data guard: 关键字段缺失."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        ticker = "999999"

        # 缺少 name/industry/market_cap
        mock_data = {
            "basic": {},
            "valuation": {"pe_ttm": 20.0, "pb": 2.0},
            "financials": {
                "income": {"net_profit": [100e8], "revenue": [500e8]},
                "balance_sheet": {
                    "TOTAL_ASSETS": [1000e8],
                    "TOTAL_CURRENT_LIAB": [500e8],
                    "TOTAL_NONCURRENT_LIAB": [200e8],
                    "GOODWILL": [0],
                },
                "cash_flow": {"NETCASH_OPERATE": [120e8]},
            },
        }

        _create_mock_cache(ticker, cache_dir, mock_data)

        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot(ticker, cache_manager=cm)

        # 验证触发 insufficient data guard
        assert "error" in result
        assert result["error"] == "insufficient_data"
        assert "missing_fields" in result
        assert "name" in result["missing_fields"]
        assert "industry" in result["missing_fields"]
        assert "market_cap" in result["missing_fields"]


def test_assemble_snapshot_insufficient_data_too_many_missing():
    """验证 insufficient data guard: >50% 字段缺失."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        ticker = "888888"

        # 只提供 name/industry/market_cap（避免触发 critical fields guard）
        # 但其他大部分字段缺失
        mock_data = {
            "basic": {
                "name": "测试股票",
                "industry": "测试行业",
                "market_cap": 1e10,
            },
            # 其他维度全部为空
        }

        _create_mock_cache(ticker, cache_dir, mock_data)

        cm = CacheManager(base_dir=str(cache_dir))
        result = assemble_snapshot(ticker, cache_manager=cm)

        # 验证触发 insufficient data guard（>50% 字段缺失）
        assert "error" in result
        assert result["error"] == "insufficient_data"
        assert "missing_fields" in result
        # 应该有很多缺失字段
        assert len(result["missing_fields"]) > 8  # 总共有 17 个数据字段，>50% 即 >8.5


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
