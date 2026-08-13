"""G1 产品 Gate（umbrella 6.1/6.2）：Top 20 派生、用户逐只复核校验与 Gate 判定.

隶属 g1-fast-personal-value-screening umbrella；只服务 6.1/6.2 证据链，
不触碰 7.x closure，不进入 G2/G3，不宣称 G1 capability passed。

设计要点（openspec/changes/g1-top20-style-review/design.md）：
- pinned run：已通过工程 Gate 的固定 run（归档 evidence bundle 提供 identity）。
- derivation：对 pinned bundle 的 input_tickers 以 allow_stale 离线再跑 L1
  （screen_a_shares 确定性计算，不调用 provider/LLM），复现候选排序。
- 绑定校验：profile_version / input_ticker_set_hash / 漏斗统计必须与 pinned 一致，
  任一不一致 → not_evaluable，不得产生 Gate 通过结论。
- 用户复核：每只 Top 20 一条记录（枚举 label + 非空理由）；缺失/重复/非法即阻断。
- Gate：worth_research_count * 10 >= n * 7 → passed；记录合法但不足 → failed；
  身份不一致或记录非法 → not_evaluable。failed/not_evaluable 绝不写成 passed。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data.lib.identity import compute_input_ticker_set_hash

SCHEMA_VERSION_DERIVATION = "g1-top20-derivation.v1"
SCHEMA_VERSION_REVIEW = "g1-top20-user-review.v1"
SCHEMA_VERSION_EVIDENCE = "g1-top20-style-review.v1"

# 用户判断标签枚举（umbrella 要求至少三态：值得/不值得/无法判断）
LABEL_WORTH = "worth_further_research"
LABEL_NOT_WORTH = "not_worth_further_research"
LABEL_UNABLE = "unable_to_judge_insufficient_data"
REVIEW_LABELS = (LABEL_WORTH, LABEL_NOT_WORTH, LABEL_UNABLE)

# pinned bundle 必须包含的身份字段
_PINNED_REQUIRED_FIELDS = ("run_id", "profile_version", "input_ticker_set_hash", "input_tickers")

# 漏斗交叉验证字段（derivation stats vs pinned funnel）
_FUNNEL_CHECK_FIELDS = ("total", "after_hard_gates", "after_factors", "after_heat_filter")

DEFAULT_TOP20_LIMIT = 20
# Gate 阈值：worth 占比 >= 70%（worth*10 >= n*7，精确整数比较）
_GATE_PASS_NUMERATOR = 7
_GATE_PASS_DENOMINATOR = 10


class Top20ValidationError(ValueError):
    """pinned bundle / derivation 绑定 / 用户复核记录不合法（阻断，不静默接受）."""


def load_pinned_run(bundle: dict | str | Path) -> dict:
    """解析并校验 pinned run evidence bundle，提取固定 run 身份.

    Args:
        bundle: 归档 evidence bundle（dict 或 JSON 文件路径）。

    Returns:
        {"run_id", "profile_version", "input_ticker_set_hash", "input_tickers",
         "run_date", "coverage", "funnel", "source_path"}

    Raises:
        Top20ValidationError: 缺身份字段、input_tickers 为空，或 input_tickers
            重算 hash 与声明不一致（bundle 损坏/被改）。
    """
    source_path: str | None = None
    if isinstance(bundle, (str, Path)):
        source_path = str(bundle)
        try:
            bundle = json.loads(Path(bundle).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Top20ValidationError(f"pinned bundle 读取失败: {source_path}: {exc}") from exc
    if not isinstance(bundle, dict):
        raise Top20ValidationError("pinned bundle 必须是 JSON 对象")

    missing = [field for field in _PINNED_REQUIRED_FIELDS if not bundle.get(field)]
    if missing:
        raise Top20ValidationError(f"pinned bundle 缺少身份字段: {missing}")

    tickers = bundle["input_tickers"]
    if not isinstance(tickers, list) or not tickers:
        raise Top20ValidationError("pinned bundle input_tickers 必须是非空列表")

    recomputed = compute_input_ticker_set_hash(tickers)
    declared = bundle["input_ticker_set_hash"]
    if recomputed != declared:
        raise Top20ValidationError(
            f"pinned bundle input_tickers 与声明 hash 不一致: "
            f"recomputed={recomputed} declared={declared}（bundle 可能被改动）"
        )

    return {
        "run_id": bundle["run_id"],
        "profile_version": bundle["profile_version"],
        "input_ticker_set_hash": declared,
        "input_tickers": list(tickers),
        "run_date": bundle.get("run_date"),
        "coverage": bundle.get("coverage"),
        "funnel": dict(bundle.get("funnel") or {}),
        "source_path": source_path,
    }


def derive_top20(
    pinned: dict,
    l1_output: dict,
    limit: int = DEFAULT_TOP20_LIMIT,
    freshness_policy: str = "allow_stale",
) -> dict:
    """从固定 run 的输入派生 Top 20（确定性 L1 再派生）.

    Args:
        pinned: load_pinned_run() 的输出。
        l1_output: screen_a_shares() 的 S5 输出（对 pinned input_tickers 的 allow_stale 再运行）。
        limit: Top N 上限（缺省 20）。
        freshness_policy: 记录到 derivation 身份（derivation 必须离线 allow_stale）。

    Returns:
        derivation 文档。status="derived" 时含 top20 逐只记录；
        status="not_evaluable" 时 top20 为空且 reason 列出全部不一致项。
    """
    reasons: list[str] = []

    derivation_profile = l1_output.get("profile_version")
    if derivation_profile != pinned["profile_version"]:
        reasons.append(
            f"profile_version 不一致: derivation={derivation_profile} pinned={pinned['profile_version']}"
        )

    derivation_hash = l1_output.get("input_ticker_set_hash")
    if derivation_hash != pinned["input_ticker_set_hash"]:
        reasons.append(
            f"input_ticker_set_hash 不一致: derivation={derivation_hash} "
            f"pinned={pinned['input_ticker_set_hash']}"
        )

    stats = l1_output.get("stats") or {}
    pinned_funnel = pinned.get("funnel") or {}
    for field in _FUNNEL_CHECK_FIELDS:
        derivation_value = stats.get(field)
        pinned_value = pinned_funnel.get(field)
        if derivation_value != pinned_value:
            reasons.append(
                f"漏斗漂移 {field}: derivation={derivation_value} pinned={pinned_value}"
            )

    candidates = l1_output.get("candidates") or []
    expected_candidates = pinned_funnel.get("after_heat_filter")
    if expected_candidates is not None and len(candidates) != expected_candidates:
        reasons.append(
            f"候选数量漂移: derivation candidates={len(candidates)} "
            f"pinned after_heat_filter={expected_candidates}"
        )

    derivation_run = {
        "run_id": l1_output.get("run_id"),
        "profile_version": derivation_profile,
        "input_ticker_set_hash": derivation_hash,
        "run_date": l1_output.get("run_date"),
        "derivation_kind": "deterministic_l1_replay",
        "freshness_policy": freshness_policy,
    }
    pinned_run = {
        "run_id": pinned["run_id"],
        "profile_version": pinned["profile_version"],
        "input_ticker_set_hash": pinned["input_ticker_set_hash"],
        "run_date": pinned.get("run_date"),
        "coverage": pinned.get("coverage"),
        "source_path": pinned.get("source_path"),
    }
    funnel_check = {
        "pinned": dict(pinned_funnel),
        "derivation": {field: stats.get(field) for field in _FUNNEL_CHECK_FIELDS},
        "consistent": not any(field in r for r in reasons for field in _FUNNEL_CHECK_FIELDS),
    }

    if reasons:
        return {
            "schema_version": SCHEMA_VERSION_DERIVATION,
            "status": "not_evaluable",
            "reason": reasons,
            "pinned_run": pinned_run,
            "derivation_run": derivation_run,
            "funnel_check": funnel_check,
            "candidate_count": len(candidates),
            "top20": [],
        }

    top20 = []
    for index, candidate in enumerate(candidates[:limit]):
        top20.append({
            "rank": index + 1,
            "ticker": candidate.get("ticker"),
            "adjusted_composite": candidate.get("adjusted_composite"),
            "factor_scores": candidate.get("factor_scores"),
            "anti_trap": candidate.get("anti_trap"),
            "pinned_run_id": pinned["run_id"],
            "profile_version": pinned["profile_version"],
            "input_ticker_set_hash": pinned["input_ticker_set_hash"],
        })

    return {
        "schema_version": SCHEMA_VERSION_DERIVATION,
        "status": "derived",
        "reason": [],
        "pinned_run": pinned_run,
        "derivation_run": derivation_run,
        "funnel_check": funnel_check,
        "candidate_count": len(candidates),
        "top20": top20,
    }


def build_review_template(derivation: dict) -> dict:
    """生成用户复核模板：逐只预填 rank/ticker 与 identity，label/reason 留空.

    label/reason 只能由真实用户填写；MUST NOT 由模型或历史结果自动填充。
    """
    if derivation.get("status") != "derived":
        raise Top20ValidationError(
            f"derivation status={derivation.get('status')}，不可生成复核模板: "
            f"{derivation.get('reason')}"
        )
    reviews = []
    for item in derivation["top20"]:
        reviews.append({
            "rank": item["rank"],
            "ticker": item["ticker"],
            "adjusted_composite": item.get("adjusted_composite"),
            "label": None,
            "reason": "",
        })
    return {
        "schema_version": SCHEMA_VERSION_REVIEW,
        "pinned_run_id": derivation["pinned_run"]["run_id"],
        "derivation_run_id": derivation["derivation_run"]["run_id"],
        "profile_version": derivation["pinned_run"]["profile_version"],
        "input_ticker_set_hash": derivation["pinned_run"]["input_ticker_set_hash"],
        "label_enum": list(REVIEW_LABELS),
        "reviews": reviews,
    }


def validate_user_review(review_doc: dict, derivation: dict) -> list[dict]:
    """严格校验用户复核文档，返回按 rank 排序的合法记录列表.

    Raises:
        Top20ValidationError: 任一违规（缺失/重复/rank-ticker 不匹配/非法 label/
            空理由/身份不一致/仅汇总无逐只记录）。MUST NOT 静默接受。
    """
    if derivation.get("status") != "derived":
        raise Top20ValidationError(
            f"derivation status={derivation.get('status')}，不可校验复核记录"
        )
    if not isinstance(review_doc, dict):
        raise Top20ValidationError("复核文档必须是 JSON 对象")

    identity_checks = (
        ("pinned_run_id", derivation["pinned_run"]["run_id"]),
        ("derivation_run_id", derivation["derivation_run"]["run_id"]),
        ("profile_version", derivation["pinned_run"]["profile_version"]),
        ("input_ticker_set_hash", derivation["pinned_run"]["input_ticker_set_hash"]),
    )
    for field, expected in identity_checks:
        if review_doc.get(field) != expected:
            raise Top20ValidationError(
                f"复核文档 {field} 与 derivation 不一致: "
                f"review={review_doc.get(field)!r} expected={expected!r}"
            )

    reviews = review_doc.get("reviews")
    if not isinstance(reviews, list) or not reviews:
        raise Top20ValidationError(
            "复核文档缺少逐只 reviews 记录；只有汇总比例不可审计，拒绝计算 Gate"
        )

    top20 = derivation["top20"]
    expected_by_rank = {item["rank"]: item["ticker"] for item in top20}

    errors: list[str] = []
    seen_ranks: set[int] = set()
    seen_tickers: set[str] = set()
    records_by_rank: dict[int, dict] = {}

    for index, entry in enumerate(reviews):
        if not isinstance(entry, dict):
            errors.append(f"reviews[{index}] 不是对象")
            continue
        rank = entry.get("rank")
        ticker = entry.get("ticker")
        label = entry.get("label")
        reason = entry.get("reason")

        if rank not in expected_by_rank:
            errors.append(f"reviews[{index}] rank={rank!r} 不在 Top {len(top20)} 范围内")
            continue
        if rank in seen_ranks:
            errors.append(f"rank={rank}（{ticker!r}）重复记录")
        if ticker in seen_tickers:
            errors.append(f"ticker={ticker!r} 重复记录")
        if ticker != expected_by_rank[rank]:
            errors.append(
                f"rank={rank} ticker 不匹配: review={ticker!r} expected={expected_by_rank[rank]!r}"
            )
        if label not in REVIEW_LABELS:
            errors.append(
                f"ticker={ticker!r} label 非法: {label!r}，允许值={list(REVIEW_LABELS)}"
            )
        if not isinstance(reason, str) or not reason.strip():
            errors.append(f"ticker={ticker!r} reason 为空（必须提供逐只理由）")

        seen_ranks.add(rank)
        seen_tickers.add(ticker)
        records_by_rank[rank] = {"rank": rank, "ticker": ticker, "label": label, "reason": reason}

    missing_ranks = sorted(set(expected_by_rank) - set(records_by_rank))
    if missing_ranks:
        missing_tickers = [expected_by_rank[r] for r in missing_ranks]
        errors.append(f"缺少复核记录 rank={missing_ranks} ticker={missing_tickers}")

    if errors:
        raise Top20ValidationError("用户复核记录校验失败: " + "; ".join(errors))

    return [records_by_rank[rank] for rank in sorted(records_by_rank)]


def evaluate_gate(records: list[dict]) -> dict:
    """按逐只记录计算 Gate 统计与 verdict（passed/failed）.

    阈值：worth_research_count * 10 >= n * 7（即 ≥70%；n=20 时 ≥14）。
    """
    total = len(records)
    if total == 0:
        raise Top20ValidationError("无逐只复核记录，无法计算 Gate")
    worth = sum(1 for r in records if r.get("label") == LABEL_WORTH)
    not_worth = sum(1 for r in records if r.get("label") == LABEL_NOT_WORTH)
    unable = sum(1 for r in records if r.get("label") == LABEL_UNABLE)
    passed = worth * _GATE_PASS_DENOMINATOR >= total * _GATE_PASS_NUMERATOR
    return {
        "total_reviewed": total,
        "worth_research_count": worth,
        "not_worth_research_count": not_worth,
        "unable_to_judge_count": unable,
        "worth_ratio": worth / total,
        "threshold": ">=70% (worth_count*10 >= n*7)",
        "gate_verdict": "passed" if passed else "failed",
    }


def finalize_top20(derivation: dict, review_doc: dict | None) -> dict:
    """汇总 derivation 与用户复核，产出 Gate evidence（三态 verdict）.

    - derivation not_evaluable → verdict=not_evaluable（不需要复核文档）。
    - 复核文档非法 → 抛 Top20ValidationError（阻断，不产出 evidence）。
    - 记录合法 → verdict=passed/failed，evidence 保留逐只审计链。

    任何分支都 MUST NOT 输出 capability passed。
    """
    base = {
        "schema_version": SCHEMA_VERSION_EVIDENCE,
        "gate_scope": "g1-fast-personal-value-screening umbrella milestones 6.1/6.2 only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pinned_run": derivation.get("pinned_run"),
        "derivation_run": derivation.get("derivation_run"),
        "funnel_check": derivation.get("funnel_check"),
    }

    if derivation.get("status") != "derived":
        return {
            **base,
            "gate_verdict": "not_evaluable",
            "reason": list(derivation.get("reason") or []) + ["derivation 未绑定 pinned run"],
            "reviews": [],
            "statistics": None,
        }

    records = validate_user_review(review_doc, derivation)
    statistics = evaluate_gate(records)

    top20_context = {item["ticker"]: item for item in derivation["top20"]}
    reviews = []
    for record in records:
        context = top20_context.get(record["ticker"], {})
        reviews.append({
            "rank": record["rank"],
            "ticker": record["ticker"],
            "adjusted_composite": context.get("adjusted_composite"),
            "label": record["label"],
            "reason": record["reason"],
            "pinned_run_id": derivation["pinned_run"]["run_id"],
            "derivation_run_id": derivation["derivation_run"]["run_id"],
            "profile_version": derivation["pinned_run"]["profile_version"],
            "input_ticker_set_hash": derivation["pinned_run"]["input_ticker_set_hash"],
        })

    return {
        **base,
        "gate_verdict": statistics["gate_verdict"],
        "reason": [],
        "reviews": reviews,
        "statistics": statistics,
    }


def save_json(document: dict[str, Any], path: str | Path) -> Path:
    """写 JSON evidence（父目录自动创建，UTF-8，缩进 2）."""
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return out_path
