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
from council.research_dossier import build_research_dossier
from council.schema import AgentOutput, CouncilResult, SynthesizerOutput, ValidationError


async def call_agent(
    agent_id: str,
    ticker: str,
    features: dict,
    other_opinions: list[AgentOutput] | None = None,
    reasoning_level: str = "heavy",
    usage_accumulator: list[dict] | None = None,
) -> AgentOutput:
    """调用单个 agent，返回 AgentOutput.

    Args:
        agent_id: agent 标识（如 "buffett"）
        ticker: 股票代码
        features: 特征数据 dict
        other_opinions: 其他 agent 的 R1 输出（R2 用，R1 为空列表）
        reasoning_level: 推理等级（"heavy" / "moderate"）
        usage_accumulator: 可选，传入则每次调用的 token usage 追加到此列表
            （f1-deviation-fix §7：供 run_debate 累加 AD-03 成本，不改 CouncilResult schema）

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
    # f3a §3 D3：透传 agent_id 给 _build_user_message 做角色分发
    user_message = _build_user_message(ticker, features, other_opinions, agent_id=agent_id)

    # 调用 LLM（f1-deviation-fix §7：返回 (content, usage)，usage 供 AD-03 成本累加）
    raw_json, usage = await call_llm(system_prompt, user_message, reasoning_level)
    if usage_accumulator is not None and usage:
        usage_accumulator.append({"agent": agent_id, "round": reasoning_level, **usage})

    # 解析并校验
    return AgentOutput.from_json(agent_id, raw_json)


def _build_user_message(
    ticker: str,
    features: dict,
    other_opinions: list[AgentOutput] | None = None,
    agent_id: str | None = None,
) -> str:
    """构建 user message（特征数据 + 他人观点）.

    f3a §3/§4（D3）：角色分发按 agent_id 从分层 dossier 取角色侧重子集，
    core_snapshot 全员共享，定性维度按 D1 角色表分发。
    - agent_id 为 buffett/munger/duan/feng_liu：按角色表分发定性维度
    - agent_id 为 da/synthesizer：走全量路径（仲裁要全知，不分发）
    - agent_id=None 或 features 是旧扁平结构：退化为全员共享（向后兼容）

    f3a §4：prompt 物理分区——公司事实段（core+main_business+peers+capex_proxy）
    + 市场共识段（research 单独成段），研报引用写明「市场预期认为……」不当事实。

    Args:
        ticker: 股票代码
        features: 特征数据 dict（f3a 起为分层 dossier，旧调用为扁平 21 字段）
        other_opinions: 其他 agent 的输出（R2 用）
        agent_id: 当前 agent 标识（角色分发用）

    Returns:
        user message 字符串
    """
    parts = [
        f"请分析以下股票：{ticker}",
        "",
    ]

    # 分层 dossier（f3a）→ 按角色分发；旧扁平 features → 全员共享退化
    if isinstance(features, dict) and "research_dossier" in features:
        parts.extend(_build_dossier_sections(features, agent_id))
    else:
        # 旧扁平 21 字段（向后兼容，agent_id=None 退化路径）
        parts.extend([
            "## 特征数据",
            json.dumps(features, ensure_ascii=False),
        ])

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
            "## R2 新证据引导",
            "如果 R1 未充分覆盖某些数据维度，请在 new_evidence 中列出。",
            "如果所有相关数据已在 R1 被引用，请声明 evidence_exhausted: true。",
            "",
            "请基于以上信息修订你的立场（可以坚持原判，也可以调整）。",
        ])
    else:
        parts.extend([
            "",
            "请独立判断，不需要参考他人观点。",
        ])

    return "\n".join(parts)


# f3a §3 D1：角色 → 定性维度侧重映射
# core_snapshot 全员共享，定性维度按角色分发
_AGENT_DIM_MAP: dict[str, tuple[str, ...]] = {
    "buffett": ("main_business", "peers", "capex_proxy"),
    "munger": ("main_business", "peers"),       # pledge 在顶层，单独注入
    "duan": ("main_business", "peers", "research"),
    "feng_liu": ("research", "capex_proxy"),
}
# DA / Synthesizer 走全量路径（仲裁要全知）
_FULL_ACCESS_AGENTS = {"da", "synthesizer"}


def _build_dossier_sections(dossier: dict, agent_id: str | None) -> list[str]:
    """从分层 dossier 按 agent_id 角色分发构造 user message 段.

    物理分区（§4）：
    - 「公司事实特征」段：core_snapshot + main_business + peers + capex_proxy
    - 「市场共识/外部预期」段：research（单独成段，研报引用写明「市场预期认为……」）
    芒格的 pledge 单独注明（治理代理）。
    """
    core = dossier.get("core_snapshot", {})
    rd = dossier.get("research_dossier", {}) or {}
    degraded_fields = rd.get("degraded_fields", []) or []
    pledge = dossier.get("pledge")

    # 决定可见维度
    if agent_id is None or agent_id in _FULL_ACCESS_AGENTS:
        # 全量路径（agent_id=None 退化 / DA / Synthesizer）
        visible_dims = ("main_business", "peers", "capex_proxy", "research")
        include_pledge = True
    else:
        visible_dims = _AGENT_DIM_MAP.get(agent_id, ())
        # 芒格含 pledge（治理代理），其他 agent 不含 pledge
        include_pledge = (agent_id == "munger")

    parts: list[str] = []

    # ── 公司事实特征段（core + 可见的定性事实维度）──────────────
    parts.append("## 公司事实特征")
    parts.append(json.dumps(core, ensure_ascii=False, indent=2))

    fact_dims = [d for d in ("main_business", "peers", "capex_proxy")
                 if d in visible_dims]
    for dim in fact_dims:
        dim_data = rd.get(dim)
        is_degraded = dim in degraded_fields or _is_error_data(dim_data)
        if is_degraded:
            parts.append(f"\n### {dim}（该维度缺失/降级）")
            parts.append(_degraded_note(dim))
            continue
        parts.append(f"\n### {dim}")
        parts.append(json.dumps(dim_data, ensure_ascii=False, indent=2))

    # pledge（芒格治理代理）单独注入公司事实段
    if include_pledge and pledge is not None:
        parts.append(f"\n### pledge（质押率，治理代理）")
        parts.append(json.dumps({"pledge_ratio": pledge}, ensure_ascii=False))

    # ── 市场共识/外部预期段（research，单独成段）───────────────
    if "research" in visible_dims:
        research_data = rd.get("research")
        parts.append("")
        parts.append("## 市场共识/外部预期（研报，非公司事实）")
        parts.append(
            "以下为卖方研报共识，是「市场预期」而非公司事实。引用时须写明"
            "「市场预期认为……」，不得作为客观事实陈述。"
        )
        is_research_degraded = "research" in degraded_fields or _is_error_data(research_data)
        if is_research_degraded:
            parts.append(_degraded_note("research"))
        else:
            parts.append(json.dumps(research_data, ensure_ascii=False, indent=2))

    return parts


def _is_error_data(data) -> bool:
    """数据是否为 fetch 全失败 __error__ 标记."""
    return isinstance(data, dict) and data.get("__error__") is True


def _degraded_note(dim: str) -> str:
    """降级维度的 prompt 注明（D5：诚实标注不静默退化）."""
    dim_cn = {
        "main_business": "主营构成",
        "peers": "竞品对比",
        "capex_proxy": "资本开支",
        "research": "研报共识",
    }.get(dim, dim)
    return f"你的{dim_cn}维度缺失，请基于核心特征（core_snapshot）判断，勿臆测该维度数据。"


def _debate_path(ticker: str) -> Path:
    """返回辩论记录文件路径（新写入用 canonical 带后缀）：debate/{canonical_ticker}/{YYYY-MM-DD}.md

    g1-canonical-run-identity D5 A+：新写入统一 canonical（600519.SH），与
    _write_council_output 的 watchlist 文件名口径一致，消除 600009.json（空壳）/
    600009.SH.json（真数据）分裂。既有 debate/{纯数字}/ 旧目录保留，_check_cache
    回退读取（见 _legacy_debate_path）。
    """
    from data.lib.identity import canonical_ticker
    today = date.today().isoformat()
    canonical = canonical_ticker(ticker)
    return Path(f"debate/{canonical}/{today}.md")


def _legacy_debate_path(ticker: str) -> Path:
    """返回旧纯数字辩论记录路径（debate/{canonical_code}/{YYYY-MM-DD}.md），供 _check_cache 回退.

    g1-canonical-run-identity D5 A+ 兼容层：既有 debate/600519/ 旧目录的历史 md
    保留不迁，_check_cache 先查 canonical 路径（_debate_path），不存在时回退此旧路径。
    force=True 清理时也同时清 canonical + 旧纯数字路径。
    """
    from data.lib.identity import canonical_code
    today = date.today().isoformat()
    code = canonical_code(ticker)
    return Path(f"debate/{code}/{today}.md")


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


def _append_usage_summary(path: Path, usage_log: list[dict]) -> None:
    """追加 token usage 汇总段（f1-deviation-fix §7，AD-03 成本实测）.

    把每次 LLM 调用的 usage 累加，写入辩论记录 md 末尾。不改 CouncilResult schema。
    缺失 usage（mock/旧 API 无 usage 字段）时写"未采集"占位，不崩溃。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    total_prompt = sum(int(u.get("prompt_tokens", 0) or 0) for u in usage_log)
    total_completion = sum(int(u.get("completion_tokens", 0) or 0) for u in usage_log)
    total_tokens = sum(int(u.get("total_tokens", 0) or 0) for u in usage_log)
    with path.open("a", encoding="utf-8") as f:
        f.write("\n## Token Usage（AD-03 成本实测）\n")
        if not usage_log:
            f.write("（本次未采集到 usage，可能为 mock 或 API 未返回 usage 字段）\n")
            return
        f.write(f"- 调用次数：{len(usage_log)}\n")
        f.write(f"- prompt_tokens 合计：{total_prompt}\n")
        f.write(f"- completion_tokens 合计：{total_completion}\n")
        f.write(f"- total_tokens 合计：{total_tokens}\n")
        f.write("```json\n")
        f.write(json.dumps(usage_log, ensure_ascii=False, indent=2))
        f.write("\n```\n")


