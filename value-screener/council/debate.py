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
import math
import os
import re
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

from council.agents import AGENT_REGISTRY, get_prompt_builder, get_agent_display_name
from council.features import assemble_council_features
from council.llm import call_llm
from council.research_dossier import build_research_dossier
from council.schema import AgentOutput, CouncilResult, SynthesizerOutput, ValidationError


_REQUIRED_CORE_FACTS = ("name", "market_cap", "pe_ttm", "roe_3y", "net_margin")
_TICKER_BINDING_KEYS = ("ticker", "code", "symbol")
_MAIN_BUSINESS_EVIDENCE_KEYS = (
    "by_industry",
    "by_product",
    "by_region",
    "main_business_text",
    "business_scope",
    "product_type",
)


def _has_evidence_value(value: Any) -> bool:
    """判断字段是否含可供 Council 消费的值（不把 None/空容器当事实）。"""
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_evidence_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_evidence_value(item) for item in value)
    return True


def _validate_declared_ticker(
    requested_ticker: str,
    payload: dict,
    *,
    location: str,
) -> None:
    """校验 dossier 已声明的 ticker/code 不会与本次请求串台。"""
    from data.lib.identity import canonical_ticker

    for key in _TICKER_BINDING_KEYS:
        declared = payload.get(key)
        if declared is None:
            continue
        if not isinstance(declared, str) or not declared.strip():
            raise ValueError(
                f"no_evidence: {location}.{key} must be a non-empty ticker string."
            )
        try:
            canonical_declared = canonical_ticker(declared)
        except ValueError as exc:
            raise ValueError(
                f"no_evidence: {location}.{key} is not a valid ticker ({declared!r})."
            ) from exc
        if canonical_declared != requested_ticker:
            raise ValueError(
                "no_evidence: ticker mismatch between requested "
                f"{requested_ticker} and {location}.{key}={canonical_declared}."
            )


def _validate_dossier_ticker_identity(requested_ticker: str, dossier: dict) -> None:
    """要求显式 dossier 的 canonical identity 存在且在可选分区中保持一致。"""
    core = dossier.get("core_snapshot")
    declared_ticker = core.get("ticker")
    if not isinstance(declared_ticker, str) or not declared_ticker.strip():
        raise ValueError(
            "no_evidence: dossier.core_snapshot.ticker is required for explicit dossier."
        )
    _validate_declared_ticker(requested_ticker, core, location="core_snapshot")

    def validate_section(value: Any, location: str) -> None:
        if isinstance(value, Mapping):
            for key in _TICKER_BINDING_KEYS:
                if key in value:
                    _validate_declared_ticker(
                        requested_ticker,
                        value,
                        location=f"{location}.{key}",
                    )
            for key, child in value.items():
                if isinstance(child, (Mapping, list, tuple)):
                    validate_section(child, f"{location}.{key}")
        elif isinstance(value, (list, tuple)):
            for index, child in enumerate(value):
                validate_section(child, f"{location}[{index}]")

    validate_section(core, "core_snapshot")

    research = dossier.get("research_dossier")
    if isinstance(research, Mapping):
        validate_section(research, "research_dossier")
    for section_name, section in dossier.items():
        if section_name not in {"core_snapshot", "research_dossier"}:
            validate_section(section, section_name)


def _validate_council_input(ticker: str, dossier: Any) -> dict:
    """验证可进入 Council 的分层 dossier，失败时不允许任何后续副作用。"""
    if not isinstance(dossier, dict) or not dossier:
        raise ValueError("no_evidence: Council input must be a non-empty dossier dict.")
    if "error" in dossier or dossier.get("__error__"):
        detail = dossier.get("error") or dossier.get("reason") or "caller-provided error shell"
        raise ValueError(f"insufficient_data: {detail}. Provide a verified dossier or skip.")

    core = dossier.get("core_snapshot")
    if not isinstance(core, dict) or not core:
        raise ValueError("no_evidence: dossier.core_snapshot must be a non-empty dict.")
    if "error" in core or core.get("__error__"):
        detail = core.get("error") or core.get("reason") or "core_snapshot error shell"
        raise ValueError(f"insufficient_data: {detail}. Provide a verified dossier or skip.")

    missing_core = [field for field in _REQUIRED_CORE_FACTS if not _has_evidence_value(core.get(field))]
    if missing_core:
        raise ValueError(
            "insufficient_data: core_snapshot missing required facts "
            f"{missing_core}. Provide a verified dossier or skip."
        )

    research = dossier.get("research_dossier")
    if not isinstance(research, Mapping):
        raise ValueError("no_evidence: dossier.research_dossier must be a dict.")
    main_business = research.get("main_business")
    if not isinstance(main_business, Mapping) or not main_business:
        raise ValueError(
            "no_evidence: dossier.research_dossier.main_business must be a non-empty dict."
        )
    if "error" in main_business or main_business.get("__error__"):
        raise ValueError(
            "no_evidence: dossier.research_dossier.main_business is unavailable."
        )
    if not any(
        _has_evidence_value(main_business.get(key))
        for key in _MAIN_BUSINESS_EVIDENCE_KEYS
    ):
        raise ValueError(
            "no_evidence: dossier.research_dossier.main_business has no business facts."
        )
    _validate_dossier_ticker_identity(ticker, dossier)

    # g2-dossier-data-quality：无论 builder 还是显式 caller-provided dossier，都必须
    # 从 raw payload 重新校验事实契约，避免 caller 注入伪造 fact_contract 绕过
    # 高严重度 fail-closed。这里只 fail-closed，不修改输入 payload（保护 audit identity hash）。
    from council.fact_grounding import build_fact_contract

    contract = build_fact_contract(dossier, ticker=ticker, fail_closed=False)
    non_core_failures = [
        fact
        for fact in contract.get("facts", [])
        if fact.get("role") != "core_snapshot"
        and fact.get("severity") == "high"
        and not fact.get("traceable")
    ]
    if non_core_failures or contract.get("high_severity_invalid_count"):
        details = "; ".join(
            f"{fact.get('fact_key')}: {fact.get('reason') or 'untraceable'}"
            for fact in non_core_failures
        )
        details = details or "; ".join(contract.get("high_severity_invalid_reasons", []))
        from council.fact_grounding import FactContractError

        raise FactContractError(f"high severity facts fail closed: {details}")

    return dossier


