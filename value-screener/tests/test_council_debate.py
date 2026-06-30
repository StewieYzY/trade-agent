"""L3 council debate 单元测试.

覆盖 debate.py 核心逻辑：
- _build_user_message 格式（R1 无 others / R2 有 others）
- _debate_path 路径生成
- _append_round markdown 格式
- _parse_debate_markdown 解析
- _check_cache 命中/未命中
- mock 注入路径（run_debate 带 mock_opinions）

LLM 调用全部 mock 掉，不花 token。
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from council.debate import (
    _append_round,
    _build_user_message,
    _check_cache,
    _debate_path,
    _parse_debate_markdown,
    run_debate,
)
from council.schema import AgentOutput, CouncilResult


# ── fixtures ───────────────────────────────────────────────────

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
def sample_agent() -> AgentOutput:
    return AgentOutput.from_dict("buffett", VALID_AGENT_DATA)


@pytest.fixture
def debate_dir(tmp_path, monkeypatch):
    """创建临时 debate 目录并 monkeypatch Path."""
    d = tmp_path / "debate"
    d.mkdir()
    monkeypatch.chdir(tmp_path)
    return d


# ── _build_user_message ────────────────────────────────────────

class TestBuildUserMessage:
    def test_r1_no_others(self):
        features = {"name": "贵州茅台", "pe_ttm": 18.0}
        msg = _build_user_message("600519", features, other_opinions=None)
        assert "600519" in msg
        assert "请独立判断" in msg
        assert "其他分析师" not in msg

    def test_r2_with_others(self, sample_agent):
        features = {"name": "贵州茅台", "pe_ttm": 18.0}
        msg = _build_user_message("600519", features, other_opinions=[sample_agent])
        assert "其他分析师" in msg
        assert "修订你的立场" in msg
        assert "巴菲特" in msg  # display name

    def test_features_compact(self):
        """features dump 不含 indent（P2-6 修复）."""
        features = {"name": "test", "pe_ttm": 18.0}
        msg = _build_user_message("600519", features)
        # compact JSON 不应有多余缩进
        assert "  " not in msg.split("## 特征数据")[1].split("请独立判断")[0]


# ── _debate_path ───────────────────────────────────────────────

class TestDebatePath:
    def test_with_suffix(self):
        path = _debate_path("600519.SH")
        assert "600519" in str(path)
        assert ".SH" not in str(path)
        assert path.suffix == ".md"

    def test_without_suffix(self):
        path = _debate_path("600519")
        assert "600519" in str(path)
        assert path.suffix == ".md"

    def test_date_in_path(self):
        from datetime import date
        path = _debate_path("600519")
        assert date.today().isoformat() in str(path)


# ── _append_round ──────────────────────────────────────────────

class TestAppendRound:
    def test_with_agents(self, tmp_path, sample_agent):
        path = tmp_path / "test.md"
        _append_round(path, 1, [sample_agent])
        content = path.read_text(encoding="utf-8")
        assert "## Round 1 · 各自表态" in content
        assert "### 巴菲特" in content
        assert "```json" in content
        assert '"signal": "bullish"' in content

    def test_skip_placeholder(self, tmp_path):
        path = tmp_path / "test.md"
        _append_round(path, 3, None)
        content = path.read_text(encoding="utf-8")
        assert "## Round 3 · Devil's Advocate" in content
        assert "（单 agent 模式，跳过）" in content

    def test_append_multiple(self, tmp_path, sample_agent):
        path = tmp_path / "test.md"
        _append_round(path, 1, [sample_agent])
        _append_round(path, 2, None)
        content = path.read_text(encoding="utf-8")
        assert "## Round 1" in content
        assert "## Round 2" in content


# ── _parse_debate_markdown ─────────────────────────────────────

class TestParseDebateMarkdown:
    def test_single_agent_r1(self):
        md = """
## Round 1 · 各自表态

