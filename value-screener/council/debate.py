"""L3 天团辩论编排器（design.md 决策 3: debate.py 是唯一状态持有者）.

4 轮串行辩论：
- Round 1: 各自表态（并行，彼此隔离，重度推理）
- Round 2: 交叉质疑（并行，可见他人 R1，重度推理；单 agent 跳过 LLM）
- Round 3: Devil's Advocate（单 agent 跳过；全天团可见 R1+R2）
- Round 4: 收敛共识（单 agent 跳过；全天团可见 R1+R2+R3，中度推理）

信息可见性由编排器控制，agent 之间不直接通信。
辩论记录 append-only 持久化，每轮结束立即写入。
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from council.agents import AGENT_REGISTRY, get_prompt_builder, get_agent_display_name
from council.features import assemble_council_features
from council.llm import call_llm
from council.schema import AgentOutput, CouncilResult, ValidationError


async def call_agent(
    agent_id: str,
    ticker: str,
    features: dict,
    other_opinions: list[AgentOutput] | None = None,
    reasoning_level: str = "heavy",
) -> AgentOutput:
    """调用单个 agent，返回 AgentOutput.

    Args:
        agent_id: agent 标识（如 "buffett"）
        ticker: 股票代码
        features: 特征数据 dict
        other_opinions: 其他 agent 的 R1 输出（R2 用，R1 为空列表）
        reasoning_level: 推理等级（"heavy" / "moderate"）

    Returns:
        AgentOutput 实例

    Raises:
        ValidationError: LLM 输出 JSON 校验失败
        httpx.HTTPStatusError / httpx.TimeoutException: LLM 调用失败
    """
    # 构建 system prompt
    builder = get_prompt_builder(agent_id)
    system_prompt = builder()

    # 构建 user message
    user_message = _build_user_message(ticker, features, other_opinions)

    # 调用 LLM
    raw_json = await call_llm(system_prompt, user_message, reasoning_level)

    # 解析并校验
    return AgentOutput.from_json(agent_id, raw_json)


def _build_user_message(
    ticker: str,
    features: dict,
    other_opinions: list[AgentOutput] | None = None,
) -> str:
    """构建 user message（特征数据 + 他人观点）.

    Args:
        ticker: 股票代码
        features: 特征数据 dict
        other_opinions: 其他 agent 的输出（R2 用）

    Returns:
        user message 字符串
    """
    parts = [
        f"请分析以下股票：{ticker}",
        "",
        "## 特征数据",
        json.dumps(features, ensure_ascii=False, indent=2),
    ]

    if other_opinions:
        parts.extend([
            "",
            "## 其他分析师的初步判断",
            "以下是其他分析师的独立判断，请阅读并思考：",
        ])
        for opinion in other_opinions:
            name = get_agent_display_name(opinion.name)
            parts.append(f"\n### {name}")
            parts.append(json.dumps(opinion.to_dict(), ensure_ascii=False, indent=2))

        parts.extend([
            "",
            "请基于以上信息修订你的立场（可以坚持原判，也可以调整）。",
        ])
    else:
        parts.extend([
            "",
            "请独立判断，不需要参考他人观点。",
        ])

    return "\n".join(parts)


def _debate_path(ticker: str) -> Path:
    """返回辩论记录文件路径：debate/{ticker}/{YYYY-MM-DD}.md"""
    today = date.today().isoformat()
    # ticker 可能含后缀（如 600519.SH），取纯数字部分
    ticker_clean = ticker.split(".")[0]
    return Path(f"debate/{ticker_clean}/{today}.md")


def _append_round(path: Path, round_num: int, agents: list[AgentOutput] | None) -> None:
    """追加单轮辩论记录到 markdown 文件.

    Args:
        path: 辩论记录文件路径
        round_num: 轮次（1-4）
        agents: 该轮 agent 输出列表（None 表示跳过）
    """
    round_titles = {
        1: "各自表态",
        2: "交叉质疑",
        3: "Devil's Advocate",
        4: "收敛共识",
    }

    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n## Round {round_num} · {round_titles[round_num]}\n")

        if agents is None:
            f.write("（单 agent 模式，跳过）\n")
        else:
            for agent_out in agents:
                name = get_agent_display_name(agent_out.name)
                f.write(f"\n### {name}\n")
                f.write("```json\n")
                f.write(agent_out.to_json())
                f.write("\n```\n")


def _check_cache(ticker: str) -> CouncilResult | None:
    """检查辩论记录缓存，命中则返回 CouncilResult.

    命中条件：debate/{ticker}/{date}.md 存在且至少含 Round 1 节。

    Args:
        ticker: 股票代码

    Returns:
        CouncilResult 或 None（未命中）
    """
    path = _debate_path(ticker)
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    if "## Round 1" not in content:
        return None

    # TODO: 解析 markdown 还原 CouncilResult
    # 当前简化处理：命中缓存时直接重跑（完整解析后续优化）
    return None


async def run_debate(
    ticker: str,
    features: dict | None = None,
    agents: list[str] | None = None,
    force: bool = False,
    mock_opinions: dict[str, AgentOutput] | None = None,
) -> CouncilResult:
    """4 轮天团辩论，返回 CouncilResult.

    Args:
        ticker: 股票代码
        features: 特征数据（缺省调 assemble_council_features）
        agents: agent 列表（缺省从 AGENT_REGISTRY 读）
        force: 跳过缓存强制重跑
        mock_opinions: R2 mock 注入（机制门验证用），key=agent_id

    Returns:
        CouncilResult 实例

    Raises:
        ValidationError: agent 输出 JSON 校验失败
        ValueError: 数据不足（insufficient_data）
    """
    # 1. 获取特征数据
    if features is None:
        features = assemble_council_features(ticker)
        if "error" in features:
            raise ValueError(f"insufficient_data: {features.get('missing_fields', [])}")

    # 2. 确定 agent 列表
    if agents is None:
        agents = list(AGENT_REGISTRY.keys())

    # 3. 检查缓存（除非 force=True）
    if not force:
        cached = _check_cache(ticker)
        if cached is not None:
            return cached

    # 4. 准备辩论记录文件
    path = _debate_path(ticker)
    if path.exists() and not force:
        # 追加模式：清空旧内容（force=True 时覆盖）
        path.unlink()

    # 5. Round 1: 各自表态（并行，彼此隔离）
    r1_tasks = [
        call_agent(agent_id, ticker, features, other_opinions=None, reasoning_level="heavy")
        for agent_id in agents
    ]
    round1 = await asyncio.gather(*r1_tasks)
    _append_round(path, 1, round1)

    # 6. Round 2: 交叉质疑
    # 单 agent 下跳过 LLM 调用（不调 LLM 浪费 token）
    if len(agents) == 1 and not mock_opinions:
        # 单 agent 且无 mock 注入：跳过
        round2 = None
        _append_round(path, 2, None)
    else:
        # 全天团或有 mock 注入：跑 R2
        r2_tasks = []
        for agent_id in agents:
            # 构建 other_opinions：排除自己，可注入 mock
            others = [a for a in round1 if a.name != agent_id]
            if mock_opinions and agent_id in mock_opinions:
                # 注入 mock 观点（机制门验证）
                others.append(mock_opinions[agent_id])

            r2_tasks.append(
                call_agent(agent_id, ticker, features, other_opinions=others, reasoning_level="heavy")
            )
        round2 = await asyncio.gather(*r2_tasks)
        _append_round(path, 2, round2)

    # 7. Round 3: Devil's Advocate（单 agent 跳过）
    if len(agents) == 1:
        da_result = None
        _append_round(path, 3, None)
    else:
        # TODO: 3b 实现 DA agent
        # 当前占位：跳过
        da_result = None
        _append_round(path, 3, None)

    # 8. Round 4: 收敛共识（单 agent 跳过）
    if len(agents) == 1:
        consensus = None
        _append_round(path, 4, None)
    else:
        # TODO: 3b 实现 synthesizer agent
        # 当前占位：跳过
        consensus = None
        _append_round(path, 4, None)

    # 9. 组装 CouncilResult
    rounds = [round1, round2, da_result, consensus]
    final_verdict = round1[0].signal if round1 else "skip"
    key_variables = CouncilResult.extract_key_variables(rounds)

    return CouncilResult(
        ticker=ticker,
        rounds=rounds,
        final_verdict=final_verdict,
        key_variables=key_variables,
    )
