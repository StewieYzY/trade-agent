"""watchlist 聚合 — L1/L2/L3 三路产出 → watchlist/{date}.json."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from data.cache.manager import CacheManager
from data.fetchers.valuation import ValuationFetcher
from scout.quality import ScoutCache


def _compute_stage(l2_verdict: str | None, l3_verdict: str | None) -> str:
    """计算 candidate 的 stage 字段.

    规则（design.md 决策 2）：
    - 有 L3 verdict（包括 "unknown"）→ l3
    - L2 deep_dive → l2
    - L2 pass/reject 或无 L2 → l1

    注意：L3 verdict="unknown" 表示 L3 运行过但 verdict 为空（如 null），
    仍标记为 l3 以区分"运行过但失败"和"未运行"。
    """
    if l3_verdict is not None:  # 包括 "unknown"
        return "l3"
    if l2_verdict == "deep_dive":
        return "l2"
    return "l1"


def _read_l1_output(l1_output_file: str | None) -> dict[str, Any]:
    """读取 L1 产出文件，校验存在性和时效性."""
    if not l1_output_file:
        # 尝试从默认位置读取
        default_paths = [
            Path("output/l1_screening.json"),
            Path("l1_screening.json"),
        ]
        for p in default_paths:
            if p.exists():
                l1_output_file = str(p)
                break
        else:
            raise FileNotFoundError(
                "未找到 L1 产出文件，请指定 --l1-file 或先运行 L1 筛选"
            )

    p = Path(l1_output_file)
    if not p.exists():
        raise FileNotFoundError(f"L1 产出文件不存在：{l1_output_file}")

    # 检查时效性（>7 天警告）
    mtime = datetime.fromtimestamp(p.stat().st_mtime).date()
    age_days = (date.today() - mtime).days
    if age_days > 7:
        print(f"⚠️  L1 产出文件已 {age_days} 天未更新，建议重新运行 L1 筛选")

    with p.open(encoding="utf-8") as f:
        return json.load(f)


def _supplement_pe_percentile(
    candidates: list[dict[str, Any]],
    valuation_fetcher: ValuationFetcher | None = None,
    cache_manager: CacheManager | None = None,
) -> list[dict[str, Any]]:
    """对 stage >= l2 的 candidate 补充 pe_percentile_5y 字段.

    规则：
    - stage=l1 的 candidate：pe_percentile_5y=null
    - stage>=l2 的 candidate：先查 CacheManager（dim=valuation），命中直接用；
      miss 则调用 ValuationFetcher.fetch_with_fallback() 并写回缓存
    - fetch 失败：pe_percentile_5y=null，不阻断聚合

    L1 刚跑过时 CacheManager 已有 valuation 缓存，命中率高，实际网络请求少。
    """
    if valuation_fetcher is None:
        valuation_fetcher = ValuationFetcher()
    if cache_manager is None:
        cache_manager = CacheManager()

    for c in candidates:
        stage = c.get("stage", "l1")
        if stage == "l1":
            c["pe_percentile_5y"] = None
            continue

        ticker = c["ticker"]

        # 先查缓存
        cached = cache_manager.get(ticker, "valuation")
        if cached and "pe_percentile_5y" in cached:
            c["pe_percentile_5y"] = cached["pe_percentile_5y"]
            continue

        # 缓存未命中，走网络
        try:
            valuation_data = valuation_fetcher.fetch_with_fallback(ticker)
            if valuation_data and not valuation_data.get("__error__") and "pe_percentile_5y" in valuation_data:
                c["pe_percentile_5y"] = valuation_data["pe_percentile_5y"]
                # 写回缓存供后续复用
                cache_manager.set(ticker, "valuation", valuation_data)
            else:
                c["pe_percentile_5y"] = None
        except (ConnectionError, TimeoutError, OSError) as e:
            print(f"⚠️  {ticker} pe_percentile_5y 补充失败：{e}")
            c["pe_percentile_5y"] = None

    return candidates


def _read_l2_cache(ticker: str, scout_cache: ScoutCache) -> dict[str, Any] | None:
    """读取 ScoutCache 中的 L2 verdict（接受过期缓存）."""
    # 尝试最近 7 天的缓存
    for days_back in range(7):
        d = date.today() - timedelta(days=days_back)
        date_str = d.isoformat()
        cached = scout_cache.get(ticker, date_str)
        if cached:
            return {
                "l2_verdict": cached.get("verdict"),
                "l2_confidence": cached.get("confidence"),
            }
    return None


def _valid_clean_dossier_quality_contract_impl(
    contract: Any,
    *,
    expected_dossier_hash: str | None = None,
    expected_audit_input_hash: str | None = None,
    expected_audit_contract: dict | None = None,
    expected_audit_dossier: dict | None = None,
) -> bool:
    """L4 只接受带完整统计 proof 的 clean dossier 状态."""
    if not isinstance(contract, dict):
        return False
    from council.fact_grounding import (
        FACT_CONTRACT_SCHEMA_VERSION,
        DEGRADATION_STATUSES,
        FRESHNESS,
        ROLES,
        SEVERITIES,
        _parse_period_end,
        _parse_time,
        _time_basis_valid,
    )

    required = {
        "schema_version",
        "ticker",
        "dossier_sha256",
        "retrieved_at",
        "facts",
        "role_status",
        "total_fact_count",
        "traceable_fact_count",
        "traceable_ratio",
        "high_severity_fact_count",
        "high_severity_untraceable_count",
        "high_severity_invalid_count",
        "high_severity_invalid_reasons",
        "stale_fact_count",
        "degraded_fact_count",
        "failed",
        "clean",
    }
    if not required.issubset(contract):
        return False
    if contract.get("schema_version") != FACT_CONTRACT_SCHEMA_VERSION:
        return False
    if (
        not isinstance(contract.get("dossier_sha256"), str)
        or expected_dossier_hash is None
        or contract.get("dossier_sha256") != expected_dossier_hash
        or expected_audit_input_hash is None
        or expected_audit_input_hash != expected_dossier_hash
        or not isinstance(expected_audit_contract, dict)
        or contract != expected_audit_contract
        or not isinstance(expected_audit_dossier, dict)
    ):
        return False
    from council.fact_grounding import build_fact_contract

    recomputed = build_fact_contract(
        expected_audit_dossier,
        ticker=contract.get("ticker"),
        retrieved_at=contract.get("retrieved_at"),
        now=_parse_time(contract.get("retrieved_at")),
        fail_closed=False,
    )
    if recomputed != contract:
        return False
    if not isinstance(contract.get("retrieved_at"), str) or _parse_time(
        contract.get("retrieved_at")
    ) is None:
        return False
    facts = contract.get("facts")
    role_status = contract.get("role_status")
    if not isinstance(facts, list) or not isinstance(role_status, list):
        return False
    if (
        len(role_status) != len(ROLES)
        or any(
            not isinstance(item, dict)
            or item.get("role") not in ROLES
            or item.get("degradation_status") not in DEGRADATION_STATUSES
            for item in role_status
        )
        or {item.get("role") for item in role_status} != set(ROLES)
    ):
        return False
    fact_required = {
        "role",
        "fact_key",
        "label",
        "value",
        "severity",
        "source",
        "report_period",
        "as_of",
        "published_at",
        "retrieved_at",
        "freshness",
        "degradation_status",
        "traceable",
        "reason",
    }
    if any(
        not isinstance(fact, dict) or not fact_required.issubset(fact)
        for fact in facts
    ):
        return False
    for fact in facts:
        if (
            fact.get("role") not in ROLES
            or fact.get("severity") not in SEVERITIES
            or fact.get("freshness") not in FRESHNESS
            or fact.get("degradation_status") not in DEGRADATION_STATUSES
            or not isinstance(fact.get("retrieved_at"), str)
            or _parse_time(fact.get("retrieved_at")) is None
        ):
            return False
        for field, parser in (
            ("report_period", _parse_period_end),
            ("as_of", _parse_time),
            ("published_at", _parse_time),
        ):
            raw = fact.get(field)
            if raw is not None and parser(raw) is None:
                return False
    if contract.get("total_fact_count") != len(facts):
        return False
    traceable_count = sum(1 for fact in facts if fact.get("traceable") is True)
    if contract.get("traceable_fact_count") != traceable_count:
        return False
    expected_ratio = traceable_count / len(facts) if facts else 0.0
    if not math.isclose(
        float(contract.get("traceable_ratio", -1)),
        expected_ratio,
        rel_tol=1e-9,
        abs_tol=1e-9,
    ):
        return False
    for fact in facts:
        expected_traceable = bool(fact.get("source")) and _time_basis_valid(
            fact.get("report_period"),
            fact.get("as_of"),
        )
        if fact.get("traceable") is not expected_traceable:
            return False
    high_facts = [fact for fact in facts if fact.get("severity") == "high"]
    if contract.get("high_severity_fact_count") != len(high_facts):
        return False
    if contract.get("high_severity_untraceable_count") != sum(
        1 for fact in high_facts if fact.get("traceable") is not True
    ):
        return False
    if contract.get("stale_fact_count") != sum(
        1 for fact in facts if fact.get("freshness") == "stale"
    ):
        return False
    if contract.get("degraded_fact_count") != sum(
        1 for fact in facts if fact.get("degradation_status") != "clean"
    ):
        return False
    if contract.get("clean") is not True or contract.get("failed") is not False:
        return False
    return (
        contract.get("high_severity_untraceable_count") == 0
        and contract.get("traceable_ratio", 0.0) >= 0.95
        and contract.get("total_fact_count", 0) > 0
        and all(
            item.get("degradation_status") == "clean"
            for item in role_status
        )
    )


def _valid_clean_dossier_quality_contract(
    contract: Any,
    *,
    expected_dossier_hash: str | None = None,
    expected_audit_input_hash: str | None = None,
    expected_audit_contract: dict | None = None,
    expected_audit_dossier: dict | None = None,
) -> bool:
    try:
        return _valid_clean_dossier_quality_contract_impl(
            contract,
            expected_dossier_hash=expected_dossier_hash,
            expected_audit_input_hash=expected_audit_input_hash,
            expected_audit_contract=expected_audit_contract,
            expected_audit_dossier=expected_audit_dossier,
        )
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError):
        return False


def _read_audit_proof(
    manifest_path: Any,
    *,
    expected_ticker: str | None = None,
    expected_run_id: str | None = None,
) -> tuple[str | None, dict | None, dict | None]:
    if not isinstance(manifest_path, str) or not manifest_path:
        return None, None, None
    try:
        from data.lib.audit_chain import verify_audit_chain

        path = Path(manifest_path)
        if path.name != "manifest.json":
            return None, None, None
        manifest = verify_audit_chain(path.parent)
        identity = manifest.get("identity")
        if not isinstance(identity, dict):
            return None, None, None
        if (
            expected_ticker is not None
            and identity.get("canonical_ticker") != expected_ticker
        ):
            return None, None, None
        if expected_run_id is not None and identity.get("run_id") != expected_run_id:
            return None, None, None
        input_hash = identity.get("input_hash")
        dossier_artifact = json.loads(
            (path.parent / "01-dossier.json").read_text(encoding="utf-8")
        )
        payload = dossier_artifact.get("payload")
        contract = payload.get("fact_contract") if isinstance(payload, dict) else None
        dossier = payload.get("dossier") if isinstance(payload, dict) else None
        return (
            input_hash,
            contract if isinstance(contract, dict) else None,
            dossier if isinstance(dossier, dict) else None,
        )
    except (OSError, TypeError, ValueError):
        return None, None, None


def _read_l3_output(ticker: str, run_date: str, watchlist_dir: Path) -> dict[str, Any] | None:
    """读取 L3 per-ticker JSON 文件（g1-canonical-run-identity D5 A+: canonical 双向回退）.

    优先读取新的 run-scoped Council 输出：
    `watchlist/{canonical}/{run_id}/{date}.json`。同一 ticker/date 有多次运行时，
    按文件修改时间选择最新 run，再回退到旧扁平文件并优先内容完整的真数据。

    caller 传 canonical ticker（600009.SH）时优先命中带后缀真数据；
    caller 传纯数字 ticker（600009）时回退也试带后缀形式。
    消除 2026-07-13_600009.json（空壳）/2026-07-13_600009.SH.json（真数据）分裂时只读空壳的 bug。
    """
    from data.lib.identity import canonical_ticker, canonical_code
    try:
        canonical = canonical_ticker(ticker)
        code = canonical_code(ticker)
    except ValueError:
        # 非法 ticker 退回旧行为
        canonical, code = ticker, ticker.split(".")[0]

    patterns = [
        f"{run_date}_{canonical}.json",            # 带后缀（真数据优先）
        f"{run_date}_{code}.json",                 # 纯数字（可能空壳，回退）
        f"{run_date}_{ticker.replace('.', '_')}.json",  # 旧 replace 形式
    ]

    def extract_l3_data(
        l3_data: dict[str, Any],
        *,
        source_run_id: str | None = None,
    ) -> dict[str, Any]:
        from data.lib.quality_status import (
            is_quality_artifact_bound,
            is_success_cache_eligible,
            quality_record_path as build_quality_record_path,
            read_quality_record,
        )

        payload_ticker = l3_data.get("ticker")
        payload_run_id = l3_data.get("run_id")
        payload_execution_mode = l3_data.get("execution_mode")
        expected_run_id = source_run_id or payload_run_id
        expected_record_suffix = (
            f"quality_status/{canonical}/{expected_run_id}/record.json"
            if expected_run_id
            else None
        )
        quality_record_path = l3_data.get("quality_record_path")
        quality_proof_valid = (
            payload_ticker == canonical
            and payload_run_id == expected_run_id
            and isinstance(quality_record_path, str)
            and expected_record_suffix is not None
            and quality_record_path.replace("\\", "/").endswith(
                expected_record_suffix
            )
        )
        quality_record = None
        if quality_proof_valid:
            quality_root = watchlist_dir.parent
            expected_quality_path = build_quality_record_path(
                quality_root,
                canonical,
                expected_run_id,
            ).resolve()
            try:
                quality_path = Path(quality_record_path)
                if not quality_path.is_absolute():
                    quality_path = quality_root / quality_path
                quality_proof_valid = (
                    quality_path.resolve() == expected_quality_path
                )
                if quality_proof_valid:
                    quality_record = read_quality_record(
                        quality_root,
                        canonical,
                        expected_run_id,
                    )
                    quality_proof_valid = quality_record is not None
                    if quality_record is not None and quality_record.artifact_path:
                        quality_proof_valid = is_quality_artifact_bound(
                            quality_root,
                            quality_record,
                            expected_date=run_date,
                        )
                    if (
                        quality_record is not None
                        and payload_execution_mode is not None
                        and payload_execution_mode != quality_record.execution_mode
                    ):
                        quality_proof_valid = False
                    if (
                        quality_record is not None
                        and quality_record.status == "complete"
                        and payload_execution_mode != quality_record.execution_mode
                    ):
                        quality_proof_valid = False
            except (OSError, TypeError, ValueError):
                quality_proof_valid = False

        run_quality_status = l3_data.get("run_quality_status")
        run_quality_reasons = l3_data.get("run_quality_reasons")
        final_quality_gate = l3_data.get("final_quality_gate")
        success_cache_eligible = l3_data.get("success_cache_eligible")
        if quality_record is not None:
            run_quality_status = quality_record.status
            run_quality_reasons = list(quality_record.reasons)
            final_quality_gate = quality_record.final_quality_gate
            success_cache_eligible = is_success_cache_eligible(quality_record)
        if not quality_proof_valid:
            success_cache_eligible = False
            if run_quality_status == "complete":
                run_quality_status = "incomplete"
                if not isinstance(run_quality_reasons, list):
                    run_quality_reasons = []
                if "quality_record_proof_invalid" not in run_quality_reasons:
                    run_quality_reasons.append("quality_record_proof_invalid")
        dossier_quality_status = l3_data.get("dossier_quality_status", "degraded")
        dossier_quality_reasons = l3_data.get(
            "dossier_quality_reasons",
            ["legacy dossier quality unknown"],
        )
        dossier_quality_contract = l3_data.get("dossier_quality_contract")
        if dossier_quality_status not in {"clean", "degraded", "failed"}:
            dossier_quality_status = "degraded"
            dossier_quality_reasons = ["invalid dossier quality status"]
            dossier_quality_contract = None
        elif not isinstance(dossier_quality_reasons, list) or not all(
            isinstance(reason, str) for reason in dossier_quality_reasons
        ):
            dossier_quality_status = "degraded"
            dossier_quality_reasons = ["invalid dossier quality reasons"]
            dossier_quality_contract = None
        if dossier_quality_contract is not None and not isinstance(
            dossier_quality_contract, dict
        ):
            dossier_quality_contract = None
        input_hash = l3_data.get("input_hash")
        audit_manifest_path = l3_data.get("audit_manifest_path")
        audit_input_hash, audit_contract, audit_dossier = _read_audit_proof(
            audit_manifest_path,
            expected_ticker=canonical,
            expected_run_id=payload_run_id,
        )
        if dossier_quality_status == "clean" and not _valid_clean_dossier_quality_contract(
            dossier_quality_contract,
            expected_dossier_hash=input_hash,
            expected_audit_input_hash=audit_input_hash,
            expected_audit_contract=audit_contract,
            expected_audit_dossier=audit_dossier,
        ):
            dossier_quality_status = "degraded"
            dossier_quality_reasons = (
                list(dossier_quality_reasons)
                if isinstance(dossier_quality_reasons, list)
                else ["invalid dossier quality reasons"]
            )
            dossier_quality_reasons.append("clean dossier quality proof missing or invalid")
        return {
            "l3_verdict": l3_data.get("final_verdict", "unknown") or "unknown",
            "l3_conviction": l3_data.get("conviction"),
            "key_variables": l3_data.get("key_variables") or None,
            "consensus_summary": l3_data.get("consensus_summary"),
            "dissent_points": l3_data.get("dissent_points"),
            "pending_verification": l3_data.get("pending_verification"),
            "run_quality_status": run_quality_status,
            "run_quality_reasons": run_quality_reasons,
            "final_quality_gate": final_quality_gate,
            "success_cache_eligible": success_cache_eligible,
            "quality_record_path": quality_record_path,
            "audit_manifest_path": audit_manifest_path,
            "audit_input_hash": audit_input_hash,
            "audit_quality_contract": audit_contract,
            "audit_dossier": audit_dossier,
            "l3_run_id": l3_data.get("run_id"),
            "input_hash": input_hash,
            "dossier_quality_status": dossier_quality_status,
            "dossier_quality_reasons": dossier_quality_reasons,
            "dossier_quality_contract": dossier_quality_contract,
            "_quality_proof_valid": quality_proof_valid,
        }

    run_scoped_paths: list[tuple[int, str, Path]] = []
    for candidate in (watchlist_dir / canonical).glob(f"*/{run_date}.json"):
        try:
            mtime_ns = candidate.stat().st_mtime_ns
        except OSError:
            continue
        run_scoped_paths.append((mtime_ns, candidate.parent.name, candidate))
    run_scoped_paths.sort(
        reverse=True,
    )
    for _, _, path in run_scoped_paths:
        try:
            with path.open(encoding="utf-8") as handle:
                l3_data = json.load(handle)
                if l3_data.get("date") != run_date:
                    continue
                return extract_l3_data(l3_data, source_run_id=path.parent.name)
        except (json.JSONDecodeError, OSError):
            continue

    # 收集旧扁平格式命中的文件，优先返回内容完整的（非空壳）
    candidates: list[dict[str, Any]] = []
    for pattern in patterns:
        p = watchlist_dir / pattern
        if p.exists():
            try:
                with p.open(encoding="utf-8") as f:
                    l3_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            candidates.append(extract_l3_data(l3_data))

    if not candidates:
        return None
    # 优先返回内容完整的（conviction 非 null 或 consensus_summary 非 null 即真数据，
    # 非空壳）。全空壳时返回第一个。
    for c in candidates:
        if c.get("l3_conviction") is not None or c.get("consensus_summary") is not None:
            return c
    return candidates[0]


def _check_l3_incomplete(l3_data: dict[str, Any] | None) -> bool:
    """L3 健康检查：判断产出是否不完整.

    规则：L3 文件存在但 conviction/consensus_summary/dissent_points/pending_verification
    全部为 null → l3_incomplete=true
    """
    if not l3_data:
        return False

    if (
        l3_data.get("run_quality_status") != "complete"
        or l3_data.get("final_quality_gate") != "passed"
        or l3_data.get("success_cache_eligible") is not True
        or l3_data.get("_quality_proof_valid") is not True
        or (
            "dossier_quality_status" in l3_data
            and l3_data.get("dossier_quality_status") != "clean"
        )
        or (
            l3_data.get("dossier_quality_status") == "clean"
            and not _valid_clean_dossier_quality_contract(
                l3_data.get("dossier_quality_contract"),
                expected_dossier_hash=l3_data.get("input_hash"),
                expected_audit_input_hash=l3_data.get("audit_input_hash"),
                expected_audit_contract=l3_data.get("audit_quality_contract"),
                expected_audit_dossier=l3_data.get("audit_dossier"),
            )
        )
    ):
        return True

    null_fields = [
        l3_data.get("l3_conviction") is None,
        l3_data.get("consensus_summary") is None,
        l3_data.get("dissent_points") is None,
        l3_data.get("pending_verification") is None,
    ]
    return all(null_fields)


def aggregate_watchlist(
    run_date: str,
    l1_output_file: str | None = None,
    scout_cache: ScoutCache | None = None,
    watchlist_dir: str | Path = "watchlist",
) -> dict[str, Any]:
    """聚合 L1/L2/L3 三路产出为 watchlist/{date}.json.

    Args:
        run_date: 运行日期（YYYY-MM-DD）
        l1_output_file: L1 产出文件路径（可选，缺省从默认位置读取）
        scout_cache: ScoutCache 实例（可选，缺省创建新实例）
        watchlist_dir: watchlist 输出目录（默认 watchlist/）

    Returns:
        watchlist JSON 结构（符合 §7 子集 + L2/L3 扩展字段）

    Raises:
        FileNotFoundError: L1 产出文件不存在
    """
    if scout_cache is None:
        scout_cache = ScoutCache()

    watchlist_dir = Path(watchlist_dir)
    watchlist_dir.mkdir(parents=True, exist_ok=True)

    # 1. 读取 L1 产出
    l1_data = _read_l1_output(l1_output_file)
    l1_candidates = l1_data.get("candidates", [])

    # 2. 聚合每个 candidate
    candidates = []
    for l1_cand in l1_candidates:
        ticker = l1_cand["ticker"]

        # 读取 L2 缓存
        l2_data = _read_l2_cache(ticker, scout_cache)
        l2_verdict = l2_data["l2_verdict"] if l2_data else None
        l2_confidence = l2_data["l2_confidence"] if l2_data else None

        # 读取 L3 产出
        l3_data = _read_l3_output(ticker, run_date, watchlist_dir)
        l3_verdict = l3_data["l3_verdict"] if l3_data else None
        l3_conviction = l3_data["l3_conviction"] if l3_data else None
        key_variables = l3_data["key_variables"] if l3_data else None

        # 计算 stage
        stage = _compute_stage(l2_verdict, l3_verdict)

        # 构造 candidate 记录
        candidate = {
            "ticker": ticker,
            "name": l1_cand.get("name", ""),
            "stage": stage,
            "l1_score": l1_cand.get("adjusted_composite"),
            "f_score": l1_cand.get("f_score"),
            "pe_ttm": l1_cand.get("pe_ttm"),
            "pe_percentile_5y": None,  # 后续补充
            "pb": l1_cand.get("pb"),
            "pledge_ratio": l1_cand.get("pledge_ratio"),
            "l2_verdict": l2_verdict,
            "l2_confidence": l2_confidence,
            "l3_verdict": l3_verdict,
            "l3_conviction": l3_conviction,
            "key_variables": key_variables,
            "run_quality_status": (
                l3_data.get("run_quality_status") if l3_data else None
            ),
            "run_quality_reasons": (
                l3_data.get("run_quality_reasons") if l3_data else None
            ),
            "final_quality_gate": (
                l3_data.get("final_quality_gate") if l3_data else None
            ),
            "success_cache_eligible": (
                l3_data.get("success_cache_eligible") if l3_data else None
            ),
            "quality_record_path": (
                l3_data.get("quality_record_path") if l3_data else None
            ),
            "l3_run_id": l3_data.get("l3_run_id") if l3_data else None,
            "dossier_quality_status": (
                l3_data.get("dossier_quality_status")
                if l3_data
                else None
            ),
            "dossier_quality_reasons": (
                l3_data.get("dossier_quality_reasons")
                if l3_data
                else None
            ),
            "dossier_quality_contract": (
                l3_data.get("dossier_quality_contract")
                if l3_data
                else None
            ),
            "input_hash": l3_data.get("input_hash") if l3_data else None,
            "last_updated": run_date,
        }

        # L3 健康检查
        if l3_data and _check_l3_incomplete(l3_data):
            candidate["l3_incomplete"] = True

        candidates.append(candidate)

    # 3. 补充 pe_percentile_5y（仅对 stage >= l2）
    candidates = _supplement_pe_percentile(candidates)

    # 4. 构造 watchlist JSON
    # g1-canonical-run-identity D6: 顶层带 run_id（从 L1 文件继承），output_file 改 run-scoped
    # {date}_{run_id[:8]}.json（同日多次运行不同 run_id 不互相覆盖）。旧 L1 无 run_id 时
    # fallback {date}.json（向后兼容）。
    run_id = l1_data.get("run_id")
    profile_version = l1_data.get("profile_version")
    input_ticker_set_hash = l1_data.get("input_ticker_set_hash")
    watchlist = {
        # g1-canonical-run-identity-repair D3: generated_at 带时区 ISO 8601（+08:00 A 股本地），
        # 供 get_latest/previous_watchlist 按真实生成时间排序（非 UUID 字典序）。
        # 用固定偏移而非系统本地时区，跨机器一致。
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "run_id": run_id,  # 从 L1 继承（可能 None，旧 L1）
        "profile_version": profile_version,
        "input_ticker_set_hash": input_ticker_set_hash,
        "l1_candidates": len(candidates),
        "l2_shortlist": sum(1 for c in candidates if c["stage"] in ("l2", "l3")),
        "candidates": candidates,
    }

    # 5. 写入文件（run-scoped 命名，D6：同日不同 run_id 不覆盖）
    if run_id:
        output_file = watchlist_dir / f"{run_date}_{run_id[:8]}.json"
    else:
        output_file = watchlist_dir / f"{run_date}.json"  # 旧 L1 无 run_id fallback
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(watchlist, f, ensure_ascii=False, indent=2)

    print(f"✓ watchlist 聚合完成：{output_file}")
    print(f"  - L1 candidates: {watchlist['l1_candidates']}")
    print(f"  - L2 shortlist: {watchlist['l2_shortlist']}")

    return watchlist