### 巴菲特
```json
{
  "name": "buffett",
  "signal": "bullish",
  "conviction": 85,
  "core_thesis": "品牌护城河",
  "key_metrics": [],
  "risks": [],
  "what_would_change_my_mind": "收入下降",
  "out_of_circle": false,
  "historical_parallel": null
}
```

## Round 2 · 交叉质疑
（单 agent 模式，跳过）

## Round 3 · Devil's Advocate
（单 agent 模式，跳过）

## Round 4 · 收敛共识
（单 agent 模式，跳过）
"""
        result = _parse_debate_markdown(md, "600519")
        assert result is not None
        assert result.ticker == "600519"
        assert result.final_verdict == "bullish"
        assert len(result.rounds[0]) == 1
        assert result.rounds[0][0].signal == "bullish"
        assert result.rounds[1] is None
        assert result.rounds[2] is None
        assert result.rounds[3] is None

    def test_no_round1_returns_none(self):
        md = "## Round 2 · 交叉质疑\n（跳过）\n"
        result = _parse_debate_markdown(md, "600519")
        assert result is None

    def test_corrupted_json_skipped(self):
        md = """
## Round 1 · 各自表态

### 巴菲特
```json
{invalid json}
```
"""
        result = _parse_debate_markdown(md, "600519")
        assert result is None

    def test_round2_with_data(self):
        agent_json = json.dumps({
            "name": "buffett",
            "signal": "bearish",
            "conviction": 70,
            "core_thesis": "重新考虑后看空",
            "key_metrics": [],
            "risks": ["新发现的风险"],
            "what_would_change_my_mind": "收入恢复增长",
            "out_of_circle": False,
            "historical_parallel": None,
        }, ensure_ascii=False, indent=2)

        md = f"""
## Round 1 · 各自表态

### 巴菲特
```json
{agent_json}
```

## Round 2 · 交叉质疑

### 巴菲特
```json
{agent_json}
```
"""
        result = _parse_debate_markdown(md, "600519")
        assert result is not None
        assert result.rounds[0] is not None
        assert result.rounds[1] is not None


# ── _check_cache ───────────────────────────────────────────────

class TestCheckCache:
    def test_no_file(self, debate_dir):
        result = _check_cache("600519.SH")
        assert result is None

    def test_file_without_round1(self, debate_dir):
        path = debate_dir / "600519" / "2026-06-30.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 空记录\n", encoding="utf-8")
        result = _check_cache("600519.SH")
        assert result is None

    def test_valid_cache_hit(self, debate_dir):
        agent_json = json.dumps({
            "name": "buffett",
            "signal": "bullish",
            "conviction": 85,
            "core_thesis": "品牌护城河",
            "key_metrics": [],
            "risks": [],
            "what_would_change_my_mind": "收入下降",
            "out_of_circle": False,
            "historical_parallel": None,
        }, ensure_ascii=False, indent=2)

        md = f"""
## Round 1 · 各自表态

### 巴菲特
```json
{agent_json}
```

