"""f3a §2: build_research_dossier 单元测试（D1/D4/D5，纯 Python，零 LLM）.

分层研究档案组装：core_snapshot（21 量化，全员共享）+ research_dossier（角色分发）。
分层 fail-fast：core_snapshot + main_business 缺失 fail-fast；peers/research/capex_proxy 缺失降级标注。
"""
from __future__ import annotations

import sys
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.research_dossier import build_research_dossier


# ── 构造 mock fixtures ──────────────────────────────────────────


def _core_snapshot() -> dict:
    """21 量化字段（模拟 assemble_council_features 返回）."""
    return {
        "ticker": "600009",
        "pe_ttm": 26.42,
        "pb": 3.0,
        "roe_3y": [15.0, 16.0, 17.0],
        "net_margin": 30.0,
        "revenue_growth": 0.12,
        "f_score": 7,
    }


def _main_business() -> dict:
    return {
        "code": "600009",
        "report_date": "2025-12-31",
        "by_industry": [{"name": "航空及相关服务", "revenue": 1.2e10, "revenue_ratio": 0.94, "gross_margin": 0.25}],
        "by_product": [{"name": "航空及相关服务", "revenue": 1.25e10, "revenue_ratio": 0.94, "gross_margin": None}],
    }


def _peers() -> dict:
    return {
        "code": "600009",
        "industry": "航空机场",
        "peer_avg_pe": 18.1,
        "industry_pe_rank": 2,
        "peer_count": 4,
        "peer_pe_list": [12.57, 28.74, 26.42, 12.99],
    }


def _research() -> dict:
    return {
        "code": "600009",
        "consensus_eps": 1.152,
        "target_price": 30.41,
        "buy_rating_pct": 1.0,
        "coverage_count": 2,
        "rating_distribution": {"买入": 1, "增持": 1},
    }


def _financials_with_capex() -> dict:
    """financials cache 含 CONSTRUCT_LONG_ASSET（近3年 list）."""
    return {
        "years": ["2023", "2024", "2025"],
        "cash_flow": {
            "NETCASH_OPERATE": [5e9, 6e9, 7e9],
            "CONSTRUCT_LONG_ASSET": [1.244e9, 1.958e9, 1.307e9],
        },
        "income": {},
        "balance_sheet": {},
    }


def _risk_with_pledge() -> dict:
    """risk cache 含 pledge_ratio（芒格代理治理）."""
    return {"pledge_ratio": 8.5, "goodwill": None, "audit_opinion": None}


_ERROR = {"ticker": "600009", "__error__": True, "dim": "main_business", "error": "all_providers_failed:main_business"}


@contextmanager
def _patch_all_fetchers(mb=_main_business(), peers=_peers(), research=_research(),
                       fin=_financials_with_capex(), risk=_risk_with_pledge(), cache_get=None):
    """patch 3 fetcher + financials/risk cache 读取（contextmanager 确保 start/stop 配对）.

    f3a §2 测试：用 ExitStack 管理所有 patch，确保退出时全部还原，
    避免泄漏到后续测试（曾因 start/stop 用不同 patch 对象导致 CacheManager.get 泄漏）。
    """
    from data.fetchers.fetch_main_business import MainBusinessFetcher
    from data.fetchers.fetch_peers import PeersFetcher
    from data.fetchers.fetch_research import ResearchFetcher
    from data.cache.manager import CacheManager

    def fake_get(self, ticker, dim):
        if dim == "financials":
            return fin
        if dim == "risk":
            return risk
        return None
    if cache_get is not None:
        fake_get = cache_get

    with ExitStack() as stack:
        stack.enter_context(patch.object(MainBusinessFetcher, "fetch_with_fallback", return_value=mb))
        stack.enter_context(patch.object(PeersFetcher, "fetch_with_fallback", return_value=peers))
        stack.enter_context(patch.object(ResearchFetcher, "fetch_with_fallback", return_value=research))
        stack.enter_context(patch.object(CacheManager, "get", fake_get))
        yield


# ── §2.1 完整 dossier 组装 ─────────────────────────────────────


