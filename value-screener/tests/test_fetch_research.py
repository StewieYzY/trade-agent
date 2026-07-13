"""f3a §1.5/1.6: ResearchFetcher 单元测试（D2 决策 (c)，纯数据层零 LLM）.

研报共识 fetcher：consensus_eps/target_price/buy_rating_pct/coverage_count。
数据源 stock_research_report_em(symbol=code)，per-symbol（非全市场表，无需 _LazyTable）。
小票常返 0 条研报（记录降级）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.fetchers.fetch_research import ResearchFetcher


def _research_df() -> pd.DataFrame:
    """模拟 stock_research_report_em 返回：多条研报."""
    return pd.DataFrame([
        {"序号": 1, "股票代码": "600009", "股票简称": "上海机场",
         "报告名称": "业绩符合预期", "东财评级": "买入", "机构": "国金证券",
         "近一月个股研报数": 0, "2026-盈利预测-收益": 0.967, "2026-盈利预测-市盈率": 28.33,
         "2027-盈利预测-收益": 1.084, "2027-盈利预测-市盈率": 25.27,
         "行业": "航空机场", "日期": "2026-05-05"},
        {"序号": 2, "股票代码": "600009", "股票简称": "上海机场",
         "报告名称": "免税新局面", "东财评级": "增持", "机构": "群益证券",
         "近一月个股研报数": 0, "2026-盈利预测-收益": 1.220, "2026-盈利预测-市盈率": 27.59,
         "2027-盈利预测-收益": 1.220, "2027-盈利预测-市盈率": 27.52,
         "行业": "航空机场", "日期": "2025-12-22"},
    ])


class TestResearchFetch:
    def test_dim_attribute(self):
        assert ResearchFetcher.dim == "research"

    def test_fetch_returns_consensus_fields(self):
        """研报非空 → 返回 consensus_eps/target_price/buy_rating_pct/coverage_count."""
        fetcher = ResearchFetcher()
        with patch("data.fetchers.fetch_research.ak.stock_research_report_em",
                   return_value=_research_df()):
            data = fetcher.fetch("600009")
        assert data["code"] == "600009"
        for key in ("consensus_eps", "target_price", "buy_rating_pct", "coverage_count"):
            assert key in data, f"missing {key}"
        # coverage_count = 研报总数 = 2
        assert data["coverage_count"] == 2

    def test_consensus_eps_is_mean_of_forecasts(self):
        """consensus_eps = 各研报最新年份（2027，最大年份列）盈利预测收益的均值."""
        fetcher = ResearchFetcher()
        with patch("data.fetchers.fetch_research.ak.stock_research_report_em",
                   return_value=_research_df()):
            data = fetcher.fetch("600009")
        # 两条研报 2027 EPS = 1.084, 1.220 → 均值 ≈ 1.152（取最大年份列）
        assert data["consensus_eps"] == pytest.approx((1.084 + 1.220) / 2, abs=0.01)

    def test_buy_rating_pct_calculated(self):
        """buy_rating_pct = 买入/增持 评级占比（含买入+增持，视为看多）."""
        fetcher = ResearchFetcher()
        with patch("data.fetchers.fetch_research.ak.stock_research_report_em",
                   return_value=_research_df()):
            data = fetcher.fetch("600009")
        # 买入 1 + 增持 1 = 2/2 = 1.0
        assert data["buy_rating_pct"] == pytest.approx(1.0, abs=0.01)

    def test_target_price_from_eps_times_pe(self):
        """target_price = consensus_eps × consensus_pe（最新年份 EPS × PE）."""
        fetcher = ResearchFetcher()
        with patch("data.fetchers.fetch_research.ak.stock_research_report_em",
                   return_value=_research_df()):
            data = fetcher.fetch("600009")
        # 2027 PE 均值 = (25.27+27.52)/2 = 26.395, EPS 均值 = 1.152
        # target_price = 1.152 × 26.395 ≈ 30.41
        assert data["target_price"] is not None
        assert data["target_price"] == pytest.approx(1.152 * 26.395, abs=0.5)

    def test_empty_research_returns_zero_coverage(self):
        """小票研报为空（df 空）→ coverage_count=0，consensus_eps=None（降级不抛）."""
        fetcher = ResearchFetcher()
        with patch("data.fetchers.fetch_research.ak.stock_research_report_em",
                   return_value=pd.DataFrame()):
            data = fetcher.fetch("600009")
        assert data["coverage_count"] == 0
        assert data["consensus_eps"] is None
        assert data["target_price"] is None
        assert data["buy_rating_pct"] == 0.0

    def test_fetch_with_fallback_all_fail_returns_error(self):
        """接口异常 → fetch 抛 → fetch_with_fallback 返 __error__."""
        fetcher = ResearchFetcher()
        with patch("data.fetchers.fetch_research.ak.stock_research_report_em",
                   side_effect=KeyError("research empty")):
            data = fetcher.fetch_with_fallback("600009")
        assert data.get("__error__") is True
        assert data.get("dim") == "research"

    def test_partial_missing_eps_filtered(self):
        """部分研报最新年份 EPS 为 NaN → consensus_eps 只用有效研报."""
        df = _research_df()
        df.loc[0, "2027-盈利预测-收益"] = None  # 第一条最新年份 EPS 缺失
        fetcher = ResearchFetcher()
        with patch("data.fetchers.fetch_research.ak.stock_research_report_em",
                   return_value=df):
            data = fetcher.fetch("600009")
        # 只剩第二条 2027 EPS = 1.220
        assert data["consensus_eps"] == pytest.approx(1.220, abs=0.01)