def _prepare_council_input(ticker: str, features: Any) -> dict:
    """解析所有入口输入，并在 cache/LLM 前收敛到已验证 dossier。"""
    if features is None:
        dossier = build_research_dossier(ticker)
    elif not isinstance(features, dict):
        raise ValueError("no_evidence: explicit features must be a dict or None.")
    elif not features:
        raise ValueError(
            "no_evidence: explicit empty features cannot start a council debate. "
            "Provide a verified dossier or skip the council run."
        )
    elif "error" in features or features.get("__error__"):
        detail = features.get("error") or features.get("reason") or "caller-provided error shell"
        raise ValueError(f"insufficient_data: {detail}. Provide a verified dossier or skip.")
    elif "core_snapshot" in features or "research_dossier" in features:
        dossier = features
    else:
        # 兼容旧的扁平快照调用，但不允许其绕过 dossier builder 或 preflight。
        dossier = build_research_dossier(ticker, core_snapshot=features)

    return _validate_council_input(ticker, dossier)


async def call_agent(
    agent_id: str,
    ticker: str,
    features: dict,
    other_opinions: list[AgentOutput] | None = None,
    reasoning_level: str = "heavy",
    usage_accumulator: list[dict] | None = None,
    prompt_recorder: list[dict] | None = None,
    prompt_stage: str | None = None,
    model: str | None = None,
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
    if prompt_recorder is not None:
        prompt_recorder.append(
            {
                "agent": agent_id,
                "stage": prompt_stage,
                "round": reasoning_level,
                "system_prompt": system_prompt,
                "user_message": user_message,
            }
        )

    # 调用 LLM（f1-deviation-fix §7：返回 (content, usage)，usage 供 AD-03 成本累加）
    if model is None:
        raw_json, usage = await call_llm(system_prompt, user_message, reasoning_level)
    else:
        raw_json, usage = await call_llm(
            system_prompt,
            user_message,
            reasoning_level,
            model=model,
        )
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
    from council.fact_grounding import (
        build_fact_contract,
        derive_quality_status,
    )

    # caller-supplied fact_contract/quality_status are sidecars only; always
    # recompute from raw dossier so a forged clean sidecar cannot expose numbers.
    fact_contract = build_fact_contract(
        dossier,
        ticker=core.get("ticker"),
        fail_closed=False,
    )
    dossier_quality_status, dossier_quality_reasons = derive_quality_status(fact_contract)
    role_degraded = {
        item.get("role")
        for item in fact_contract.get("role_status", [])
        if item.get("degradation_status") != "clean"
    }
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
    grounded_core = _grounded_core_snapshot(core, fact_contract)
    parts.append(json.dumps(grounded_core, ensure_ascii=False, indent=2))
    if dossier_quality_status != "clean":
        parts.append(
            "该 dossier 质量状态为 "
            f"{dossier_quality_status}，以下未展示的数字不得自行补全。"
        )

    fact_dims = [d for d in ("main_business", "peers", "capex_proxy")
                 if d in visible_dims]
    for dim in fact_dims:
        dim_data = rd.get(dim)
        is_degraded = (
            dim in degraded_fields
            or dim in role_degraded
            or _is_error_data(dim_data)
        )
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
        is_research_degraded = (
            "research" in degraded_fields
            or "research" in role_degraded
            or _is_error_data(research_data)
        )
        if is_research_degraded:
            parts.append(_degraded_note("research"))
        else:
            parts.append(json.dumps(research_data, ensure_ascii=False, indent=2))

    return parts


def _grounded_core_snapshot(
    core: dict[str, Any],
    fact_contract: dict[str, Any],
) -> dict[str, Any]:
    """只把有字段级 clean provenance 的 core 数字送入 prompt."""
    facts = {
        fact.get("fact_key"): fact
        for fact in fact_contract.get("facts", [])
        if fact.get("role") == "core_snapshot"
    }
    core_status = next(
        (
            item
            for item in fact_contract.get("role_status", [])
            if item.get("role") == "core_snapshot"
        ),
        {},
    )
    core_clean = core_status.get("degradation_status") == "clean"
    grounded: dict[str, Any] = {}
    for key, value in core.items():
        if key in {"fact_provenance", "provenance"}:
            continue
        if isinstance(value, (int, float, list, tuple)):
            if not core_clean:
                continue
            fact = facts.get(f"core_snapshot.{key}")
            if not fact or not fact.get("traceable") or fact.get("degradation_status") != "clean":
                continue
        grounded[key] = value
    return grounded


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


def _debate_path(ticker: str, run_id: str | None = None) -> Path:
    """返回辩论记录路径；audited run 使用 run-scoped 目录.

    g1-canonical-run-identity D5 A+：新写入统一 canonical（600519.SH），与
    _write_council_output 的 watchlist 文件名口径一致，消除 600009.json（空壳）/
    600009.SH.json（真数据）分裂。既有 debate/{纯数字}/ 旧目录保留，_check_cache
    回退读取（见 _legacy_debate_path）。
    """
    from data.lib.identity import canonical_ticker
    today = date.today().isoformat()
    canonical = canonical_ticker(ticker)
    if run_id is not None:
        return Path(f"debate/{canonical}/{run_id}/{today}.md")
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
    dossier_quality_status: str | None,
    dossier_quality_reasons: list[str] | None,
    dossier_quality_contract: dict | None,
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
        "dossier_quality_status": dossier_quality_status,
        "dossier_quality_reasons": dossier_quality_reasons or [],
        "dossier_quality_contract": dossier_quality_contract,
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
    prompt_recorder: list[dict] | None = None,
    model: str | None = None,
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
    if prompt_recorder is not None:
        prompt_recorder.append(
            {
                "agent": "da",
                "stage": "r3",
                "round": "heavy",
                "system_prompt": system_prompt,
                "user_message": user_message,
            }
        )

    if model is None:
        raw_json, usage = await call_llm(system_prompt, user_message, "heavy")
    else:
        raw_json, usage = await call_llm(
            system_prompt,
            user_message,
            "heavy",
            model=model,
        )
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
    prompt_recorder: list[dict] | None = None,
    model: str | None = None,
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
    if prompt_recorder is not None:
        prompt_recorder.append(
            {
                "agent": "synthesizer",
                "stage": "r4",
                "round": "moderate",
                "system_prompt": system_prompt,
                "user_message": user_message,
            }
        )

    if model is None:
        raw_json, usage = await call_llm(system_prompt, user_message, "moderate")
    else:
        raw_json, usage = await call_llm(
            system_prompt,
            user_message,
            "moderate",
            model=model,
        )
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
    dossier_quality_status: str = "degraded"
    dossier_quality_reasons: list[str] = ["legacy dossier quality unknown"]
    dossier_quality_contract: dict | None = None
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
                    dossier_quality_status = state.get("dossier_quality_status", "degraded")
                    dossier_quality_reasons = state.get(
                        "dossier_quality_reasons",
                        ["legacy dossier quality unknown"],
                    ) or []
                    dossier_quality_contract = state.get("dossier_quality_contract")
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
        execution_mode="council",
        dossier_quality_status=dossier_quality_status,
        dossier_quality_reasons=dossier_quality_reasons,
        dossier_quality_contract=dossier_quality_contract,
        dissent_points=round4_synthesizer.dissent_points if round4_synthesizer else None,
        pending_verification=round4_synthesizer.pending_verification if round4_synthesizer else None,
    )


