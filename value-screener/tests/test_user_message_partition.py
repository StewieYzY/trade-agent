"""f3a §4: prompt 物理分区测试（design Risks，研报不当事实）.

user message 物理分区：公司事实段 + 市场共识/外部预期段。
research 单独成段不混进公司事实段，研报引用标注「市场预期认为……」。
system prompt（build_*_prompt）不动。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.debate import _build_user_message


def _full_dossier() -> dict:
    return {
        "core_snapshot": {"ticker": "600009", "pe_ttm": 26.42},
        "research_dossier": {
            "main_business": {"code": "600009", "by_industry": [{"name": "航空", "revenue_ratio": 0.94}]},
            "peers": {"peer_avg_pe": 18.1, "industry_pe_rank": 2},
            "capex_proxy": {"latest": 1.307e9},
            "research": {"consensus_eps": 1.152, "target_price": 30.41, "buy_rating_pct": 1.0, "coverage_count": 2},
            "degraded_fields": [],
        },
        "pledge": 8.5,
    }


class TestUserMessagePartition:
    def test_duan_message_has_two_physical_sections(self):
        """段永平（含 research）user message 分「公司事实特征」段 + 「市场共识/外部预期」段."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="duan")
        assert "公司事实特征" in msg
        assert "市场共识" in msg or "外部预期" in msg

    def test_feng_liu_message_has_two_physical_sections(self):
        """冯柳（含 research）也分两段."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="feng_liu")
        assert "公司事实特征" in msg
        assert "市场共识" in msg or "外部预期" in msg

    def test_research_not_in_fact_section(self):
        """research 单独成段，不混进公司事实段."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="duan")
        # 找到「市场共识」段的位置
        consensus_idx = msg.find("市场共识") if "市场共识" in msg else msg.find("外部预期")
        fact_idx = msg.find("公司事实特征")
        assert consensus_idx > fact_idx  # 市场共识段在公司事实段之后
        # research 数据（consensus_eps）只在市场共识段之后出现
        eps_idx = msg.find("consensus_eps")
        assert eps_idx > consensus_idx

    def test_research_citation_marks_market_expectation(self):
        """研报引用标注「市场预期认为……」/「非公司事实」."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="duan")
        assert "市场预期" in msg
        assert "非公司事实" in msg or "不得作为客观事实" in msg

    def test_buffett_no_research_section(self):
        """buffett 不含 research，不应有市场共识段（无 research 可引）."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="buffett")
        assert "consensus_eps" not in msg
        # buffett 无 research 维度，不应出现市场共识段
        assert "市场共识" not in msg

    def test_system_prompt_not_changed(self):
        """system prompt 函数保持无参签名不变（build_*_prompt 不动）."""
        from council.prompt import (build_buffett_prompt, build_munger_prompt,
                                    build_duan_prompt, build_feng_liu_prompt)
        import inspect
        for fn in (build_buffett_prompt, build_munger_prompt, build_duan_prompt, build_feng_liu_prompt):
            sig = inspect.signature(fn)
            assert len(sig.parameters) == 0, f"{fn.__name__} 应保持无参签名"

    def test_capex_in_fact_section_not_consensus(self):
        """capex_proxy 属公司事实段，不属市场共识段."""
        msg = _build_user_message("600009", _full_dossier(), other_opinions=None, agent_id="buffett")
        # capex 在公司事实段内
        capex_idx = msg.find("capex")
        if capex_idx < 0:
            capex_idx = msg.find("1.307")  # capex 数据值
        assert capex_idx > 0
        # capex 应在「市场共识」标记之前（若无市场共识段则更简单）
        consensus_idx = msg.find("市场共识")
        if consensus_idx > 0:
            assert capex_idx < consensus_idx