def _append_orchestration_state(
    path: Path,
    da_skipped_reason: str | None,
    council_degraded: bool,
    degraded_reason: str | None,
) -> None:
    """f2 CR P2：追加编排状态段到 debate md，供 _parse_debate_markdown 缓存恢复.

    写入 da_skipped_reason/council_degraded/degraded_reason 三字段。
    缓存命中（同股同日重跑）时 _parse_debate_markdown 从此段恢复编排状态，
    避免 CLI to_json / 质量门因缓存丢失降级/跳 DA 上下文。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "da_skipped_reason": da_skipped_reason,
        "council_degraded": council_degraded,
        "degraded_reason": degraded_reason,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write("\n## 编排状态\n")
        f.write("```json\n")
        f.write(json.dumps(state, ensure_ascii=False, indent=2))
        f.write("\n```\n")


async def _call_da(
    round1: list[AgentOutput],
    round2: list[AgentOutput] | None,
    ticker: str,
    features: dict,
    usage_accumulator: list[dict] | None = None,
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

    raw_json, usage = await call_llm(system_prompt, user_message, "heavy")
    if usage_accumulator is not None and usage:
        usage_accumulator.append({"agent": "da", "round": "heavy", **usage})
    return AgentOutput.from_json("da", raw_json)


async def _call_synthesizer(
    round1: list[AgentOutput],
    round2: list[AgentOutput] | None,
    da_result: AgentOutput | None,
    ticker: str,
    features: dict,
    usage_accumulator: list[dict] | None = None,
    da_skipped_reason: str | None = None,
) -> SynthesizerOutput:
    """调用 Synthesizer（共识收敛器）.

    传入 R1+R2+R3 的输出，返回 SynthesizerOutput。
    f2 CR P1#1：da_skipped_reason 非空时，user message 注入引导，让 LLM 知道
    为何没 DA（low/extreme/evidence_exhausted/runtime_degraded），并在
    consensus_summary 标注此原因。
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
    elif da_skipped_reason:
        # f2 CR P1#1：DA 被跳过时，告知 synthesizer 原因，引导其基于 R1(+R2) 自行收敛
        parts.append(
            f"\n## ⚠️ DA 被跳过（da_skipped_reason: {da_skipped_reason}）\n"
            f"本次无 Devil's Advocate 仲裁报告。原因：{da_skipped_reason}。\n"
            f"请基于 R1（+R2 if 已提供）自行加权多数收敛，consensus_summary 须标注"
            f"「DA 被跳过（{da_skipped_reason}）」。"
        )

    user_message = "\n".join(parts)

    raw_json, usage = await call_llm(system_prompt, user_message, "moderate")
    if usage_accumulator is not None and usage:
        usage_accumulator.append({"agent": "synthesizer", "round": "moderate", **usage})
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

    # f2 CR P2：解析「## 编排状态」JSON 段恢复 da_skipped_reason/council_degraded/degraded_reason
    # 老格式 md 无此段 → 3 字段走默认 None/False，向后兼容
    da_skipped_reason: str | None = None
    council_degraded = False
    degraded_reason: str | None = None
    state_marker = "## 编排状态"
    state_idx = content.find(state_marker)
    if state_idx >= 0:
        state_json_start = content.find("```json", state_idx)
        if state_json_start >= 0:
            state_json_start = content.find("\n", state_json_start) + 1
            state_json_end = content.find("```", state_json_start)
            if state_json_end >= 0:
                block = content[state_json_start:state_json_end].strip()
                try:
                    state = json.loads(block)
                    da_skipped_reason = state.get("da_skipped_reason")
                    council_degraded = state.get("council_degraded", False)
                    degraded_reason = state.get("degraded_reason")
                except json.JSONDecodeError:
                    pass  # 编排状态段损坏 → 走默认，不崩

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
        da_skipped_reason=da_skipped_reason,
        council_degraded=council_degraded,
        degraded_reason=degraded_reason,
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
    # g1-canonical-run-identity D5 A+：canonical 路径不存在时回退旧纯数字路径
    # （兼容既有 debate/600519/ 旧目录，升级后仍可命中）
    if not path.exists():
        legacy = _legacy_debate_path(ticker)
        if legacy.exists():
            path = legacy
        else:
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
    # g1-canonical-run-identity D5 A+：入口 canonicalize ticker，后续 _debate_path /
    # _check_cache / _write_council_output / CouncilResult 全用 canonical 形式，
    # 无论调用方传纯数字 600519 还是带后缀 600519.SH 都统一。
    from data.lib.identity import canonical_ticker
    ticker = canonical_ticker(ticker)

    # 1. 获取特征数据
    # f3a §3 D4：L3 入口从 assemble_council_features 改为 build_research_dossier，
    # features 形参语义从「扁平 21 字段」变为「分层 dossier」（形参名保持 features 不变）。
    # build_research_dossier 内部 core_snapshot 不足时已抛 ValueError（与原 guard 同模式）。
    if features is None:
        features = build_research_dossier(ticker)
        # build_research_dossier 对 core_snapshot 不足已在内部 fail-fast 抛 ValueError；
        # 此处保留向后兼容：若调用方传入旧扁平 features 含 error 仍走原 guard
        if isinstance(features, dict) and "error" in features and "research_dossier" not in features:
            missing = features.get("missing_fields", [])
            guard = features.get("guard", "unknown")
            guard_detail = features.get("guard_detail", "")
            raise ValueError(
                f"insufficient_data [{guard}]: 缺失字段 {missing}。"
                f"{guard_detail}。再重跑 council。"
            )

    # 2. 确定 agent 列表
    if agents is None:
        agents = list(AGENT_REGISTRY.keys())

    # 3. 检查缓存（除非 force=True）
    if not force:
        cached = _check_cache(ticker)
        if cached is not None:
            return cached

    # 4. 准备辩论记录文件
    # g1-canonical-run-identity D5 A+：force=True 同时清 canonical + 旧纯数字路径，
    # 避免旧内容残留（既有 debate/{纯数字}/ 旧目录 + 新 debate/{canonical}/ 都清）。
    path = _debate_path(ticker)
    if force:
        if path.exists():
            path.unlink()
        legacy = _legacy_debate_path(ticker)
        if legacy.exists():
            legacy.unlink()

    # f1-deviation-fix §7：token usage 累加器（供 AD-03 成本实测，写入辩论记录 md，不改 schema）
    usage_log: list[dict] = []

    # f2 §3.5/3.6：R1 用 return_exceptions 收集，统计 error rate
    r1_tasks = [
        call_agent(
            agent_id, ticker, features,
            other_opinions=None, reasoning_level="heavy",
            usage_accumulator=usage_log,
        )
        for agent_id in agents
    ]
    r1_raw = await asyncio.gather(*r1_tasks, return_exceptions=True)

    # 分离成功/失败：失败的是 Exception 实例
    round1: list[AgentOutput] = []
    r1_errors: list[Exception] = []
    for item in r1_raw:
        if isinstance(item, Exception):
            r1_errors.append(item)
        else:
            round1.append(item)

    # f3c §D2：R1 质量门主流程断路器。f1 把 detect_circular_reference /
    # verify_r1_feature_grounding 放 verify_quality_gate.py 但没在 run_debate 调，
    # 导致质量门只在人工检查时 print、watchlist 产出照常落盘（CLAUDE.md 悬案
    # 6/7 watchlist null 闭环根因）。f3c 在此接入：显性环形引用 hard fail 阻断
    # （R1 other_opinions=None 本该隔离，core_thesis 引用他人只能是模型编造，
    # 铁证无歧义），凭空数字/隐性串台 soft warning（记入 r1_quality_warnings，
    # 不阻断——凭空数字有 dossier 嵌套误判风险，隐性串台字符串匹配有逃逸面）。
    # 在 error_rate/降级判断之前：降级豁免 R3 DA 跳过，不豁免串台铁证。
    # 延迟 import 打破循环依赖（verify_quality_gate 顶部 import run_debate）。
    from council.verify_quality_gate import detect_circular_reference, verify_r1_feature_grounding

    r1_quality_warnings: list[str] = []
    for agent in round1:
        ok_circ, circ_issues = detect_circular_reference(agent)
        if not ok_circ:
            raise ValueError(
                f"circular_reference: {agent.name} 的 R1 core_thesis 引用其他 agent"
                f"（{circ_issues}）。R1 other_opinions=None 本该隔离，引用他人只能是"
                f"模型编造/串台。不产出'成功'JSON 落盘。检查 system prompt 案例锚定"
                f"是否诱导复读或模型幻觉后重跑。"
            )
        ok_ground, ground_issues = verify_r1_feature_grounding(agent, features)
        if not ok_ground:
            r1_quality_warnings.append(
                f"{agent.name}: {ground_issues}"
            )

    # f2 §3.5/3.6：error rate ≥ 0.4 触发运行时降级（动态比，spec review #4）
    active_count = len(agents)
    failed_count = len(r1_errors)
    error_rate = failed_count / active_count if active_count else 0.0
    runtime_degraded = error_rate >= 0.4

    # 编排状态：DA skipped reason + 降级标记（写 CouncilResult，spec review #3 连带）
    da_skipped_reason: str | None = None
    council_degraded = False
    degraded_reason: str | None = None

    if runtime_degraded:
        # f2 CR P1#3：R1 全部失败（无幸存 agent）→ fail-fast，不跑 R4/不写空壳 watchlist。
        # 「用幸存 R1 做 R4」前提是有幸存 R1；全空时连 final_verdict 都凑不出，
        # 硬出结论会重新引入 L3 最怕的无依据输出（600900 教训）。与 f1 insufficient_data 同模式。
        if not round1:
            raise ValueError(
                f"council_failed: all_agents_failed——R1 全部 {active_count} 个 agent 失败"
                f"（error_rate=100%），无幸存观点，无法产出 council。"
                f"检查 LLM 限流/模型故障后重跑。"
            )
        # 运行时降级：跳 R2/R3，用幸存 R1 做 R4，confidence_cap=40
        council_degraded = True
        degraded_reason = "high_agent_error_rate"
        da_skipped_reason = "runtime_degraded"
        round2 = None
        da_result = None
        _append_round(path, 1, round1 if round1 else None)
        _append_round(path, 2, None)  # 跳 R2
        _append_round(path, 3, None)  # 跳 R3
    elif len(agents) == 1 and not mock_opinions:
        # 单 agent 且无 mock 注入：跳过 R2/R3（沿用原逻辑，不调分歧度分流——
        # 单 agent compute_divergence 无意义且会因 other_opinions 缺失影响 R2）
        round2 = None
        da_result = None
        _append_round(path, 1, round1)
        _append_round(path, 2, None)
        _append_round(path, 3, None)
    else:
        _append_round(path, 1, round1)

        if len(agents) == 1:
            # 单 agent + mock_opinions 注入：跑 R2（机制门验证），但不调分流/DA/synth
            # （沿用原 test_mock_injection 行为）
            r2_tasks = []
            for agent_id in agents:
                others = [a for a in round1 if a.name != agent_id]
                if mock_opinions and agent_id in mock_opinions:
                    others.append(mock_opinions[agent_id])
                r2_tasks.append(
                    call_agent(
                        agent_id, ticker, features,
                        other_opinions=others, reasoning_level="heavy",
                        usage_accumulator=usage_log,
                    )
                )
            round2 = await asyncio.gather(*r2_tasks)
            _append_round(path, 2, round2)
            da_result = None
            _append_round(path, 3, None)
        else:
            # f2 §3.1/3.2：R1 后分歧度分流（D1）
            from council.divergence import compute_divergence
            divergence = compute_divergence(round1)
            level = divergence["level"]

            if level in ("low", "extreme"):
                # 低/极高分歧跳 R2/R3，直接 R4（spec review #1：extreme 输出 neutral+divergence_level）
                da_skipped_reason = "low_divergence" if level == "low" else "extreme_divergence"
                round2 = None
                da_result = None
                _append_round(path, 2, None)
                _append_round(path, 3, None)
            else:
                # medium/high：跑 R2
                r2_tasks = []
                for agent_id in agents:
                    others = [a for a in round1 if a.name != agent_id]
                    if mock_opinions and agent_id in mock_opinions:
                        others.append(mock_opinions[agent_id])
                    r2_tasks.append(
                        call_agent(
                            agent_id, ticker, features,
                            other_opinions=others, reasoning_level="heavy",
                            usage_accumulator=usage_log,
                        )
                    )
                round2 = await asyncio.gather(*r2_tasks)
                _append_round(path, 2, round2)

                # f2 §3.3/3.4：R2 后聚合 evidence_exhausted，≥3 则跳 R3
                exhausted_count = sum(
                    1 for a in round2 if getattr(a, "evidence_exhausted", False)
                )
                if exhausted_count >= 3:
                    da_skipped_reason = "evidence_exhausted"
                    da_result = None
                    _append_round(path, 3, None)
                else:
                    da_result = await _call_da(
                        round1, round2, ticker, features, usage_accumulator=usage_log
                    )
                    _append_da_round(path, da_result)

    # Round 4: 收敛共识（单 agent 或降级时仍跑 R4，用幸存 R1）
    if len(agents) == 1 and not runtime_degraded:
        consensus = None
        _append_round(path, 4, None)
    else:
        consensus = await _call_synthesizer(
            round1, round2, da_result, ticker, features,
            usage_accumulator=usage_log,
            da_skipped_reason=da_skipped_reason,
        )
        # f2 §3.5/3.6：运行时降级时 confidence_cap=40
        if runtime_degraded and consensus and consensus.conviction > 40:
            consensus.conviction = 40
        _append_synthesizer_round(path, consensus)

    # f1-deviation-fix §7：把 token usage 汇总写入辩论记录（AD-03 成本实测，不改 CouncilResult schema）
    _append_usage_summary(path, usage_log)

    # f2 CR P2：编排状态写入 debate md，供缓存恢复（da_skipped_reason/council_degraded/degraded_reason）
    _append_orchestration_state(path, da_skipped_reason, council_degraded, degraded_reason)

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
        da_skipped_reason=da_skipped_reason,
        council_degraded=council_degraded,
        degraded_reason=degraded_reason,
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

    # g1-canonical-run-identity D5 A+：result.ticker canonical 化（带后缀），
    # 无论 run_debate 入口收到纯数字还是带后缀，watchlist 文件名 + 字段都统一 canonical，
    # 与 _debate_path 口径一致，消除 600009.json（空壳）/600009.SH.json（真数据）分裂。
    from data.lib.identity import canonical_ticker
    canonical = canonical_ticker(result.ticker)

    # f2 §3.7：分歧报告字段从 round4 SynthesizerOutput 取（DA skipped 时 round4 仍跑）
    r4 = result.round4
    output = {
        "ticker": canonical,
        "date": date_str,
        "final_verdict": result.final_verdict,
        "conviction": r4.conviction if r4 else None,
        "consensus_summary": result.consensus_summary,
        "key_variables": result.key_variables,
        "dissent_points": result.dissent_points,
        "pending_verification": result.pending_verification,
        "debate_path": str(debate_path),
        # f2 §1 分歧报告字段（round4 可能 None，如单 agent 跳 R4）
        "divergence_level": r4.divergence_level if r4 else None,
        "divergence_score": r4.divergence_score if r4 else None,
        "key_disagreements": r4.key_disagreements if r4 else [],
        "confidence_adjustment": r4.confidence_adjustment if r4 else 0.0,
        "divergence_source": r4.divergence_source if r4 else None,
        "calibration_status": r4.calibration_status if r4 else "uncalibrated",
        # f2 §3.7 + spec review #3：DA skipped reason + 运行时降级标记
        "da_skipped_reason": result.da_skipped_reason,
        "council_degraded": result.council_degraded,
        "degraded_reason": result.degraded_reason,
    }

    # L4 消费方：文件名用 canonical ticker（含交易所后缀 600519.SH），与字段一致
    # g1-canonical-run-identity D5 A+：canonical 化确保无论 result.ticker 是纯数字还是
    # 带后缀，watchlist 文件名都统一为带后缀（与 _debate_path 口径一致，消除空壳/真数据分裂）。
    output_path = watchlist_dir / f"{date_str}_{canonical}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
