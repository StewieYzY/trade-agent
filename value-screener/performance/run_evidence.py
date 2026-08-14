"""G1 performance/cost evidence orchestrator.

包裹 screen_a_shares + scout_batch，采集分阶段耗时、关键字段可用率、
L2 成本双口径、未处理异常，输出可复核的 evidence bundle JSON。

不修改 L1/L2 生产逻辑，只做证据采集和 Gate 判定。

review P1/P2 修复记录：
- P1-1 方案 A：不改写 pledge_ratio 值（canonical data-minimum-contract 要求
  「None + status」，MUST NOT 用"视为 0"掩盖）。可用率按 canonical 语义判定：
  pledge_status=record_not_found → availability_status=usable（非 missing）。
- P2-2：_check_cache_warmth 去除死 import，不用有 mkdir 副作用的私有 _path，
  cache_base 参数生效。
- P2-3：warm_cache 仅指 L1 数据缓存预检结果（design D7 口径）；L2 scout cache
  命中单独记录在 cost.cache_hits，不混入 warm_cache。
- P2-1/P2-5：bundle 记录 coverage（partial_market/full_market）、ticker_source
  和 evidence_notes（L2 cache 复用、成本口径等显式标注）。
"""
from __future__ import annotations

import json
import time
import traceback
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from screener.main import screen_a_shares, G1_QUANT_DIMENSIONS
from council.llm import LIGHT_LLM_TIMEOUT_SECONDS
from scout.batch import SCOUT_CONCURRENCY, scout_batch

# G1 排序所需的最小关键字段集合
KEY_FIELDS = ("ticker", "f_score", "adjusted_composite", "pe_ttm", "pb", "pledge_ratio")

# AD-03 基准单价
TOKEN_PRICE_YUAN_PER_1K = 0.001

# Gate 阈值
GATE_MAX_ELAPSED_MINUTES = 15
GATE_MIN_FIELD_AVAILABILITY = 0.95
GATE_MAX_L2_COST_YUAN = 2.0
GATE_MAX_UNHANDLED_EXCEPTIONS = 0

# canonical data-minimum-contract: record_not_found = known-zero，usable（非 missing）
_USABLE_PLEDGE_STATUS = ("record_not_found",)


def _check_cache_warmth(
    tickers: list[str],
    cache_base: str | Path | None = None,
    freshness_policy: str = "require_fresh",
) -> dict:
    """预检本地缓存可用性，并独立统计数据新鲜度."""
    from data.cache.manager import CacheManager

    cm = CacheManager(base_dir=cache_base) if cache_base is not None else CacheManager()
    total = len(tickers) * len(G1_QUANT_DIMENSIONS)
    counts = {
        dim: {
            "fresh": 0,
            "stale": 0,
            "missing": 0,
            "invalid": 0,
            "oldest_age_seconds": None,
            "latest_age_seconds": None,
            "ttl_seconds": cm._ttl(dim),
        }
        for dim in G1_QUANT_DIMENSIONS
    }
    for t in tickers:
        code = CacheManager.normalize_ticker(t)
        for dim in G1_QUANT_DIMENSIONS:
            path = cm.base / code / f"{dim}.json"
            item = counts[dim]
            if not path.exists():
                item["missing"] += 1
                continue
            age = max(0.0, time.time() - path.stat().st_mtime)
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (json.JSONDecodeError, OSError):
                item["invalid"] += 1
                continue
            if not cm.is_valid_payload(dim, payload):
                item["invalid"] += 1
                continue
            freshness = "fresh" if age <= item["ttl_seconds"] else "stale"
            item[freshness] += 1
            if item["oldest_age_seconds"] is None or age > item["oldest_age_seconds"]:
                item["oldest_age_seconds"] = age
            if item["latest_age_seconds"] is None or age < item["latest_age_seconds"]:
                item["latest_age_seconds"] = age
    freshness_totals = {
        key: sum(item[key] for item in counts.values())
        for key in ("fresh", "stale", "missing", "invalid")
    }
    return {
        "cache_warm": sum(freshness_totals[key] for key in ("missing", "invalid")) == 0,
        "data_freshness": {
            "policy": freshness_policy,
            "by_dimension": counts,
            **freshness_totals,
            "total_slots": total,
        },
        "cache_hits": freshness_totals["fresh"] + freshness_totals["stale"],
        "cache_expired": freshness_totals["stale"],
        "cache_missing": freshness_totals["missing"] + freshness_totals["invalid"],
        "total_slots": total,
        "warm_cache": freshness_totals["missing"] + freshness_totals["invalid"] == 0,
    }