class TestBuildResearchDossierFull:
    def test_returns_layered_structure(self):
        """完整采集 → 返回 core_snapshot + research_dossier 含四维度 + degraded_fields."""
        with _patch_all_fetchers():
            dossier = build_research_dossier("600009", core_snapshot=_core_snapshot())
        assert "core_snapshot" in dossier
        assert "research_dossier" in dossier
        rd = dossier["research_dossier"]
        for dim in ("main_business", "peers", "capex_proxy", "research", "degraded_fields"):
            assert dim in rd, f"missing {dim}"
        # 完整采集 → degraded_fields 为空
        assert rd["degraded_fields"] == []

    def test_core_snapshot_passed_through(self):
        """core_snapshot 原样透传为顶层字段."""
        core = _core_snapshot()
        with _patch_all_fetchers():
            dossier = build_research_dossier("600009", core_snapshot=core)
        assert dossier["core_snapshot"] is core

    def test_capex_proxy_reads_construct_long_asset_latest(self):
        """capex_proxy 读 financials.cash_flow.CONSTRUCT_LONG_ASSET 取 [-1] 最新期."""
        with _patch_all_fetchers():
            dossier = build_research_dossier("600009", core_snapshot=_core_snapshot())
        capex = dossier["research_dossier"]["capex_proxy"]
        assert capex is not None
        # 最新期 1.307e9
        assert capex.get("latest") == pytest.approx(1.307e9, rel=0.01)

    def test_pledge_read_for_munger_proxy(self):
        """pledge 从 risk cache 读，作芒格治理代理（在 dossier 顶层或 research_dossier）."""
        with _patch_all_fetchers():
            dossier = build_research_dossier("600009", core_snapshot=_core_snapshot())
        # pledge 应可从 dossier 取到（芒格角色分发用）
        pledge = dossier.get("pledge") or dossier["research_dossier"].get("pledge")
        assert pledge == 8.5

    def test_core_snapshot_none_calls_assemble_council_features(self):
        """core_snapshot 缺省 → 内部调 assemble_council_features."""
        with patch("council.research_dossier.assemble_council_features",
                   return_value=_core_snapshot()) as mock_acf:
            with _patch_all_fetchers():
                dossier = build_research_dossier("600009")
            mock_acf.assert_called_once()
        assert "core_snapshot" in dossier


# ── §2.3 分层 fail-fast ────────────────────────────────────────


class TestLayeredFailFast:
    def test_core_snapshot_error_propagates(self):
        """core_snapshot 含 error → fail-fast 传播不组装 dossier."""
        with patch("council.research_dossier.assemble_council_features",
                   return_value={"error": "insufficient_data", "missing_fields": ["roe"]}):
            with pytest.raises(ValueError, match="insufficient_data|core_snapshot"):
                build_research_dossier("600009")

    def test_main_business_error_fail_fast(self):
        """main_business 返 __error__ → fail-fast（core+main_business 是核心）."""
        err = {"__error__": True, "dim": "main_business", "error": "all_providers_failed:main_business"}
        with _patch_all_fetchers(mb=err):
            with pytest.raises(ValueError, match="main_business"):
                build_research_dossier("600009", core_snapshot=_core_snapshot())

    def test_peers_error_degrades_not_blocks(self):
        """peers 返 __error__ → 降级标 degraded_fields=['peers']，不阻断."""
        err = {"__error__": True, "dim": "peers", "error": "industry unknown"}
        with _patch_all_fetchers(peers=err):
            dossier = build_research_dossier("600009", core_snapshot=_core_snapshot())
        assert "peers" in dossier["research_dossier"]["degraded_fields"]

    def test_research_empty_degrades_not_blocks(self):
        """research 返 coverage_count=0（小票无研报）→ 降级不阻断."""
        empty_research = {"code": "600009", "consensus_eps": None, "target_price": None,
                          "buy_rating_pct": 0.0, "coverage_count": 0, "rating_distribution": {}}
        with _patch_all_fetchers(research=empty_research):
            dossier = build_research_dossier("600009", core_snapshot=_core_snapshot())
        # research 字段存在但 coverage_count=0；是否标 degraded 看实现，至少不抛
        assert dossier["research_dossier"]["research"]["coverage_count"] == 0

    def test_capex_missing_degrades(self):
        """financials cache 缺 CONSTRUCT_LONG_ASSET → capex_proxy 降级标 degraded."""
        fin_no_capex = {"years": ["2023"], "cash_flow": {"NETCASH_OPERATE": [5e9]}, "income": {}, "balance_sheet": {}}
        with _patch_all_fetchers(fin=fin_no_capex):
            dossier = build_research_dossier("600009", core_snapshot=_core_snapshot())
        assert "capex_proxy" in dossier["research_dossier"]["degraded_fields"]

    def test_multiple_degraded_fields_accumulate(self):
        """peers + capex 都缺失 → degraded_fields 含两者."""
        peers_err = {"__error__": True, "dim": "peers", "error": "x"}
        fin_no_capex = {"years": ["2023"], "cash_flow": {"NETCASH_OPERATE": [5e9]}, "income": {}, "balance_sheet": {}}
        with _patch_all_fetchers(peers=peers_err, fin=fin_no_capex):
            dossier = build_research_dossier("600009", core_snapshot=_core_snapshot())
        df = dossier["research_dossier"]["degraded_fields"]
        assert "peers" in df
        assert "capex_proxy" in df
