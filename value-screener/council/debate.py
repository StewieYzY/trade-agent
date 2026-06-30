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
import re
from datetime import date
from pathlib import Path
from typing import Any

from council.agents import AGENT_REGISTRY, get_prompt_builder, get_agent_display_name
from council.features import assemble_council_features
from council.llm import call_llm
from council.schema import AgentOutput, CouncilResult, SynthesizerOutput, ValidationError


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
        json.dumps(features, ensure_ascii=False),
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


def _append_agent_round(path: Path, round_num: int, agents: list[AgentOutput]) -> None:
    """追加 R1/R2 轮次（多 agent 列表）."""
    _append_round(path, round_num, agents)


def _append_da_round(path: Path, da: AgentOutput) -> None:
    """追加 R3 DA 输出（单对象）."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write("\n## Round 3 · Devil's Advocate\n")
        f.write("```json\n")
        f.write(da.to_json())
        f.write("\n```\n")


def _append_synthesizer_round(path: Path, syn: SynthesizerOutput) -> None:
    """追加 R4 Synthesizer 输出（单对象，不同类型）."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write("\n## Round 4 · 收敛共识\n")
        f.write("```json\n")
        f.write(syn.to_json())
        f.write("\n```\n")


async def _call_da(
    round1: list[AgentOutput],
    round2: list[AgentOutput] | None,
    ticker: str,
    features: dict,
) -> AgentOutput:
    """调用 DA（Devil's Advocate）.

    传入 R1+R2 的输出，返回 DA 的 AgentOutput（含 extra.blind_spots）。
    """
    from council.prompt import build_da_prompt

    system_prompt = build_da_prompt()

    # 构建 user message：传入 R1+R2 的完整输出
    parts = [
        f"请分析以下股票的辩论记录：{ticker}",
        "",
        "## 特征数据",
        json.dumps(features, ensure_ascii=False),
        "",
        "## Round 1 · 各自表态",
    ]
    for agent in round1:
        parts.append(f"\n### {get_agent_display_name(agent.name)}")
        parts.append(json.dumps(agent.to_dict(), ensure_ascii=False, indent=2))

    if round2:
        parts.append("\n## Round 2 · 交叉质疑")
        for agent in round2:
            parts.append(f"\n### {get_agent_display_name(agent.name)}")
            parts.append(json.dumps(agent.to_dict(), ensure_ascii=False, indent=2))

    user_message = "\n".join(parts)

    raw_json = await call_llm(system_prompt, user_message, "heavy")
    return AgentOutput.from_json("da", raw_json)


async def _call_synthesizer(
    round1: list[AgentOutput],
    round2: list[AgentOutput] | None,
    da_result: AgentOutput | None,
    ticker: str,
    features: dict,
) -> SynthesizerOutput:
    """调用 Synthesizer（共识收敛器）.

    传入 R1+R2+R3 的输出，返回 SynthesizerOutput。
    """
    from council.prompt import build_synthesizer_prompt

    system_prompt = build_synthesizer_prompt()

    # 构建 user message：传入 R1+R2+R3 的完整输出
    parts = [
        f"请综合以下股票的辩论结果：{ticker}",
        "",
        "## 特征数据",
        json.dumps(features, ensure_ascii=False),
        "",
        "## Round 1 · 各自表态",
    ]
    for agent in round1:
        parts.append(f"\n### {get_agent_display_name(agent.name)}")
        parts.append(json.dumps(agent.to_dict(), ensure_ascii=False, indent=2))

    if round2:
        parts.append("\n## Round 2 · 交叉质疑")
        for agent in round2:
            parts.append(f"\n### {get_agent_display_name(agent.name)}")
            parts.append(json.dumps(agent.to_dict(), ensure_ascii=False, indent=2))

    if da_result:
        parts.append("\n## Round 3 · Devil's Advocate")
        parts.append("```json")
        parts.append(json.dumps(da_result.to_dict(), ensure_ascii=False, indent=2))
        parts.append("```")

    user_message = "\n".join(parts)

    raw_json = await call_llm(system_prompt, user_message, "moderate")
    return SynthesizerOutput.from_json(raw_json)