def _field_is_available(candidate: dict, field: str) -> bool:
    """单字段可用性判定.

    一般字段：非 None 且非空字符串即可用。
    pledge_ratio 特例（canonical data-minimum-contract「risk.pledge_ratio 缺失三态区分」）：
    值为 None 但 pledge_status=record_not_found 时按 known-zero 记 usable，
    不计 missing；source_failed/invalid_value/无 status 的 None 仍计 missing。
    """
    val = candidate.get(field)
    if val is not None and val != "":
        return True
    if field == "pledge_ratio" and candidate.get("pledge_status") in _USABLE_PLEDGE_STATUS:
        return True
    return False


def _compute_field_availability(candidates: list[dict]) -> dict:
    """独立计算关键字段可用率，不从 stats 派生."""
    total_fields = len(candidates) * len(KEY_FIELDS)
    if total_fields == 0:
        return {"rate": 1.0, "checked_fields": list(KEY_FIELDS), "total_fields": 0, "missing_count": 0}
    missing = 0
    for c in candidates:
        for field in KEY_FIELDS:
            if not _field_is_available(c, field):
                missing += 1
    return {
        "rate": (total_fields - missing) / total_fields,
        "checked_fields": list(KEY_FIELDS),
        "total_fields": total_fields,
        "missing_count": missing,
    }


def _compute_cost(usage_summary: dict) -> dict:
    """双口径成本：实测 token × 单价 + 等效全量调用推算."""
    call_count = usage_summary.get("call_count", 0)
    cache_hits = usage_summary.get("cache_hits", 0)
    total_tokens = usage_summary.get("total_tokens", 0)
    measured = total_tokens * TOKEN_PRICE_YUAN_PER_1K / 1000.0
    # 等效全量：无缓存时的全量调用成本（按本次实测单只平均 token 外推）
    if call_count > 0:
        avg_tokens_per_call = total_tokens / call_count
        equivalent_full = (
            (call_count + cache_hits)
            * avg_tokens_per_call
            * TOKEN_PRICE_YUAN_PER_1K
            / 1000.0
        )
    elif cache_hits > 0:
        # 没有真实调用就没有可用于外推的单只 token 基准，不能伪造 0 元等效成本。
        equivalent_full = None
    else:
        equivalent_full = 0.0
    return {
        "measured_yuan": measured,
        "equivalent_full_yuan": equivalent_full,
        "call_count": call_count,
        "cache_hits": cache_hits,
        "total_tokens": total_tokens,
    }


def _build_funnel(l1_stats: dict, l2_results: list[dict], failure_summary: dict) -> dict:
    """构建完整漏斗 + L2 分布."""
    return {
        "total": l1_stats.get("total", 0),
        "after_hard_gates": l1_stats.get("after_hard_gates", 0),
        "after_factors": l1_stats.get("after_factors", 0),
        "after_heat_filter": l1_stats.get("after_heat_filter", 0),
        "l2_input": len(l2_results),
        "l2_deep_dive": sum(1 for r in l2_results if r.get("verdict") == "deep_dive"),
        "l2_watch": sum(1 for r in l2_results if r.get("verdict") == "watch"),
        "l2_skip": sum(1 for r in l2_results if r.get("verdict") == "skip"),
        "l2_error": sum(1 for r in l2_results if r.get("verdict") == "error"),
        "l2_degraded": failure_summary.get("degraded", 0),
    }


def _judge_gate(
    timing: dict,
    field_availability: dict,
    cost: dict,
    unhandled_count: int,
) -> bool:
    """硬 Gate 只判断字段可用率和未处理异常；耗时/成本仅作观测."""
    availability_ok = field_availability["rate"] >= GATE_MIN_FIELD_AVAILABILITY
    exception_ok = unhandled_count <= GATE_MAX_UNHANDLED_EXCEPTIONS
    return availability_ok and exception_ok


def _l2_execution_gate(funnel: dict, cost: dict, force_l2: bool) -> bool:
    """force-L2 全量错误且零调用时，禁止最终 full-market Gate 通过."""
    return not (
        force_l2
        and funnel.get("l2_input", 0) > 0
        and funnel.get("l2_error", 0) == funnel.get("l2_input", 0)
        and cost.get("call_count", 0) == 0
    )


def _gate_thresholds() -> dict:
    return {
        "min_field_availability": GATE_MIN_FIELD_AVAILABILITY,
        "max_unhandled_exceptions": GATE_MAX_UNHANDLED_EXCEPTIONS,
        "reject_all_l2_errors_when_force_l2": True,
        "reference_max_elapsed_minutes": GATE_MAX_ELAPSED_MINUTES,
        "reference_max_l2_cost_yuan": GATE_MAX_L2_COST_YUAN,
    }


