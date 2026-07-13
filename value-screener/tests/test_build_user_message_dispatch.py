"""f3a §3.1/3.2: _build_user_message 角色分发测试（D3，最敏感步骤）.

_build_user_message 加 agent_id 形参，按 agent_id 从 dossier 的 research_dossier 取角色侧重子集。
core_snapshot 全员共享，定性维度按 D1 角色表分发。
DA/Synthesizer 走全量路径。agent_id=None 退化全员共享（向后兼容）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.debate import _build_user_message


def _full_dossier() -> dict:
    """构造完整分层 dossier（各维度带可辨识字段值）."""
    return {
        "core_snapshot": {
            "ticker": "600009",
            "pe_ttm": 26.42,
            "roe_3y": [15.0, 16.0, 17.0],
        },
        "research_dossier": {
            "main_business": {"code": "600009", "by_industry": [{"name": "航空", "revenue_ratio": 0.94}]},
            "peers": {"code": "600009", "peer_avg_pe": 18.1, "industry_pe_rank": 2},
            "capex_proxy": {"latest": 1.307e9, "series": [1.244e9, 1.958e9, 1.307e9]},
            "research": {"consensus_eps": 1.152, "target_price": 30.41, "buy_rating_pct": 1.0, "coverage_count": 2},
            "degraded_fields": [],
        },
        "pledge": 8.5,
    }


# ── 角色分发断言 helper ────────────────────────────────────────


def _contains(msg: str, marker: str) -> bool:
    return marker in msg


class TestBuildUserMessageDispatch:
    def test_buffett_gets_business_peers_capex_not_research(self):
        """buffett = main_business + peers + capex_proxy，不含 research."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="buffett")
        # 含 core_snapshot 全员共享
        assert _contains(msg, "pe_ttm")
        # 含 main_business / peers / capex_proxy
        assert _contains(msg, "by_industry") or _contains(msg, "主营")
        assert _contains(msg, "peer_avg_pe")
        assert _contains(msg, "capex") or _contains(msg, "CONSTRUCT") or _contains(msg, "1.307")
        # 不含 research（consensus_eps/target_price/buy_rating）
        assert not _contains(msg, "consensus_eps")
        assert not _contains(msg, "target_price")

    def test_feng_liu_gets_research_capex_not_business_peers(self):
        """feng_liu = research + capex_proxy，不含 main_business/peers."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="feng_liu")
        assert _contains(msg, "pe_ttm")  # core 全员共享
        assert _contains(msg, "consensus_eps")
        assert _contains(msg, "target_price")
        assert _contains(msg, "capex") or _contains(msg, "1.307")
        # 不含 main_business / peers
        assert not _contains(msg, "by_industry")
        assert not _contains(msg, "peer_avg_pe")

    def test_munger_gets_business_peers_pledge(self):
        """munger = main_business + peers + pledge（代理治理）."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="munger")
        assert _contains(msg, "pe_ttm")
        assert _contains(msg, "by_industry") or _contains(msg, "主营")
        assert _contains(msg, "peer_avg_pe")
        assert _contains(msg, "pledge")
        # 不含 research
        assert not _contains(msg, "consensus_eps")

    def test_duan_gets_business_peers_research(self):
        """duan = main_business + peers + research."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="duan")
        assert _contains(msg, "by_industry") or _contains(msg, "主营")
        assert _contains(msg, "peer_avg_pe")
        assert _contains(msg, "consensus_eps")
        # 不含 capex（dossier.cabex 不给段永平）—— 注：capex 字段名 'capex_proxy'
        assert not _contains(msg, "capex_proxy")

    def test_da_gets_full_dossier(self):
        """DA 走全量路径（不分发），含所有维度."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="da")
        assert _contains(msg, "by_industry") or _contains(msg, "主营")
        assert _contains(msg, "peer_avg_pe")
        assert _contains(msg, "consensus_eps")
        assert _contains(msg, "capex") or _contains(msg, "1.307")
        assert _contains(msg, "pledge")

    def test_synthesizer_gets_full_dossier(self):
        """Synthesizer 走全量路径."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="synthesizer")
        assert _contains(msg, "by_industry") or _contains(msg, "主营")
        assert _contains(msg, "consensus_eps")
        assert _contains(msg, "capex") or _contains(msg, "1.307")

    def test_agent_id_none_degrades_to_full(self):
        """agent_id=None 退化全员共享（向后兼容 fallback）."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id=None)
        # 退化路径：含全部维度（与旧行为一致，整个 features json.dumps）
        assert _contains(msg, "by_industry") or _contains(msg, "主营")
        assert _contains(msg, "consensus_eps")
        assert _contains(msg, "capex")

    def test_core_snapshot_always_present(self):
        """任意 agent 都含完整 core_snapshot（21 量化字段全员共享）."""
        for agent_id in ("buffett", "munger", "duan", "feng_liu", "da", "synthesizer"):
            msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id=agent_id)
            assert _contains(msg, "pe_ttm"), f"{agent_id} 缺 core_snapshot"

    def test_degraded_field_noted_in_message(self):
        """peers 降级时，对应 agent 的 user message 注明维度缺失（不静默退化）."""
        dossier = _full_dossier()
        dossier["research_dossier"]["peers"] = {"__error__": True, "reason": "industry 缺失"}
        dossier["research_dossier"]["degraded_fields"] = ["peers"]
        msg = _build_user_message("600009", dossier, other_opinions=None, agent_id="buffett")
        # 注明竞品维度缺失
        assert "缺失" in msg or "degraded" in msg.lower() or "降级" in msg


class TestBuildUserMessageStillHandlesOtherOpinions:
    def test_other_opinions_still_appended(self):
        """加 agent_id 后，R2 的 other_opinions 仍正常拼接（不破坏 R2 路径）."""
        from council.schema import AgentOutput
        opinion = AgentOutput(name="munger", signal="bullish", conviction=80,
                              core_thesis="看好长期价值",
                              what_would_change_my_mind="业绩下滑", out_of_circle=False)
        msg = _build_user_message("600009", _full_dossier(),
                                  other_opinions=[opinion], agent_id="buffett")
        assert "其他分析师" in msg
        assert "看好长期价值" in msg