def _parse_debate_markdown(content: str, ticker: str) -> CouncilResult | None:
    """解析辩论记录 markdown，还原 CouncilResult.

    从 markdown 中提取 ```json ... ``` 块，按轮次分组，
    反序列化为 AgentOutput 列表。R4 使用 SynthesizerOutput。

    Args:
        content: markdown 文件内容
        ticker: 股票代码

    Returns:
        CouncilResult 或 None（解析失败时降级为重跑）
    """
    # 按轮次 header 分割
    round_pattern = re.compile(r"^## Round (\d+)", re.MULTILINE)
    sections = round_pattern.split(content)
    # sections[0] = 文件头（空或标题），sections[1] = "1", sections[2] = R1内容, ...

    rounds: list[list[AgentOutput] | None] = [None, None, None, None]
    round4_synthesizer: SynthesizerOutput | None = None

    for i in range(1, len(sections), 2):
        if i + 1 >= len(sections):
            break
        round_num = int(sections[i])
        section_content = sections[i + 1]

        if round_num < 1 or round_num > 4:
            continue

        # 跳过标记
        if "（单 agent 模式，跳过）" in section_content:
            rounds[round_num - 1] = None
            continue

        # 提取 ```json ... ``` 块
        json_pattern = re.compile(r"```json\n(.*?)\n```", re.DOTALL)
        json_blocks = json_pattern.findall(section_content)

        if not json_blocks:
            # 无 JSON 块但有内容 → 可能是损坏的记录
            rounds[round_num - 1] = None
            continue

        # R4 使用 SynthesizerOutput
        if round_num == 4:
            try:
                data = json.loads(json_blocks[0])
                round4_synthesizer = SynthesizerOutput.from_dict(data)
            except (json.JSONDecodeError, ValidationError):
                round4_synthesizer = None
            continue

        # R1/R2/R3 使用 AgentOutput
        agents_in_round = []
        for block in json_blocks:
            try:
                data = json.loads(block)
                agent_id = data.get("name", "unknown")
                agents_in_round.append(AgentOutput.from_dict(agent_id, data))
            except (json.JSONDecodeError, ValidationError):
                # 单个块解析失败不影响其他块
                continue

        rounds[round_num - 1] = agents_in_round if agents_in_round else None

    # 至少 R1 有数据才算命中
    if not rounds[0]:
        return None

    round1 = list(rounds[0])
    round2 = list(rounds[1]) if rounds[1] else None
    round3 = rounds[2][0] if rounds[2] else None  # DA 是单个 AgentOutput

    key_variables = CouncilResult.extract_key_variables(round1, round2)

    # final_verdict 逻辑
    final_verdict = round4_synthesizer.final_signal if round4_synthesizer else round1[0].signal

    return CouncilResult(
        ticker=ticker,
        round1=round1,
        round2=round2,
        round3=round3,
        round4=round4_synthesizer,
        final_verdict=final_verdict,
        key_variables=key_variables,
        consensus_summary=round4_synthesizer.consensus_summary if round4_synthesizer else None,
        dissent_points=round4_synthesizer.dissent_points if round4_synthesizer else None,
        pending_verification=round4_synthesizer.pending_verification if round4_synthesizer else None,
    )


def _check_cache(ticker: str) -> CouncilResult | None:
    """检查辩论记录缓存，命中则返回 CouncilResult.

    命中条件：debate/{ticker}/{date}.md 存在且至少含 Round 1 节，
    且 Round 1 中至少有一个可解析的 AgentOutput JSON。

    解析失败（格式损坏）→ 返回 None（降级为重跑）。

    Args:
        ticker: 股票代码

    Returns:
        CouncilResult 或 None（未命中/解析失败）
    """
    path = _debate_path(ticker)
    if not path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    if "## Round 1" not in content:
        return None

    return _parse_debate_markdown(content, ticker)


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
    # force=True 时删除旧文件再覆盖写入；force=False 时由 _check_cache 提前返回
    path = _debate_path(ticker)
    if force and path.exists():
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
        da_result = await _call_da(round1, round2, ticker, features)
        _append_da_round(path, da_result)

    # 8. Round 4: 收敛共识（单 agent 跳过）
    if len(agents) == 1:
        consensus = None
        _append_round(path, 4, None)
    else:
        consensus = await _call_synthesizer(round1, round2, da_result, ticker, features)
        _append_synthesizer_round(path, consensus)

    # 9. 组装 CouncilResult
    key_variables = CouncilResult.extract_key_variables(round1, round2)

    # 全天团：final_verdict 取 round4.final_signal
    # 单 agent：final_verdict 取 round1[0].signal
    final_verdict = consensus.final_signal if consensus else round1[0].signal

    result = CouncilResult(
        ticker=ticker,
        round1=list(round1),
        round2=list(round2) if round2 else None,
        round3=da_result,
        round4=consensus,
        final_verdict=final_verdict,
        key_variables=key_variables,
        consensus_summary=consensus.consensus_summary if consensus else None,
        dissent_points=consensus.dissent_points if consensus else None,
        pending_verification=consensus.pending_verification if consensus else None,
    )

    # 10. 写入 L3→L4 接口文件
    _write_council_output(result, path)

    return result


def _write_council_output(result: CouncilResult, debate_path: Path) -> None:
    """写入 L3→L4 接口文件（watchlist/{date}_{ticker}.json）.

    Args:
        result: CouncilResult 实例
        debate_path: 辩论记录路径（用于提取日期）
    """
    watchlist_dir = Path("watchlist")
    watchlist_dir.mkdir(exist_ok=True)

    # 从 debate_path 提取日期（debate/{ticker}/{date}.md）
    date_str = debate_path.stem
    ticker_clean = debate_path.parent.name

    output = {
        "ticker": result.ticker,
        "date": date_str,
        "final_verdict": result.final_verdict,
        "conviction": result.round4.conviction if result.round4 else None,
        "consensus_summary": result.consensus_summary,
        "key_variables": result.key_variables,
        "dissent_points": result.dissent_points,
        "pending_verification": result.pending_verification,
        "debate_path": str(debate_path),
    }

    output_path = watchlist_dir / f"{date_str}_{ticker_clean}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