def build_failure_bundle(
    error: BaseException,
    elapsed_seconds: float,
    ticker_count: int,
    coverage: str = "partial_market",
    tickers: list[str] | None = None,
    ticker_source: str = "unspecified",
    freshness_policy: str = "require_fresh",
) -> dict[str, Any]:
    """运行失败时构造失败证据 bundle.

    保留失败证据，不以默认值伪造成功（umbrella「不得用默认值掩盖缺失」同源要求）。
    """
    return {
        "run_date": date.today().isoformat(),
        "mode": "live",
        "schema_version": "g1-full-market-performance-cost.v2",
        "coverage": coverage,
        "input_tickers": list(tickers or []),
        "run_failed": True,
        "failure": {
            "error": str(error),
            "traceback": "".join(traceback.format_exception(error)),
            "elapsed_seconds_before_failure": elapsed_seconds,
        },
        "timing": {"total_elapsed_seconds": elapsed_seconds},
        "observed_metrics": {
            "total_elapsed_seconds": elapsed_seconds,
            "reference_thresholds": {
                "max_elapsed_minutes": GATE_MAX_ELAPSED_MINUTES,
                "max_l2_cost_yuan": GATE_MAX_L2_COST_YUAN,
            },
        },
        "funnel": {},
        "field_availability": {},
        "cost": {},
        "artifact_id": f"failure-{uuid.uuid4().hex[:12]}",
        "exceptions": {"unhandled_count": 1, "error_details": [{"error": str(error)}]},
        "cache_warm": False,
        "data_freshness": {
            "policy": freshness_policy,
            "status": "unknown_before_pipeline_completion",
        },
        "run_config": {
            "ticker_count": ticker_count,
            "ticker_source": ticker_source,
            "freshness_policy": freshness_policy,
        },
        "metrics_gate_passed": False,
        "hard_gate_passed": False,
        "gate_passed": False,
        "gate_thresholds": _gate_thresholds(),
    }