## Round 2 · 交叉质疑
（单 agent 模式，跳过）
"""
        from datetime import date
        path = debate_dir / "600519" / f"{date.today().isoformat()}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")

        result = _check_cache("600519.SH")
        assert result is not None
        assert result.final_verdict == "bullish"


# ── run_debate (with mocked LLM) ──────────────────────────────

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


class TestRunDebate:
    @pytest.mark.anyio
    async def test_single_agent_r1_only(self, debate_dir):
        """单 agent: R1 调 LLM, R2-4 跳过."""
        with patch("council.debate.call_llm", new_callable=AsyncMock, return_value=LLM_RESPONSE):
            result = await run_debate("600519", features={"name": "test"})
        assert result.final_verdict == "bullish"
        assert len(result.rounds[0]) == 1
        assert result.rounds[1] is None
        assert result.rounds[2] is None
        assert result.rounds[3] is None

    @pytest.mark.anyio
    async def test_mock_injection_triggers_r2(self, debate_dir):
        """mock_opinions 注入使单 agent R2 被触发."""
        mock_agent = AgentOutput.from_dict("munger", {
            "signal": "bearish",
            "conviction": 60,
            "core_thesis": "管理层有问题",
            "key_metrics": [],
            "risks": ["管理层减持"],
            "what_would_change_my_mind": "管理层回购",
            "out_of_circle": False,
            "historical_parallel": None,
        })

        call_count = 0

        async def mock_call_llm(system_prompt, user_message, reasoning_level="heavy"):
            nonlocal call_count
            call_count += 1
            # R2 的 user message 应包含 others
            if call_count == 2:
                assert "其他分析师" in user_message
                assert "munger" in user_message  # mock agent 未注册，fallback 为 agent_id
            return LLM_RESPONSE

        with patch("council.debate.call_llm", side_effect=mock_call_llm):
            result = await run_debate(
                "600519",
                features={"name": "test"},
                mock_opinions={"buffett": mock_agent},
            )

        assert call_count == 2  # R1 + R2
        assert result.rounds[1] is not None  # R2 被触发
        # T2: 验证 R2 输出被正确收集到 rounds[1]
        assert len(result.rounds[1]) == 1
        assert result.rounds[1][0].name == "buffett"
        assert result.rounds[1][0].signal == "bullish"
        assert result.rounds[1][0].conviction == 80

    @pytest.mark.anyio
    async def test_cache_hit_skips_llm(self, debate_dir):
        """缓存命中时不调 LLM."""
        # 先写入缓存
        from datetime import date
        agent_json = json.dumps({
            "name": "buffett",
            "signal": "bullish",
            "conviction": 90,
            "core_thesis": "缓存命中",
            "key_metrics": [],
            "risks": [],
            "what_would_change_my_mind": "不会变",
            "out_of_circle": False,
            "historical_parallel": None,
        }, ensure_ascii=False, indent=2)

        md = f"""
## Round 1 · 各自表态

### 巴菲特
```json
{agent_json}
```

## Round 2 · 交叉质疑
（单 agent 模式，跳过）
"""
        path = debate_dir / "600519" / f"{date.today().isoformat()}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(md, encoding="utf-8")

        with patch("council.debate.call_llm", new_callable=AsyncMock) as mock_llm:
            result = await run_debate("600519", features={"name": "test"})

        mock_llm.assert_not_called()
        assert result.final_verdict == "bullish"
        assert result.rounds[0][0].conviction == 90  # 来自缓存

    @pytest.mark.anyio
    async def test_force_skips_cache(self, debate_dir):
        """force=True 时跳过缓存，且验证文件层覆盖（P0-2 核心）."""
        # 先写入旧缓存（conviction=90）
        from datetime import date
        old_agent_json = json.dumps({
            "name": "buffett",
            "signal": "bullish",
            "conviction": 90,
            "core_thesis": "缓存命中",
            "key_metrics": [],
            "risks": [],
            "what_would_change_my_mind": "不会变",
            "out_of_circle": False,
            "historical_parallel": None,
        }, ensure_ascii=False, indent=2)

        old_md = f"""
## Round 1 · 各自表态

### 巴菲特
```json
{old_agent_json}
```

## Round 2 · 交叉质疑
（单 agent 模式，跳过）
"""
        path = debate_dir / "600519" / f"{date.today().isoformat()}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(old_md, encoding="utf-8")

        with patch("council.debate.call_llm", new_callable=AsyncMock, return_value=LLM_RESPONSE):
            result = await run_debate("600519", features={"name": "test"}, force=True)

        # 返回值验证：force=True 应该重跑 LLM，conviction 应该是 80 而非 90
        assert result.rounds[0][0].conviction == 80

        # 文件层验证（P0-2 核心）：旧记录应被清除，不应混叠
        new_md = path.read_text(encoding="utf-8")
        assert "缓存命中" not in new_md, "旧记录残留：force=True 未清除旧文件"
        assert new_md.count("## Round 1") == 1, "Round 1 重复：文件追加而非覆盖"
        assert "好公司" in new_md, "新记录未写入"
