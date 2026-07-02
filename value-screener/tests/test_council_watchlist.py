"""L3→L4 接口（watchlist 产出）单元测试.

覆盖:
- _write_council_output 字段完整性
- 与 L1/L2 watchlist 独立（不覆盖 {date}_screener.json）
- 单 agent fallback 时 None 字段处理
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from council.debate import _write_council_output, run_debate
from council.schema import AgentOutput, CouncilResult, SynthesizerOutput


VALID_AGENT_DATA = {
    "signal": "bullish",
    "conviction": 85,
    "core_thesis": "品牌护城河深厚",
    "key_metrics": ["ROE 32%"],
    "risks": ["宏观风险"],
    "what_would_change_my_mind": "连续两季负增长",
    "out_of_circle": False,
    "historical_parallel": "可口可乐",
}


@pytest.fixture
def watchlist_dir(tmp_path, monkeypatch):
    """创建临时工作目录."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestWriteCouncilOutput:
    def test_full_council_fields(self, watchlist_dir):
        """全天团接口文件字段完整."""
        agent = AgentOutput.from_dict("buffett", VALID_AGENT_DATA)
        syn = SynthesizerOutput(
            final_signal="bullish",
            conviction=75,
            consensus_summary="品牌护城河深厚",
            dissent_points=[{"topic": "估值", "who_disagrees": "munger", "their_reason": "PE过高"}],
            pending_verification=["现金流验证"],
        )
        result = CouncilResult(
            ticker="600519.SH",
            round1=[agent],
            round2=[agent],
            round3=agent,
            round4=syn,
            final_verdict="bullish",
            key_variables=["ROE > 20%"],
            consensus_summary="品牌护城河深厚",
            dissent_points=[{"topic": "估值"}],
            pending_verification=["现金流验证"],
        )

        debate_path = Path("debate/600519/2026-06-30.md")
        _write_council_output(result, debate_path)

        output_path = watchlist_dir / "watchlist" / "2026-06-30_600519.SH.json"
        assert output_path.exists()

        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["ticker"] == "600519.SH"
        assert data["date"] == "2026-06-30"
        assert data["final_verdict"] == "bullish"
        assert data["conviction"] == 75
        assert data["consensus_summary"] == "品牌护城河深厚"
        assert data["key_variables"] == ["ROE > 20%"]
        assert len(data["dissent_points"]) == 1
        assert data["pending_verification"] == ["现金流验证"]
        assert "debate/600519/2026-06-30.md" in data["debate_path"]

    def test_single_agent_fallback_none_fields(self, watchlist_dir):
        """单 agent fallback: consensus_summary/dissent_points/pending_verification 为 None."""
        agent = AgentOutput.from_dict("buffett", VALID_AGENT_DATA)
        result = CouncilResult(
            ticker="600519.SH",
            round1=[agent],
            final_verdict="bullish",
            key_variables=["连续两季负增长"],
        )

        debate_path = Path("debate/600519/2026-06-30.md")
        _write_council_output(result, debate_path)

        output_path = watchlist_dir / "watchlist" / "2026-06-30_600519.SH.json"
        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["final_verdict"] == "bullish"
        assert data["conviction"] is None  # 无 round4
        assert data["consensus_summary"] is None
        assert data["dissent_points"] is None
        assert data["pending_verification"] is None

    def test_watchlist_dir_auto_created(self, watchlist_dir):
        """watchlist/ 目录不存在时自动创建."""
        agent = AgentOutput.from_dict("buffett", VALID_AGENT_DATA)
        result = CouncilResult(
            ticker="600519.SH",
            round1=[agent],
            final_verdict="bullish",
        )
        debate_path = Path("debate/600519/2026-06-30.md")
        _write_council_output(result, debate_path)
        assert (watchlist_dir / "watchlist").exists()

    def test_independent_from_screener_watchlist(self, watchlist_dir):
        """接口文件与 L1/L2 watchlist 独立."""
        # 先创建 screener watchlist
        screener_dir = watchlist_dir / "watchlist"
        screener_dir.mkdir()
        screener_file = screener_dir / "2026-06-30_screener.json"
        screener_file.write_text('{"tickers": ["600519"]}', encoding="utf-8")

        # 写 council watchlist
        agent = AgentOutput.from_dict("buffett", VALID_AGENT_DATA)
        result = CouncilResult(
            ticker="600519.SH",
            round1=[agent],
            final_verdict="bullish",
        )
        debate_path = Path("debate/600519/2026-06-30.md")
        _write_council_output(result, debate_path)

        # screener 文件不受影响
        assert screener_file.exists()
        assert json.loads(screener_file.read_text())["tickers"] == ["600519"]
        # council 文件独立存在
        council_file = watchlist_dir / "watchlist" / "2026-06-30_600519.SH.json"
        assert council_file.exists()


LLM_RESPONSE = json.dumps({
    "signal": "bullish",
    "conviction": 80,
    "core_thesis": "好公司",
    "key_metrics": ["ROE 30%"],
    "risks": ["估值偏高"],
    "what_would_change_my_mind": "业绩下滑",
    "out_of_circle": False,
    "historical_parallel": None,
}, ensure_ascii=False)

# f1-deviation-fix §7：call_llm 返回 (content, usage)，mock 带 usage
LLM_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


class TestRunDebateWritesWatchlist:
    @pytest.mark.anyio
    async def test_run_debate_writes_council_json(self, watchlist_dir):
        """run_debate 末尾自动写入 watchlist."""
        with patch("council.debate.call_llm", new_callable=AsyncMock, return_value=(LLM_RESPONSE, LLM_USAGE)):
            result = await run_debate("600519", agents=["buffett"], features={"name": "test"})

        today = date.today().isoformat()
        output_path = watchlist_dir / "watchlist" / f"{today}_600519.json"
        assert output_path.exists()

        data = json.loads(output_path.read_text(encoding="utf-8"))
        assert data["ticker"] == "600519"
        assert data["final_verdict"] == "bullish"