async def run_full_market_evidence(
    tickers: list[str],
    exclude_cyclicals: bool = False,
    force_l2: bool = False,
    coverage: str = "partial_market",
    ticker_source: str = "unspecified",
    freshness_policy: str = "require_fresh",
) -> dict[str, Any]:
    """编排一次 warm-cache L1+L2 运行，采集性能/成本证据.

    Args:
        tickers: ticker 列表（cached subset 或全市场）
        exclude_cyclicals: 是否排除周期股
        force_l2: 是否强制重跑 L2（跳过缓存）
        coverage: "partial_market"（已缓存子集）或 "full_market"（完整可交易集合）
        ticker_source: ticker 列表来源描述（evidence 可复现性，review P2-5）

    Returns:
        evidence bundle dict，含 timing/funnel/field_availability/cost/exceptions/
        run_config/gate_passed/gate_thresholds/coverage/evidence_notes 和 run identity。
    """
    # L1 数据缓存温暖度预检（design D7 口径：warm_cache 仅指 L1 数据缓存）
    cache_status = _check_cache_warmth(tickers, freshness_policy=freshness_policy)

    total_start = time.monotonic()

    # L1 阶段
    l1_start = time.monotonic()
    l1_output = screen_a_shares(
        tickers,
        exclude_cyclicals=exclude_cyclicals,
        freshness_policy=freshness_policy,
    )
    l1_elapsed = time.monotonic() - l1_start

    run_id = l1_output.get("run_id")
    profile_version = l1_output.get("profile_version")
    input_ticker_set_hash = l1_output.get("input_ticker_set_hash")

    candidates = l1_output.get("candidates", [])

    # L2 阶段
    l2_start = time.monotonic()
    run_identity = {
        "run_id": run_id,
        "profile_version": profile_version,
        "input_ticker_set_hash": input_ticker_set_hash,
    } if run_id else None

    l2_results, usage_summary, failure_summary = await scout_batch(
        candidates, force=force_l2, run_identity=run_identity,
        freshness_policy=freshness_policy,
    )
    l2_elapsed = time.monotonic() - l2_start

    total_elapsed = time.monotonic() - total_start

    # 构建证据
    timing = {
        "total_elapsed_seconds": total_elapsed,
        "l1_elapsed_seconds": l1_elapsed,
        "l2_elapsed_seconds": l2_elapsed,
    }
    field_availability = _compute_field_availability(candidates)
    cost = _compute_cost(usage_summary)
    funnel = _build_funnel(l1_output.get("stats", {}), l2_results, failure_summary)
    unhandled_count = failure_summary.get("unhandled_exceptions", 0)

    # evidence_notes：显式标注证据口径（review P2-1/P2-5）
    evidence_notes = []
    if coverage != "full_market":
        evidence_notes.append(
            f"coverage={coverage}: 本次输入 {len(tickers)} 只（ticker_source={ticker_source}），"
            "不是完整可交易 A 股集合；耗时/成本/可用率结论仅对该输入集合成立。"
        )
    if usage_summary.get("cache_hits", 0) > 0:
        equivalent_note = (
            "cost.equivalent_full_yuan 为无缓存等效外推（按本次单只平均 token）。"
            if cost["equivalent_full_yuan"] is not None
            else "本次无真实 LLM 调用，无法计算 cost.equivalent_full_yuan。"
        )
        evidence_notes.append(
            f"L2 实测成本为 scout-cache 复用口径：{usage_summary.get('cache_hits')} 次缓存命中 / "
            f"{usage_summary.get('call_count')} 次真实 LLM 调用；"
            + equivalent_note
        )
    if not cache_status["cache_warm"]:
        evidence_notes.append(
            f"L1 本地缓存不可用（missing={cache_status['data_freshness']['missing']}, "
            f"invalid={cache_status['data_freshness']['invalid']}）。"
        )
    if cache_status["data_freshness"]["stale"]:
        evidence_notes.append(
            f"本次存在 {cache_status['data_freshness']['stale']} 个 stale 数据槽位；"
            f"freshness_policy={freshness_policy}。"
        )

    hard_gate_passed = _judge_gate(
        timing,
        field_availability,
        cost,
        unhandled_count,
    )
    l2_execution_passed = _l2_execution_gate(funnel, cost, force_l2)
    observed_metrics = {
        "total_elapsed_seconds": timing["total_elapsed_seconds"],
        "l1_elapsed_seconds": timing["l1_elapsed_seconds"],
        "l2_elapsed_seconds": timing["l2_elapsed_seconds"],
        "l2_cost": cost,
        "reference_thresholds": {
            "max_elapsed_minutes": GATE_MAX_ELAPSED_MINUTES,
            "max_l2_cost_yuan": GATE_MAX_L2_COST_YUAN,
        },
    }

    bundle = {
        "schema_version": "g1-full-market-performance-cost.v2",
        "run_id": run_id,
        "profile_version": profile_version,
        "input_ticker_set_hash": input_ticker_set_hash,
        "input_tickers": list(tickers),
        "run_date": l1_output.get("run_date", date.today().isoformat()),
        "cache_warm": cache_status["cache_warm"],
        "data_freshness": cache_status["data_freshness"],
        "warm_cache": cache_status["cache_warm"],
        "cache_status": cache_status,
        "coverage": coverage,
        "mode": "live",
        "timing": timing,
        # G1 6.1/6.2：归档 heat-filter 后有序候选（与 L2 输入同源），
        # 供 Top 20 派生离线消费；8-12 run 只存聚合指标导致候选排序不可复现。
        "l1_candidates": candidates,
        "funnel": funnel,
        "field_availability": field_availability,
        "cost": cost,
        "exceptions": {
            "unhandled_count": unhandled_count,
            "error_details": failure_summary.get("errors", []),
        },
        "observed_metrics": observed_metrics,
        "run_config": {
            "exclude_cyclicals": exclude_cyclicals,
            "force_l2": force_l2,
            "freshness_policy": freshness_policy,
            "semaphore_concurrency": SCOUT_CONCURRENCY,
            "l2_timeout_seconds": LIGHT_LLM_TIMEOUT_SECONDS,
            "ticker_count": len(tickers),
            "ticker_source": ticker_source,
        },
        "gate_thresholds": _gate_thresholds(),
        "hard_gate_passed": hard_gate_passed,
        "metrics_gate_passed": hard_gate_passed,
        "l2_execution_passed": l2_execution_passed,
        "gate_passed": hard_gate_passed and l2_execution_passed and coverage == "full_market",
        "evidence_notes": evidence_notes,
    }
    return bundle


def save_evidence_bundle(bundle: dict[str, Any], output_dir: str | Path = "data/evidence") -> Path:
    """保存 evidence bundle 到 JSON 文件.

    Returns:
        写入的文件路径。
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = bundle.get("run_id")
    run_date = bundle.get("run_date", date.today().isoformat())
    artifact_id = bundle.get("artifact_id")
    suffix = run_id[:8] if run_id else artifact_id or f"artifact-{time.time_ns()}"
    filename = f"{run_date}_{suffix}.json"
    out_path = out_dir / filename
    out_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return out_path