def _check_cache(
    ticker: str,
    *,
    expected_execution_mode: str | None = None,
) -> CouncilResult | None:
    """检查辩论记录缓存，命中则返回 CouncilResult.

    命中条件：debate/{ticker}/{date}.md 存在、绑定的 G2 quality record
    是 complete 且 final quality gate passed，且至少含 Round 1 节。

    解析失败（格式损坏）→ 返回 None（降级为重跑）。

    Args:
    ticker: 股票代码
    expected_execution_mode: 本次请求的编排模式；不匹配的 record 不能命中

    Returns:
        CouncilResult 或 None（未命中/解析失败）
    """
    from data.lib.identity import canonical_ticker
    from data.lib.quality_status import (
        is_success_cache_eligible,
        read_quality_record,
    )

    canonical = canonical_ticker(ticker)
    quality_root = Path("quality_status") / canonical
    matching_quality_record = None
    record_paths: list[tuple[int, str, Path]] = []
    for candidate in quality_root.glob("*/record.json"):
        try:
            mtime_ns = candidate.stat().st_mtime_ns
        except OSError:
            continue
        record_paths.append((mtime_ns, candidate.parent.name, candidate))
    record_paths.sort(reverse=True)
    for _, _, record_path in record_paths:
        try:
            record = read_quality_record(
                ".",
                canonical,
                record_path.parent.name,
            )
        except (OSError, ValueError):
            return None
        if record is None:
            return None
        if (
            expected_execution_mode is not None
            and record.execution_mode != expected_execution_mode
        ):
            return None
        matching_quality_record = record
        break
    if (
        matching_quality_record is None
        or not is_success_cache_eligible(matching_quality_record)
        or not matching_quality_record.artifact_path
    ):
        return None
    path = Path(matching_quality_record.artifact_path)
    expected_artifact_root = (
        Path("debate")
        / canonical
        / matching_quality_record.run_id
    ).resolve()
    try:
        path.resolve().relative_to(expected_artifact_root)
    except ValueError:
        return None
    if path.name != f"{date.today().isoformat()}.md":
        return None
    if not path.exists():
        return None

    if not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    if "## Round 1" not in content:
        return None

    result = _parse_debate_markdown(content, ticker)
    if result is not None:
        result.run_id = matching_quality_record.run_id
        result.execution_mode = matching_quality_record.execution_mode
        result.run_quality_status = matching_quality_record.status
        result.run_quality_reasons = list(matching_quality_record.reasons)
        result.final_quality_gate = matching_quality_record.final_quality_gate
        result.success_cache_eligible = is_success_cache_eligible(matching_quality_record)
        result.quality_record_path = str(
            quality_root / matching_quality_record.run_id / "record.json"
        )
        result.debate_path = str(path)
    return result


