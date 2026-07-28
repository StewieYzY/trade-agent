"""g1-4-data-source-resilience D1: industry_mapper 失败显式化测试.

承接 canonical data-minimum-contract §4「industry_mapper 静默空 dict」禁止项。
5533→18 根因：build_industry_map 东财失败静默返空 dict，下游 _fetch_industry_map
吞异常返 {}，全市场塌进「未分类」。
"""
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

# industry_mapper 顶部 import akshare 在函数内，故 patch ak.stock_board_industry_name_em
from data.lib import industry_mapper


def _make_fake_ak(board_name_raises=False, cons_raises=False, boards=None, cons_map=None):
    """构造 fake akshare 模块控制东财接口行为."""
    fake = types.ModuleType("akshare")

    def _board_name_em():
        if board_name_raises:
            raise KeyError("stock_board_industry_name_em blocked")
        return boards if boards is not None else _df([{"板块名称": "白酒"}, {"板块名称": "银行"}])

    def _board_cons_em(symbol):
        if cons_raises:
            raise KeyError(f"cons blocked for {symbol}")
        return cons_map.get(symbol) if cons_map else None

    fake.stock_board_industry_name_em = _board_name_em
    fake.stock_board_industry_cons_em = _board_cons_em
    return fake


def _df(rows):
    import pandas as pd
    return pd.DataFrame(rows)


@pytest.fixture
def clean_industry_cache(monkeypatch, tmp_path):
    """每个测试重置 _LazyTable 缓存 + industry_mapper 文件缓存（唯一路径，避免测试间缓存污染）."""
    # industry_mapper 的 _CACHE_FILE：每测试唯一路径，避免成功测试写的缓存污染失败测试
    cache_path = tmp_path / "_industry_map.json"
    monkeypatch.setattr(industry_mapper, "_CACHE_FILE", cache_path)
    # basic.py 的 _lazy_industry 是 _LazyTable 实例，重置其缓存
    import data.fetchers.basic as basic_mod
    basic_mod._lazy_industry.reset()
    yield
    basic_mod._lazy_industry.reset()


def test_build_industry_map_eastmoney_failure_returns_source_failed_status(clean_industry_cache, monkeypatch):
    """东财行业接口全失败时不得静默返空 dict，应返带 status=source_failed 的结构（D1）"""
    fake_ak = _make_fake_ak(board_name_raises=True)
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    result = industry_mapper.build_industry_map()

    # 不得返裸空 dict {} 掩盖失败
    assert not (isinstance(result, dict) and len(result) == 0 and not hasattr(result, "status")), (
        "东财全失败不得静默返空 dict {}，须显式标 source_failed"
    )
    assert getattr(result, "status", None) == "source_failed", (
        "东财全失败应返带 status=source_failed 的结构"
    )
    assert "eastmoney" in getattr(result, "attempted_sources", []), (
        "source_failed 应携带 attempted_sources"
    )


def test_build_industry_map_success_returns_available_status(clean_industry_cache, monkeypatch):
    """东财完整成功时返 available 状态 + 正常映射（D1）"""
    boards = _df([{"板块名称": "白酒"}])
    cons = _df([{"代码": "600519"}])
    fake_ak = _make_fake_ak(boards=boards, cons_map={"白酒": cons})
    monkeypatch.setitem(sys.modules, "akshare", fake_ak)

    result = industry_mapper.build_industry_map()

    assert getattr(result, "status", None) == "available"
    assert result.get("600519") == "白酒"
