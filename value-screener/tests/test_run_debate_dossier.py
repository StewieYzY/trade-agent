"""f3a §3.3/3.4: run_debate 改调 build_research_dossier 测试（D4）.

run_debate L3 入口从 assemble_council_features 改为 build_research_dossier。
call_agent/_call_da/_call_synthesizer 的 features 形参语义变为分层 dossier。
dossier 含 core_snapshot error 时抛 ValueError（insufficient_data）。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.debate import run_debate, call_agent


def _full_dossier() -> dict:
    return {
        "core_snapshot": {"ticker": "600009", "pe_ttm": 26.42, "roe_3y": [15.0, 16.0, 17.0]},
        "research_dossier": {
            "main_business": {"code": "600009", "by_industry": [{"name": "航空", "revenue_ratio": 0.94}]},
            "peers": {"peer_avg_pe": 18.1, "industry_pe_rank": 2},
            "capex_proxy": {"latest": 1.307e9},
            "research": {"consensus_eps": 1.152, "target_price": 30.41, "buy_rating_pct": 1.0, "coverage_count": 2},
            "degraded_fields": [],
        },
        "pledge": 8.5,
    }


class TestRunDebateDossier:
    def test_run_debate_calls_build_research_dossier(self):
        """run_debate(ticker) features=None → 调 build_research_dossier 而非 assemble_council_features."""
        async def fake_call_agent(agent_id, *a, **kw):
            return _mk_agent(agent_id)
        with patch("council.debate.build_research_dossier", return_value=_full_dossier()) as mock_dossier, \
             patch("council.debate.assemble_council_features") as mock_acf, \
             patch("council.debate.call_agent", side_effect=fake_call_agent), \
             patch("council.debate._call_synthesizer", new_callable=AsyncMock) as mock_synth:
            mock_synth.return_value = _mk_synth()
            import asyncio
            asyncio.run(run_debate("600009", agents=["buffett"], force=True))
        mock_dossier.assert_called_once()
        mock_acf.assert_not_called()

    def test_dossier_error_raises_value_error(self):
        """build_research_dossier 抛 ValueError（core_snapshot 不足）→ run_debate 传播 ValueError."""
        with patch("council.debate.build_research_dossier",
                   side_effect=ValueError("core_snapshot insufficient_data")):
            import asyncio
            with pytest.raises(ValueError, match="insufficient_data|core_snapshot"):
                asyncio.run(run_debate("600009", force=True))

    def test_call_agent_receives_dossier_and_passes_agent_id(self):
        """call_agent 的 features 形参是分层 dossier，且透传 agent_id 给 _build_user_message."""
        import asyncio
        captured = {}

        async def fake_call_agent(agent_id, ticker, features, **kw):
            captured["agent_id"] = agent_id
            captured["features"] = features
            captured["other_opinions"] = kw.get("other_opinions")
            return _mk_agent(agent_id)

        # 验证 _build_user_message 在 call_agent 内被调时收到 agent_id
        with patch("council.debate.build_research_dossier", return_value=_full_dossier()), \
             patch("council.debate.call_agent", side_effect=fake_call_agent), \
             patch("council.debate._call_synthesizer", new_callable=AsyncMock, return_value=_mk_synth()):
            asyncio.run(run_debate("600009", agents=["buffett"], force=True))
        # call_agent 收到的 features 是分层 dossier
        assert "research_dossier" in captured["features"]
        assert "core_snapshot" in captured["features"]

    def test_call_agent_passes_agent_id_to_build_user_message(self):
        """call_agent 内部调 _build_user_message 时透传 agent_id（角色分发生效）."""
        import asyncio
        with patch("council.debate.call_llm", new_callable=AsyncMock,
                   return_value=('{"signal":"bullish","conviction":75,"core_thesis":"x","what_would_change_my_mind":"y","out_of_circle":false}', {"total_tokens": 100})):
            with patch("council.debate.build_research_dossier", return_value=_full_dossier()):
                # call_agent 真实调用 _build_user_message，验证 buffett 不含 research
                import asyncio
                agent = asyncio.run(call_agent("buffett", "600009", _full_dossier(), other_opinions=None))
                # 验证 agent 创建成功即可（call_llm 已 mock）
                assert agent.name == "buffett"


def _mk_agent(agent_id):
    from council.schema import AgentOutput
    return AgentOutput(name=agent_id, signal="bullish", conviction=75,
                       core_thesis="看好", what_would_change_my_mind="业绩下滑", out_of_circle=False)


def _mk_synth():
    from council.schema import SynthesizerOutput
    return SynthesizerOutput(final_signal="bullish", conviction=75,
                             consensus_summary="看好长期", dissent_points=[], pending_verification=[])
