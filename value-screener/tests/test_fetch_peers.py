"""f3a §1.3/1.4: PeersFetcher 单元测试（D2 决策 (c)，纯数据层零 LLM）.

竞品对比 fetcher：依赖 industry 字段，调 stock_board_industry_cons_em(industry) 拿成分股，
算 peer_avg_pe / 行业排名。industry 缺失 → 返 __error__（触发 dossier 降级）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.fetchers.fetch_peers import PeersFetcher
import data.fetchers.fetch_peers as _peers_mod


@pytest.fixture(autouse=True)
def _reset_industry_cons_cache():
    """每个 case 清空模块级 _LazyTable 缓存，避免跨用例 df 污染."""
    _peers_mod._lazy_industry_cons.clear()
    yield
    _peers_mod._lazy_industry_cons.clear()


def _cons_df() -> pd.DataFrame:
    """模拟 stock_board_industry_cons_em 返回：行业成分股含 PE/PB."""
    return pd.DataFrame([
        {"序号": 1, "代码": "000089", "名称": "深圳机场", "最新价": 6.33,
         "涨跌幅": 1.61, "涨跌额": 0.10, "成交量": 46505, "成交额": 29173817.0,
         "振幅": 2.25, "最高": 6.33, "最低": 6.19, "今开": 6.19, "昨收": 6.23,
         "换手率": 0.23, "市盈率-动态": 12.57, "市净率": 1.12},
        {"序号": 2, "代码": "600004", "名称": "白云机场", "最新价": 7.48,
         "涨跌幅": 0.0, "涨跌额": 0.0, "成交量": 28630, "成交额": 21354406.0,
         "振幅": 1.20, "最高": 7.50, "最低": 7.41, "今开": 7.42, "昨收": 7.48,
         "换手率": 0.12, "市盈率-动态": 28.74, "市净率": 0.91},
        {"序号": 3, "代码": "600009", "名称": "上海机场", "最新价": 30.0,
         "涨跌幅": 0.0, "涨跌额": 0.0, "成交量": 100, "成交额": 3000.0,
         "振幅": 0.0, "最高": 30.0, "最低": 30.0, "今开": 30.0, "昨收": 30.0,
         "换手率": 0.0, "市盈率-动态": 26.42, "市净率": 3.0},
        {"序号": 4, "代码": "600897", "名称": "厦门空港", "最新价": 14.63,
         "涨跌幅": -0.27, "涨跌额": -0.04, "成交量": 4438, "成交额": 6488741.0,
         "振幅": 0.95, "最高": 14.71, "最低": 14.57, "今开": 14.58, "昨收": 14.67,
         "换手率": 0.11, "市盈率-动态": 12.99, "市净率": 1.27},
    ])


# ── 主路径 ──────────────────────────────────────────────────────


class TestPeersFetch:
    def test_dim_attribute(self):
        assert PeersFetcher.dim == "peers"

    def test_fetch_returns_peer_avg_pe_and_rank(self):
        """industry 已知 → 调 cons_em 拿成分股，算 peer_avg_pe + 行业排名."""
        fetcher = PeersFetcher()
        # 注入 industry（模拟从 basic cache 读到 industry="航空机场"）
        fetcher._test_industry_override = "航空机场"
        with patch("data.fetchers.fetch_peers.ak.stock_board_industry_cons_em",
                   return_value=_cons_df()):
            data = fetcher.fetch("600009")
        assert data["code"] == "600009"
        assert data["industry"] == "航空机场"
        # peer_avg_pe 是除自身外其他成分股 PE 均值
        # 其他成分 PE = [12.57, 28.74, 12.99] → 均值 ≈ 18.1
        assert "peer_avg_pe" in data
        assert data["peer_avg_pe"] == pytest.approx((12.57 + 28.74 + 12.99) / 3, abs=0.01)
        # 行业排名：按 PE 排序，自身排名
        assert "industry_pe_rank" in data
        assert "peer_count" in data
        assert data["peer_count"] == 4  # 含自身

    def test_fetch_peer_list_excludes_self_pe(self):
        """peer_pe_list 应含所有成分股 PE（含自身），但 peer_avg_pe 排除自身."""
        fetcher = PeersFetcher()
        fetcher._test_industry_override = "航空机场"
        with patch("data.fetchers.fetch_peers.ak.stock_board_industry_cons_em",
                   return_value=_cons_df()):
            data = fetcher.fetch("600009")
        pe_list = data.get("peer_pe_list", [])
        assert len(pe_list) == 4
        # 含自身的 26.42
        assert any(abs(p - 26.42) < 0.01 for p in pe_list)

    def test_industry_missing_returns_error(self):
        """industry 缺失（industry=None）→ fetch 抛 KeyError → fetch_with_fallback 返 __error__."""
        fetcher = PeersFetcher()
        fetcher._test_industry_override = None  # industry 缺失
        data = fetcher.fetch_with_fallback("600009")
        assert data.get("__error__") is True
        assert data.get("dim") == "peers"

    def test_cons_em_empty_raises(self):
        """cons_em 返空 → 抛 KeyError（由 fetch_with_fallback 兜底返 __error__）."""
        fetcher = PeersFetcher()
        fetcher._test_industry_override = "航空机场"
        with patch("data.fetchers.fetch_peers.ak.stock_board_industry_cons_em",
                   return_value=pd.DataFrame()):
            data = fetcher.fetch_with_fallback("600009")
        assert data.get("__error__") is True

    def test_industry_missing_with_fallback_returns_error(self):
        """industry 缺失 → fetch 抛 → fetch_with_fallback 无兜底 → __error__."""
        fetcher = PeersFetcher()
        fetcher._test_industry_override = None
        data = fetcher.fetch_with_fallback("600009")
        assert data.get("__error__") is True
        assert "peers" in data.get("error", "")

    def test_fetch_excludes_negative_pe_from_avg(self):
        """亏损股 PE 为负/None → peer_avg_pe 应过滤掉（亏损股 PE 无比较意义）."""
        df = _cons_df()
        df.loc[0, "市盈率-动态"] = -5.0  # 深圳机场变亏损
        fetcher = PeersFetcher()
        fetcher._test_industry_override = "航空机场"
        with patch("data.fetchers.fetch_peers.ak.stock_board_industry_cons_em",
                   return_value=df):
            data = fetcher.fetch("600009")
        # 排除自身 26.42 + 排除负 PE 的深圳机场 → 白云 28.74 + 厦门 12.99
        assert data["peer_avg_pe"] == pytest.approx((28.74 + 12.99) / 2, abs=0.01)