async def run_debate(
    ticker: str,
    features: dict | None = None,
    agents: list[str] | None = None,
    force: bool = False,
    mock_opinions: dict[str, AgentOutput] | None = None,
    audit_root: str | Path | None = None,
    audit_identity=None,
    profile_version: str | None = None,
    prompt_version: str | None = None,
    model_configuration: dict | None = None,
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
    from data.lib.identity import canonical_ticker, generate_run_id
    from data.lib.audit_chain import (
        AuditChainWriter,
        create_audit_identity,
        payload_sha256,
        validate_audit_identity,
        validate_audit_identity_structure,
    )
    from council.fact_grounding import dossier_without_quality_sidecar
    if audit_identity is not None:
        validate_audit_identity_structure(audit_identity)
    ticker = canonical_ticker(ticker)

    # 1. 解析并验证输入。所有显式/隐式路径都必须在 cache、文件写入和任意 LLM
    # 调用前收敛为可审计 dossier；失败表示本次 Council 根本未执行。
    features = _prepare_council_input(ticker, features)
    from council.fact_grounding import evaluate_dossier_quality

    dossier_quality_status, dossier_quality_reasons, dossier_quality_contract = evaluate_dossier_quality(
        features,
        ticker=ticker,
    )
    audit_dossier = dossier_without_quality_sidecar(features)
    provided_model_configuration = model_configuration or {}
    unsupported_model_fields = set(provided_model_configuration) - {
        "heavy_model",
        "moderate_model",
        "reasoning_levels",
    }
    if unsupported_model_fields:
        raise ValueError(
            "unsupported council model_configuration fields: "
            + ", ".join(sorted(unsupported_model_fields))
        )
    if (
        "reasoning_levels" in provided_model_configuration
        and provided_model_configuration["reasoning_levels"] != ["heavy", "moderate"]
    ):
        raise ValueError(
            "reasoning_levels must remain ['heavy', 'moderate'] for Council runtime"
        )
    runtime_model_configuration = {
        "heavy_model": os.environ.get("LLM_MODEL_HEAVY"),
        "moderate_model": os.environ.get("LLM_MODEL_MODERATE"),
        "reasoning_levels": ["heavy", "moderate"],
        **provided_model_configuration,
    }
    if audit_identity is not None:
        if profile_version is not None and profile_version != audit_identity.profile_version:
            raise ValueError("council profile_version does not match audit identity")
        if prompt_version is not None and prompt_version != audit_identity.prompt_version:
            raise ValueError("council prompt_version does not match audit identity")
        if runtime_model_configuration != audit_identity.model_configuration:
            raise ValueError("council model_configuration does not match audit identity")
        validate_audit_identity(audit_identity, ticker=ticker, dossier=audit_dossier)
    elif audit_root is not None:
        audit_identity = create_audit_identity(
            ticker,
            dossier=audit_dossier,
            profile_version=profile_version or "g2-council-v1",
            prompt_version=prompt_version or "council-prompt-v1",
            model_configuration=runtime_model_configuration,
        )
    if agents is None:
        agents = list(AGENT_REGISTRY.keys())
    execution_mode = "single_agent" if len(agents) == 1 else "council"
    quality_run_id = audit_identity.run_id if audit_identity is not None else generate_run_id()
    from data.lib.quality_status import RunQualityRecord, write_quality_record

    def persist_early_incomplete(reason: str) -> None:
        write_quality_record(
            ".",
            RunQualityRecord(
                canonical_ticker=ticker,
                run_id=quality_run_id,
                status="incomplete",
                reasons=(reason,),
                completed_stages=(),
                final_quality_gate="not_run",
                execution_mode=execution_mode,
            ),
        )

    audit_writer = None
    if audit_identity is not None:
        try:
            audit_writer = AuditChainWriter(audit_root or "audit_runs", audit_identity)
            audit_writer.write(
                "dossier",
                {
                    "ticker": ticker,
                    "run_id": audit_identity.run_id,
                    "profile_version": audit_identity.profile_version,
                    "input_hash": audit_identity.input_hash,
                    "dossier_snapshot": audit_identity.dossier_snapshot,
                    "prompt_version": audit_identity.prompt_version,
                    "model_configuration": audit_identity.model_configuration,
                    "dossier": audit_dossier,
                    "dossier_sha256": payload_sha256(audit_dossier),
                    "dossier_quality_status": dossier_quality_status,
                    "dossier_quality_reasons": dossier_quality_reasons,
                    "fact_contract": dossier_quality_contract,
                },
            )
        except (Exception, asyncio.CancelledError):
            if audit_writer is not None:
                audit_writer.abort()
            persist_early_incomplete("audit_dossier_interrupted")
            raise

    # 2. 确定 agent 列表

    # 3. 检查缓存（除非 force=True）
    if not force and audit_writer is None:
        cached = _check_cache(
            ticker,
            expected_execution_mode=execution_mode,
        )
        if cached is not None:
            return cached

    # 4. 准备辩论记录文件
    # g1-canonical-run-identity D5 A+：force=True 同时清 canonical + 旧纯数字路径，
    # 避免旧内容残留（既有 debate/{纯数字}/ 旧目录 + 新 debate/{canonical}/ 都清）。
    path = _debate_path(ticker, quality_run_id)
    if force and audit_writer is None:
        if path.exists():
            path.unlink()
        legacy = _legacy_debate_path(ticker)
        if legacy.exists():
            legacy.unlink()

    from data.lib.quality_status import (
        RunQualityRecord,
        is_success_cache_eligible,
        replace_quality_record,
        write_quality_record,
    )

    completed_stages: list[str] = []
    quality_path: Path | None = None

    def persist_quality(
        status: str,
        *,
        reasons: tuple[str, ...],
        final_quality_gate: str,
        allow_complete_upgrade: bool = False,
    ) -> RunQualityRecord:
        nonlocal quality_path
        record = RunQualityRecord(
            canonical_ticker=ticker,
            run_id=quality_run_id,
            status=status,
            reasons=reasons,
            completed_stages=tuple(completed_stages),
            final_quality_gate=final_quality_gate,
            artifact_path=str(path),
            execution_mode=execution_mode,
        )
        if quality_path is None:
            quality_path = write_quality_record(".", record)
        else:
            replace_quality_record(
                ".",
                record,
                allow_complete_upgrade=allow_complete_upgrade,
            )
        return record

    def persist_incomplete(stage: str) -> None:
        persist_quality(
            "incomplete",
            reasons=(f"{stage}_interrupted",),
            final_quality_gate="not_run",
        )

    def append_stage(
        stage: str,
        writer,
        *args,
        completed_stage: str | None = "",
        failure_stage: str | None = None,
    ) -> None:
        try:
            writer(*args)
            if completed_stage == "":
                completed_stage = stage
            if completed_stage is not None and completed_stage not in completed_stages:
                completed_stages.append(completed_stage)
        except (Exception, asyncio.CancelledError):
            persist_incomplete(failure_stage or stage)
            if audit_writer is not None:
                audit_writer.abort()
            raise

    persist_quality(
        "incomplete",
        reasons=(),
        final_quality_gate="not_run",
    )

    # f1-deviation-fix §7：token usage 累加器（供 AD-03 成本实测，写入辩论记录 md，不改 schema）
    usage_log: list[dict] = []
    prompt_records: list[dict] = []
    heavy_model = runtime_model_configuration.get("heavy_model")
    moderate_model = runtime_model_configuration.get("moderate_model")
    prompt_record_kwargs = {}
    if audit_writer is not None:
        prompt_record_kwargs = {
            "prompt_recorder": prompt_records,
            "model": heavy_model,
        }
    audit_da_kwargs = (
        {"prompt_recorder": prompt_records, "model": heavy_model}
        if audit_writer is not None
        else {}
    )
    audit_synth_kwargs = (
        {"prompt_recorder": prompt_records, "model": moderate_model}
        if audit_writer is not None
        else {}
    )

    # f2 §3.5/3.6：R1 用 return_exceptions 收集，统计 error rate
    r1_tasks = [
        call_agent(
            agent_id, ticker, features,
            other_opinions=None, reasoning_level="heavy",
            usage_accumulator=usage_log,
            **(
                {"prompt_stage": "r1"}
                if audit_writer is not None
                else {}
            ),
            **prompt_record_kwargs,
        )
        for agent_id in agents
    ]
    try:
        r1_raw = await asyncio.gather(*r1_tasks, return_exceptions=True)
    except asyncio.CancelledError:
        persist_incomplete("r1")
        if audit_writer is not None:
            audit_writer.abort()
        raise

    # 分离成功/失败：失败的是 Exception 实例
    round1: list[AgentOutput] = []
    r1_errors: list[Exception] = []
    for item in r1_raw:
        if isinstance(item, asyncio.CancelledError):
            persist_incomplete("r1")
            if audit_writer is not None:
                audit_writer.abort()
            raise item
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
    from council.verify_quality_gate import (
        detect_circular_reference,
        verify_da_fact_check,
        verify_divergence_report,
        verify_r1_feature_grounding,
        verify_r2_new_evidence,
    )

    r1_quality_warnings: list[str] = []
    quality_warnings: list[str] = []

    def fail_quality_gate(stage: str, issues: list[str]) -> None:
        reasons = (
            (stage,)
            if stage == "r1_circular_reference"
            else tuple(
                dict.fromkeys(
                    [stage, *[f"{stage}: {issue}" for issue in issues]]
                )
            )
        )
        persist_quality(
            "failed",
            reasons=reasons,
            final_quality_gate="failed",
        )
        if audit_writer is not None:
            audit_writer.abort()
        raise ValueError(
            f"quality_gate_failed: {stage} — {'; '.join(issues)}"
        )

    def record_quality_warnings(stage: str, warnings: list[str]) -> None:
        quality_warnings.extend(
            f"{stage}: {warning}" for warning in warnings
        )

    for agent in round1:
        ok_circ, circ_issues = detect_circular_reference(agent)
        if not ok_circ:
            fail_quality_gate("r1_circular_reference", circ_issues)
        ok_ground, ground_issues = verify_r1_feature_grounding(agent, features)
        if not ok_ground:
            r1_quality_warnings.append(
                f"{agent.name}: {ground_issues}"
            )
        if ground_issues:
            record_quality_warnings("r1", [f"{agent.name}: {issue}" for issue in ground_issues])
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
            if audit_writer is not None:
                audit_writer.abort()
            persist_quality(
                "failed",
                reasons=("r1_failed",),
                final_quality_gate="failed",
            )
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
        ok_da, da_issues = verify_da_fact_check(
            None,
            agent_ids=tuple(agents),
            da_skipped_reason=da_skipped_reason,
        )
        if not ok_da:
            fail_quality_gate("da", da_issues)
        record_quality_warnings("da", da_issues)
        append_stage("r1", _append_round, path, 1, round1 if round1 else None)
        append_stage("r2", _append_round, path, 2, None, completed_stage=None)  # 跳 R2
        append_stage("da", _append_round, path, 3, None, completed_stage=None)  # 跳 R3
    elif len(agents) == 1 and not mock_opinions:
        # 单 agent 且无 mock 注入：跳过 R2/R3（沿用原逻辑，不调分歧度分流——
        # 单 agent compute_divergence 无意义且会因 other_opinions 缺失影响 R2）
        round2 = None
        da_result = None
        append_stage("r1", _append_round, path, 1, round1)
        append_stage("r2", _append_round, path, 2, None, completed_stage=None)
        append_stage("da", _append_round, path, 3, None, completed_stage=None)
    else:
        append_stage("r1", _append_round, path, 1, round1)

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
                        **(
                            {
                                **prompt_record_kwargs,
                                "prompt_stage": "r2",
                            }
                            if audit_writer is not None
                            else {}
                        ),
                    )
                )
                try:
                    round2 = await asyncio.gather(*r2_tasks)
                except (Exception, asyncio.CancelledError):
                    persist_incomplete("r2")
                    if audit_writer is not None:
                        audit_writer.abort()
                    raise
            append_stage("r2", _append_round, path, 2, round2)
            for agent in round2:
                ok_r2, r2_warnings = verify_r2_new_evidence(agent, features)
                if not ok_r2:
                    fail_quality_gate("r2", r2_warnings)
                record_quality_warnings("r2", r2_warnings)
            da_result = None
            append_stage("da", _append_round, path, 3, None)
        else:
            # f2 §3.1/3.2：R1 后分歧度分流（D1）
            from council.divergence import compute_divergence
            try:
                divergence = compute_divergence(round1)
            except (Exception, asyncio.CancelledError):
                persist_incomplete("r2")
                if audit_writer is not None:
                    audit_writer.abort()
                raise
            level = divergence["level"]

            if level in ("low", "extreme"):
                # 低/极高分歧跳 R2/R3，直接 R4（spec review #1：extreme 输出 neutral+divergence_level）
                da_skipped_reason = "low_divergence" if level == "low" else "extreme_divergence"
                round2 = None
                da_result = None
                ok_da, da_issues = verify_da_fact_check(
                    None,
                    agent_ids=tuple(agents),
                    da_skipped_reason=da_skipped_reason,
                )
                if not ok_da:
                    fail_quality_gate("da", da_issues)
                record_quality_warnings("da", da_issues)
                append_stage("r2", _append_round, path, 2, None, completed_stage=None)
                append_stage("da", _append_round, path, 3, None, completed_stage=None)
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
                            **(
                                {
                                    **prompt_record_kwargs,
                                    "prompt_stage": "r2",
                                }
                                if audit_writer is not None
                                else {}
                            ),
                        )
                    )
                try:
                    round2 = await asyncio.gather(*r2_tasks)
                except (Exception, asyncio.CancelledError):
                    persist_incomplete("r2")
                    if audit_writer is not None:
                        audit_writer.abort()
                    raise
                append_stage("r2", _append_round, path, 2, round2)
                for agent in round2:
                    ok_r2, r2_warnings = verify_r2_new_evidence(agent, features)
                    if not ok_r2:
                        fail_quality_gate("r2", r2_warnings)
                    record_quality_warnings("r2", r2_warnings)
                # f2 §3.3/3.4：R2 后聚合 evidence_exhausted，≥3 则跳 R3
                exhausted_count = sum(
                    1 for a in round2 if getattr(a, "evidence_exhausted", False)
                )
                if exhausted_count >= 3:
                    da_skipped_reason = "evidence_exhausted"
                    da_result = None
                    ok_da, da_issues = verify_da_fact_check(
                        None,
                        agent_ids=tuple(agents),
                        da_skipped_reason=da_skipped_reason,
                    )
                    if not ok_da:
                        fail_quality_gate("da", da_issues)
                    record_quality_warnings("da", da_issues)
                    append_stage("da", _append_round, path, 3, None)
                else:
                    try:
                        da_result = await _call_da(
                            round1,
                            round2,
                            ticker,
                            features,
                            usage_accumulator=usage_log,
                            **audit_da_kwargs,
                        )
                    except (Exception, asyncio.CancelledError):
                        persist_incomplete("da")
                        if audit_writer is not None:
                            audit_writer.abort()
                        raise
                    ok_da, da_issues = verify_da_fact_check(
                        da_result,
                        agent_ids=tuple(agents),
                        da_skipped_reason=None,
                    )
                    if not ok_da:
                        fail_quality_gate("da", da_issues)
                    record_quality_warnings("da", da_issues)
                    append_stage("da", _append_da_round, path, da_result)
    # Round 4: 收敛共识（单 agent 或降级时仍跑 R4，用幸存 R1）
    if len(agents) == 1 and not runtime_degraded:
        consensus = None
        append_stage(
            "synthesizer",
            _append_round,
            path,
            4,
            None,
            completed_stage=None,
        )
    else:
        try:
            consensus = await _call_synthesizer(
                round1, round2, da_result, ticker, features,
                usage_accumulator=usage_log,
                da_skipped_reason=da_skipped_reason,
                **audit_synth_kwargs,
            )
        except (Exception, asyncio.CancelledError):
            persist_incomplete("synthesizer")
            if audit_writer is not None:
                audit_writer.abort()
            raise
        # f2 §3.5/3.6：运行时降级时 confidence_cap=40
        if runtime_degraded and consensus and consensus.conviction > 40:
            consensus.conviction = 40
        ok_r4, r4_issues = verify_divergence_report(consensus)
        if not ok_r4:
            fail_quality_gate("r4", r4_issues)
        record_quality_warnings("r4", r4_issues)
        append_stage("synthesizer", _append_synthesizer_round, path, consensus)
    # f1-deviation-fix §7：把 token usage 汇总写入辩论记录（AD-03 成本实测，不改 CouncilResult schema）
    append_stage(
        "quality_artifact",
        _append_usage_summary,
        path,
        usage_log,
        completed_stage=None,
        failure_stage="quality_artifact",
    )

    # f2 CR P2：编排状态写入 debate md，供缓存恢复（da_skipped_reason/council_degraded/degraded_reason）
    append_stage(
        "final_validation",
        _append_orchestration_state,
        path,
        da_skipped_reason,
        council_degraded,
        degraded_reason,
        dossier_quality_status,
        dossier_quality_reasons,
        dossier_quality_contract,
    )

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
        execution_mode=execution_mode,
        dossier_quality_status=dossier_quality_status,
        dossier_quality_reasons=dossier_quality_reasons,
        dossier_quality_contract=dossier_quality_contract,
    )

    terminal_observations: list[str] = []
    if r1_errors:
        terminal_observations.append(
            f"r1_agent_errors:{len(r1_errors)}/{len(agents)}"
        )
    if r1_quality_warnings:
        terminal_observations.extend(r1_quality_warnings)
    if quality_warnings:
        terminal_observations.extend(quality_warnings)
    if runtime_degraded:
        terminal_observations.append(degraded_reason or "runtime_degraded")
    if da_skipped_reason:
        terminal_observations.append(da_skipped_reason)
    terminal_reasons = tuple(dict.fromkeys(terminal_observations))

    if runtime_degraded:
        terminal_status = "runtime_degraded"
        final_quality_gate = "warning"
    elif da_skipped_reason:
        terminal_status = "da_skipped"
        final_quality_gate = "warning"
    elif terminal_reasons:
        terminal_status = "warning"
        final_quality_gate = "warning"
    else:
        terminal_status = "complete"
        terminal_reasons = ()
        final_quality_gate = "passed"
    quality_record = persist_quality(
        terminal_status,
        reasons=terminal_reasons,
        final_quality_gate=final_quality_gate,
        allow_complete_upgrade=terminal_status == "complete",
    )
    result.run_id = quality_run_id
    result.run_quality_status = quality_record.status
    result.run_quality_reasons = list(quality_record.reasons)
    result.final_quality_gate = quality_record.final_quality_gate
    result.success_cache_eligible = is_success_cache_eligible(quality_record)
    result.quality_record_path = str(quality_path)
    result.debate_path = str(path)

    if audit_writer is not None:
        result.run_id = audit_identity.run_id
        result.profile_version = audit_identity.profile_version
        result.input_hash = audit_identity.input_hash
        result.dossier_snapshot = audit_identity.dossier_snapshot
        result.prompt_version = audit_identity.prompt_version
        result.model_configuration = audit_identity.model_configuration
        result.audit_manifest_path = str(audit_writer.run_root / "manifest.json")
        prompt_records.sort(
            key=lambda item: (
                {"r1": 1, "r2": 2, "r3": 3, "r4": 4}.get(item.get("stage"), 99),
                item.get("agent", ""),
                item.get("round", ""),
            )
        )
        prompt_binding = {
            "ticker": ticker,
            "run_id": audit_identity.run_id,
            "profile_version": audit_identity.profile_version,
            "input_hash": audit_identity.input_hash,
            "dossier_snapshot": audit_identity.dossier_snapshot,
            "prompt_version": audit_identity.prompt_version,
            "model_configuration": audit_identity.model_configuration,
            "prompts": prompt_records,
        }
        output_path = _council_output_path(result, path)
        staged_output_path = _staged_council_output_path(output_path)
        try:
            audit_writer.write(
                "prompt",
                {
                    "ticker": ticker,
                    "run_id": audit_identity.run_id,
                    "profile_version": audit_identity.profile_version,
                    "input_hash": audit_identity.input_hash,
                    "dossier_snapshot": audit_identity.dossier_snapshot,
                    "prompt_version": audit_identity.prompt_version,
                    "model_configuration": audit_identity.model_configuration,
                    "prompt_binding_sha256": payload_sha256(prompt_binding),
                    "prompts": prompt_records,
                },
            )
            _write_council_output(result, path, output_path=staged_output_path)
            output = json.loads(staged_output_path.read_text(encoding="utf-8"))
            audit_writer.write(
                "debate",
                {
                "ticker": ticker,
                "run_id": audit_identity.run_id,
                "profile_version": audit_identity.profile_version,
                "input_hash": audit_identity.input_hash,
                "dossier_snapshot": audit_identity.dossier_snapshot,
                "prompt_version": audit_identity.prompt_version,
                "model_configuration": audit_identity.model_configuration,
                "debate_path": str(path),
                "debate_text": path.read_text(encoding="utf-8"),
                "debate_text_sha256": payload_sha256(path.read_text(encoding="utf-8")),
                "result_sha256": payload_sha256(result.to_json()),
                },
            )
            audit_writer.write(
                "quality_report",
                {
                "ticker": ticker,
                "run_id": audit_identity.run_id,
                "profile_version": audit_identity.profile_version,
                "input_hash": audit_identity.input_hash,
                "dossier_snapshot": audit_identity.dossier_snapshot,
                "prompt_version": audit_identity.prompt_version,
                "model_configuration": audit_identity.model_configuration,
                "r1_quality_warnings": r1_quality_warnings,
                "council_degraded": council_degraded,
                "degraded_reason": degraded_reason,
                },
            )
            audit_writer.write(
                "final_result",
                {
                "ticker": ticker,
                "run_id": audit_identity.run_id,
                "profile_version": audit_identity.profile_version,
                "input_hash": audit_identity.input_hash,
                "dossier_snapshot": audit_identity.dossier_snapshot,
                "prompt_version": audit_identity.prompt_version,
                "model_configuration": audit_identity.model_configuration,
                "published_output_path": str(output_path),
                "published_output": output,
                "published_output_sha256": payload_sha256(output),
                },
            )
            audit_writer.finalize()
            _promote_staged_output(staged_output_path, output_path)
        except (Exception, asyncio.CancelledError):
            if _is_promoted_staging_output(staged_output_path, output_path):
                output_path.unlink(missing_ok=True)
            staged_output_path.unlink(missing_ok=True)
            replace_quality_record(
                ".",
                RunQualityRecord(
                    canonical_ticker=ticker,
                    run_id=quality_run_id,
                    status="incomplete",
                    reasons=("final_validation_interrupted",),
                    completed_stages=tuple(
                        stage
                        for stage in completed_stages
                        if stage != "final_validation"
                    ),
                    final_quality_gate="not_run",
                    artifact_path=str(path),
                    execution_mode=execution_mode,
                ),
                completed_stages_to_remove=("final_validation",),
            )
            audit_writer.abort()
            raise

    # 10. 写入 L3→L4 接口文件
    if audit_writer is None:
        output_path = _council_output_path(result, path)
        staged_output_path = _staged_council_output_path(output_path)
        try:
            _write_council_output(result, path, output_path=staged_output_path)
            _promote_staged_output(staged_output_path, output_path)
        except (Exception, asyncio.CancelledError):
            if _is_promoted_staging_output(staged_output_path, output_path):
                output_path.unlink(missing_ok=True)
            staged_output_path.unlink(missing_ok=True)
            failed_record = RunQualityRecord(
                canonical_ticker=ticker,
                run_id=quality_run_id,
                status="incomplete",
                reasons=("final_validation_interrupted",),
                completed_stages=tuple(
                    stage for stage in completed_stages if stage != "final_validation"
                ),
                final_quality_gate="not_run",
                artifact_path=str(path),
                execution_mode=execution_mode,
            )
            replace_quality_record(
                ".",
                failed_record,
                completed_stages_to_remove=("final_validation",),
            )
            raise

    return result


