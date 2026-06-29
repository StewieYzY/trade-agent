"""Tests for scout/prompt.py (tasks 6.1)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scout.prompt import SCOUT_SYSTEM_PROMPT, format_snapshot


def test_system_prompt_structure():
    """验证 system prompt 包含 5 个问题 + JSON schema."""
    assert "1. 这是一家什么生意" in SCOUT_SYSTEM_PROMPT
    assert "2. 便宜吗" in SCOUT_SYSTEM_PROMPT
    assert "3. 生意好吗" in SCOUT_SYSTEM_PROMPT
    assert "4. 有什么明显的红旗" in SCOUT_SYSTEM_PROMPT
    assert "5. 一句话结论" in SCOUT_SYSTEM_PROMPT
    assert '"verdict"' in SCOUT_SYSTEM_PROMPT
    assert '"confidence"' in SCOUT_SYSTEM_PROMPT
    assert '"one_liner"' in SCOUT_SYSTEM_PROMPT
    assert '"red_flags"' in SCOUT_SYSTEM_PROMPT
    assert '"green_flags"' in SCOUT_SYSTEM_PROMPT
    assert '"anti_trap_flags"' in SCOUT_SYSTEM_PROMPT


def test_format_snapshot_basic():
    """验证 format_snapshot 渲染基本字段."""
    features = {
        "ticker": "600519",
        "name": "贵州茅台",
        "industry": "白酒",
        "market_cap": 20000,
        "pe_ttm": 38.5,
        "pb": 8.2,
        "pe_percentile_5y": 45.0,
        "roe_3y": [28.5, 25.3, 22.1],
        "roe_trend": "趋势下降",
        "net_margin": 52.3,
        "debt_ratio": 18.5,
        "goodwill_ratio": 0.0,
        "operating_cashflow": 450.0,
        "net_profit": 420.0,
        "cashflow_match": "匹配",
        "revenue_growth": 15.2,
        "pledge_ratio": 5.0,
        "price_change_60d": 12.5,
        "turnover_percentile": 65.0,
        "f_score": 8,
    }

    output = format_snapshot(features)

    # 验证关键字段
    assert "贵州茅台 (600519)" in output
    assert "白酒" in output
    assert "20000亿" in output
    assert "38.5" in output
    assert "8.2" in output
    # pe_percentile_5y=45.0 -> pct() 去掉 .0 -> "45%"
    assert "45%" in output
    assert "趋势下降" in output
    assert "52.3" in output
    assert "18.5" in output
    assert "匹配" in output
    assert "15.2" in output
    assert "5%" in output  # pledge_ratio=5.0 -> "5%"
    assert "12.5" in output
    assert "65%" in output  # turnover_percentile=65.0 -> "65%"
    assert "8/9" in output


def test_format_snapshot_missing_data():
    """验证 format_snapshot 处理缺失数据."""
    features = {
        "ticker": "000001",
        "name": None,
        "industry": None,
        "market_cap": None,
        "pe_ttm": None,
        "pb": None,
        "pe_percentile_5y": None,
        "roe_3y": None,
        "roe_trend": "数据缺失",
        "net_margin": None,
        "debt_ratio": None,
        "goodwill_ratio": None,
        "operating_cashflow": None,
        "net_profit": None,
        "cashflow_match": "数据缺失",
        "revenue_growth": None,
        "pledge_ratio": None,
        "price_change_60d": None,
        "turnover_percentile": None,
        "f_score": None,
    }

    output = format_snapshot(features)

    # 验证缺失字段渲染为 "数据缺失"
    assert "数据缺失" in output
    assert output.count("数据缺失") >= 10  # 大部分字段缺失


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
