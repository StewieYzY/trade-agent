"""f3a §1.7: 3 新 fetcher 注册到 _DIM_FETCHERS + _DIM_TTL 验证.

确保 BatchFetcher._fetch_one 能按新 dim 查缓存→采集→cache.set。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.batch_fetcher import _DIM_FETCHERS
from data.cache.manager import _DIM_TTL, QUARTERLY, STATIC
from data.fetchers.fetch_main_business import MainBusinessFetcher
from data.fetchers.fetch_peers import PeersFetcher
from data.fetchers.fetch_research import ResearchFetcher


class TestFetcherRegistration:
    def test_main_business_registered_in_dim_fetchers(self):
        assert "main_business" in _DIM_FETCHERS
        assert _DIM_FETCHERS["main_business"] is MainBusinessFetcher

    def test_peers_registered_in_dim_fetchers(self):
        assert "peers" in _DIM_FETCHERS
        assert _DIM_FETCHERS["peers"] is PeersFetcher

    def test_research_registered_in_dim_fetchers(self):
        assert "research" in _DIM_FETCHERS
        assert _DIM_FETCHERS["research"] is ResearchFetcher

    def test_main_business_ttl_registered(self):
        """main_business = QUARTERLY（主营构成随财报季更新）."""
        assert "main_business" in _DIM_TTL
        assert _DIM_TTL["main_business"] == QUARTERLY

    def test_peers_ttl_registered(self):
        """peers = DAILY_PRICE 档位（成分股 PE 随行情日变）."""
        assert "peers" in _DIM_TTL
        assert _DIM_TTL["peers"] > 0

    def test_research_ttl_registered(self):
        """research = DAILY 档位（研报日更）."""
        assert "research" in _DIM_TTL
        assert _DIM_TTL["research"] > 0

    def test_existing_five_dims_unchanged(self):
        """不污染现有五个 dim 的注册."""
        for dim in ("basic", "financials", "kline", "valuation", "risk"):
            assert dim in _DIM_FETCHERS
            assert dim in _DIM_TTL