def _council_output_path(result: CouncilResult, debate_path: Path) -> Path:
    from data.lib.identity import canonical_ticker

    canonical = canonical_ticker(result.ticker)
    date_str = debate_path.stem
    if result.run_id:
        return Path("watchlist") / canonical / result.run_id / f"{date_str}.json"
    return Path("watchlist") / f"{date_str}_{canonical}.json"


def _staged_council_output_path(output_path: Path) -> Path:
    relative = output_path.relative_to("watchlist")
    return Path("watchlist") / ".staging" / relative


def _promote_staged_output(staged_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(staged_path, output_path)
    except FileExistsError as exc:
        raise FileExistsError(
            f"refusing to overwrite audited council output: {output_path}"
        ) from exc
    staged_path.unlink()


def _is_promoted_staging_output(staged_path: Path, output_path: Path) -> bool:
    try:
        return staged_path.exists() and output_path.exists() and os.path.samefile(
            staged_path, output_path
        )
    except OSError:
        return False


def _build_council_output(result: CouncilResult, debate_path: Path) -> dict:
    """写入 L3→L4 接口文件（watchlist/{date}_{ticker}.json）.

    Args:
        result: CouncilResult 实例
        debate_path: 辩论记录路径（用于提取日期）
    """
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
        "execution_mode": result.execution_mode,
        "run_id": result.run_id,
        "profile_version": result.profile_version,
        "input_hash": result.input_hash,
        "dossier_snapshot": result.dossier_snapshot,
        "prompt_version": result.prompt_version,
        "model_configuration": result.model_configuration,
        "audit_manifest_path": result.audit_manifest_path,
        "run_quality_status": result.run_quality_status,
        "run_quality_reasons": result.run_quality_reasons,
        "final_quality_gate": result.final_quality_gate,
        "success_cache_eligible": result.success_cache_eligible,
        "quality_record_path": result.quality_record_path,
        "dossier_quality_status": result.dossier_quality_status,
        "dossier_quality_reasons": result.dossier_quality_reasons,
        "dossier_quality_contract": result.dossier_quality_contract,
    }

    # L4 消费方：文件名用 canonical ticker（含交易所后缀 600519.SH），与字段一致
    # g1-canonical-run-identity D5 A+：canonical 化确保无论 result.ticker 是纯数字还是
    # 带后缀，watchlist 文件名都统一为带后缀（与 _debate_path 口径一致，消除空壳/真数据分裂）。
    return output


def _write_council_output(
    result: CouncilResult,
    debate_path: Path,
    *,
    output_path: Path | None = None,
) -> Path:
    output_path = output_path or _council_output_path(result, debate_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "x" if result.run_id else "w"
    with output_path.open(mode, encoding="utf-8") as f:
        json.dump(_build_council_output(result, debate_path), f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    return output_path
