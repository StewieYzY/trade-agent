"""G2 dossier 角色事实的字段级来源追溯与质量契约.

这是 dossier 事实证据的纯 contract 层：
- 从 ``main_business`` / ``peers`` / ``research`` / ``capex_proxy`` 提取关键事实；
- 为每个事实绑定 source、report_period、published_at、retrieved_at、freshness 和
  degradation_status；
- 对高严重度事实执行 fail-closed 校验，并输出可复核追溯率统计。

它不修改 raw role payload，不修改 prompt/debate/audit chain 主契约，不调用任何
provider 或 LLM。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from data.lib.identity import canonical_code

FACT_CONTRACT_SCHEMA_VERSION = "g2-dossier-fact-contract-v1"
DERIVED_DOSSIER_KEYS = frozenset(
    {"fact_contract", "quality_status", "quality_reasons"}
)

ROLES = ("core_snapshot", "main_business", "peers", "research", "capex_proxy")
SEVERITIES = ("high", "medium", "low")
FRESHNESS = ("fresh", "stale", "unknown")
DEGRADATION_STATUSES = ("clean", "degraded", "unavailable")

SOURCE_BY_ROLE = {
    "main_business": "eastmoney.stock_zygc_em",
    "main_business_fallback": "ths.stock_zyjs_ths",
    "peers": "eastmoney.stock_board_industry_cons_em",
    "research": "eastmoney.stock_research_report_em",
}

CORE_NUMERIC_FACTS = (
    "market_cap",
    "pe_ttm",
    "pb",
    "pe_percentile_5y",
    "roe_3y",
    "net_margin",
    "debt_ratio",
    "goodwill_ratio",
    "operating_cashflow",
    "net_profit",
    "revenue_growth",
    "pledge_ratio",
    "price_change_60d",
    "turnover_avg_percentile_60d",
    "f_score",
)


class FactContractError(ValueError):
    """事实契约违反 fail-closed 规则。"""


def dossier_without_quality_sidecar(dossier: dict[str, Any]) -> dict[str, Any]:
    """返回用于 audit identity 的 raw dossier，不把派生质量 sidecar 混入 hash."""
    return {
        key: value
        for key, value in dossier.items()
        if key not in DERIVED_DOSSIER_KEYS
    }


def _parse_period_end(value: Any) -> datetime | None:
    """把 report_period 归一到周期结束时刻；不合法返回 None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        pass
    if re.fullmatch(r"\d{4}", text):
        return datetime(int(text), 12, 31, tzinfo=timezone.utc)
    match = re.fullmatch(r"(\d{4})-(\d{2})", text)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            return None
        if month == 12:
            return datetime(year, 12, 31, tzinfo=timezone.utc)
        return datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(seconds=1)
    return None


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def _freshness(
    report_period: str | None,
    published_at: str | None,
    as_of: str | None,
    retrieved_at: str | None,
    now: datetime,
    stale_after_days: int,
) -> str:
    values = (
        (report_period, _parse_period_end(report_period)),
        (as_of, _parse_time(as_of)),
    )
    if any(raw is not None and parsed is None for raw, parsed in values):
        return "unknown"
    # D5 uses report_period/as_of as the fact time bases. published_at is
    # retained as provenance metadata, but must not make fresh evidence stale.
    bases = [parsed for _, parsed in values if parsed is not None]
    if not bases:
        retrieved_basis = _parse_time(retrieved_at)
        if retrieved_basis is not None:
            bases = [retrieved_basis]
    if not bases:
        return "unknown"
    ages = [(now - basis).total_seconds() / 86_400 for basis in bases]
    return "stale" if any(age > stale_after_days for age in ages) else "fresh"


def _is_error_data(data: Any) -> bool:
    return isinstance(data, dict) and data.get("__error__") is True


@dataclass(frozen=True)
class FactEvidence:
    """一条 dossier 关键事实及其字段级证据元数据."""

    role: str
    fact_key: str
    label: str
    value: Any
    severity: str
    source: str | None
    report_period: str | None
    as_of: str | None
    published_at: str | None
    retrieved_at: str | None
    freshness: str
    degradation_status: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise FactContractError(f"unknown fact role: {self.role!r}")
        if self.severity not in SEVERITIES:
            raise FactContractError(f"unknown fact severity: {self.severity!r}")
        if self.freshness not in FRESHNESS:
            raise FactContractError(f"unknown freshness: {self.freshness!r}")
        if self.degradation_status not in DEGRADATION_STATUSES:
            raise FactContractError(
                f"unknown degradation_status: {self.degradation_status!r}"
            )

    @property
    def traceable(self) -> bool:
        return bool(self.source) and _time_basis_valid(
            self.report_period,
            self.as_of,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "fact_key": self.fact_key,
            "label": self.label,
            "value": self.value,
            "severity": self.severity,
            "source": self.source,
            "report_period": self.report_period,
            "as_of": self.as_of,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "freshness": self.freshness,
            "degradation_status": self.degradation_status,
            "traceable": self.traceable,
            "reason": self.reason,
        }


def _code_matches(payload: dict, requested_code: str) -> bool:
    declared = payload.get("code")
    if declared is None:
        return True
    try:
        return canonical_code(declared) == requested_code
    except (TypeError, ValueError):
        return False


def _latest_year(payload: dict) -> str | None:
    years = payload.get("years")
    if not isinstance(years, list) or not years:
        return None
    last = years[-1]
    return str(last) if last is not None else None


def _time_basis_valid(report_period: Any, as_of: Any) -> bool:
    """报告期/观察时点必须是可解析的日期，不接受任意非空字符串."""
    if report_period is not None and _parse_period_end(report_period) is None:
        return False
    if as_of is not None and _parse_time(as_of) is None:
        return False
    return bool(_parse_period_end(report_period) or _parse_time(as_of))


def _core_provenance(dossier: dict, core: dict) -> dict[str, Any]:
    """读取 core_snapshot 的字段级 provenance sidecar."""
    sidecar = dossier.get("core_fact_provenance")
    if isinstance(sidecar, dict):
        return sidecar
    sidecar = core.get("fact_provenance")
    if isinstance(sidecar, dict):
        return sidecar
    return {}


def build_fact_contract(
    dossier: dict,
    *,
    ticker: str | None = None,
    retrieved_at: str | None = None,
    now: datetime | None = None,
    stale_after_days: int = 730,
    fail_closed: bool = True,
) -> dict[str, Any]:
    """从分层 dossier 提取事实证据，输出可复核契约；高严重度不可追溯时 fail closed."""
    research = dossier.get("research_dossier")
    if not isinstance(research, dict):
        raise FactContractError("dossier.research_dossier must be a dict")

    core = dossier.get("core_snapshot") or {}
    raw_ticker = ticker or core.get("ticker")
    if not raw_ticker:
        raise FactContractError("dossier ticker is required for fact provenance")
    try:
        requested_code = canonical_code(raw_ticker)
    except (TypeError, ValueError) as exc:
        raise FactContractError("dossier ticker is invalid") from exc

    retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
    current = now or datetime.now(timezone.utc)
    degraded_fields = set(research.get("degraded_fields") or [])

    facts: list[FactEvidence] = []
    role_status: list[dict[str, str]] = []
    invalid_high: list[str] = []
    invalid_roles: set[str] = set()

    def add_fact(
        *,
        role: str,
        fact_key: str,
        label: str,
        value: Any,
        severity: str,
        source: str | None,
        report_period: str | None,
        as_of: str | None,
        published_at: str | None,
        source_mismatch: bool,
    ) -> None:
        if value is None:
            return
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            invalid_roles.add(role)
            if severity == "high":
                invalid_high.append(f"{fact_key}: non-finite numeric value")
            return
        src = None if source_mismatch else source
        valid_time_basis = _time_basis_valid(report_period, as_of)
        freshness = _freshness(
            report_period,
            published_at,
            as_of,
            retrieved,
            current,
            stale_after_days,
        )
        degradation_status = "clean"
        reason: str | None = None
        if source_mismatch:
            degradation_status = "degraded"
            reason = f"source ticker mismatch for {fact_key}"
        elif not src:
            degradation_status = "degraded"
            reason = f"missing source for {fact_key}"
        elif published_at is not None and _parse_time(published_at) is None:
            degradation_status = "degraded"
            reason = f"invalid published_at for {fact_key}"
        elif freshness == "unknown":
            degradation_status = "degraded"
            reason = f"missing time basis for {fact_key}"
        elif freshness == "stale":
            degradation_status = "degraded"
            reason = f"stale time basis for {fact_key}"
        elif not valid_time_basis:
            degradation_status = "degraded"
            reason = f"invalid or missing time basis for {fact_key}"
        facts.append(
            FactEvidence(
                role=role,
                fact_key=fact_key,
                label=label,
                value=value,
                severity=severity,
                source=src,
                report_period=report_period,
                as_of=as_of,
                published_at=published_at,
                retrieved_at=retrieved,
                freshness=freshness,
                degradation_status=degradation_status,
                reason=reason,
            )
        )

    def role_quality(role: str, *, unavailable: bool, unavailable_reason: str) -> tuple[str, str | None]:
        if unavailable:
            return "unavailable", unavailable_reason
        if role in invalid_roles:
            return "degraded", f"{role} contains non-finite numeric facts"
        role_facts = [fact for fact in facts if fact.role == role]
        if not role_facts:
            return "degraded", f"{role} contains no numeric facts"
        if any(
            fact.degradation_status != "clean" or not fact.traceable
            for fact in role_facts
        ):
            return "degraded", f"{role} contains untraceable or degraded facts"
        return "clean", None

    # ── core_snapshot ───────────────────────────────────────────
    core_facts_before = len(facts)
    core_provenance = _core_provenance(dossier, core)
    for fact_key in CORE_NUMERIC_FACTS:
        value = core.get(fact_key)
        if value is None:
            continue
        metadata = core_provenance.get(fact_key)
        metadata = metadata if isinstance(metadata, dict) else {}
        source = metadata.get("source")
        report_period = metadata.get("report_period")
        as_of = metadata.get("as_of")
        published_at = metadata.get("published_at")
        metadata_retrieved_at = metadata.get("retrieved_at") or retrieved
        source_ticker = metadata.get("ticker") or metadata.get("code")
        mismatch = (
            source_ticker is not None
            and not _code_matches({"code": source_ticker}, requested_code)
        )
        if isinstance(value, list):
            invalid = any(
                isinstance(item, float) and (math.isnan(item) or math.isinf(item))
                for item in value
            )
            if invalid:
                invalid_roles.add("core_snapshot")
                invalid_high.append(f"core_snapshot.{fact_key}: non-finite numeric value")
                continue
        add_fact(
            role="core_snapshot",
            fact_key=f"core_snapshot.{fact_key}",
            label=f"核心特征 {fact_key}",
            value=value,
            severity="high",
            source=source,
            report_period=report_period,
            as_of=as_of,
            published_at=published_at,
            source_mismatch=mismatch,
        )
        if facts:
            facts[-1] = FactEvidence(
                role=facts[-1].role,
                fact_key=facts[-1].fact_key,
                label=facts[-1].label,
                value=facts[-1].value,
                severity=facts[-1].severity,
                source=facts[-1].source,
                report_period=facts[-1].report_period,
                as_of=facts[-1].as_of,
                published_at=facts[-1].published_at,
                retrieved_at=metadata_retrieved_at,
                freshness=facts[-1].freshness,
                degradation_status=facts[-1].degradation_status,
                reason=facts[-1].reason,
            )
    core_fact_count = len(facts) - core_facts_before
    core_untraceable_count = sum(
        1
        for fact in facts[core_facts_before:]
        if not fact.traceable
    )
    role_status.append(
        {
            "role": "core_snapshot",
            "degradation_status": (
                "degraded"
                if core_untraceable_count or "core_snapshot" in invalid_roles
                else "clean"
            ),
            "reason": (
                "core_snapshot contains untraceable numeric facts"
                if core_untraceable_count
                else "core_snapshot contains non-finite numeric facts"
                if "core_snapshot" in invalid_roles
                else None
            ),
        }
    )

    # ── main_business ─────────────────────────────────────────────
    mb = research.get("main_business")
    mb_degraded = "main_business" in degraded_fields or _is_error_data(mb)
    mb_facts_before = len(facts)
    if isinstance(mb, dict) and not mb_degraded:
        source = (
            SOURCE_BY_ROLE["main_business"]
            if any(k in mb for k in ("by_industry", "by_product", "by_region"))
            else SOURCE_BY_ROLE["main_business_fallback"]
        )
        report_period = mb.get("report_date")
        mismatch = not _code_matches(mb, requested_code)
        for category in ("by_industry", "by_product", "by_region"):
            entries = mb.get(category) or []
            if not isinstance(entries, list):
                continue
            for index, entry in enumerate(entries):
                if not isinstance(entry, dict):
                    continue
                for field in ("revenue", "revenue_ratio", "gross_margin"):
                    add_fact(
                        role="main_business",
                        fact_key=f"main_business.{category}[{index}].{field}",
                        label=f"主营 {category}[{index}].{field}",
                        value=entry.get(field),
                        severity="high",
                        source=source,
                        report_period=report_period,
                        as_of=None,
                        published_at=mb.get("published_at"),
                        source_mismatch=mismatch,
                    )
    if not isinstance(mb, dict) or mb_degraded:
        mb_role_status = "unavailable"
        mb_role_reason = "main_business unavailable"
    elif len(facts) == mb_facts_before:
        # 兜底纯文本没有可追溯的数值主营构成，属于弱证据，不得标 clean。
        mb_role_status = "degraded"
        mb_role_reason = "main_business fallback text only (no numeric business facts)"
    else:
        mb_role_status, mb_role_reason = role_quality(
            "main_business",
            unavailable=False,
            unavailable_reason="main_business unavailable",
        )
    role_status.append(
        {
            "role": "main_business",
            "degradation_status": mb_role_status,
            "reason": mb_role_reason,
        }
    )

    # ── peers ─────────────────────────────────────────────────────
    peers = research.get("peers")
    peers_degraded = "peers" in degraded_fields or _is_error_data(peers)
    if isinstance(peers, dict) and not peers_degraded:
        source = SOURCE_BY_ROLE["peers"]
        mismatch = not _code_matches(peers, requested_code)
        add_fact(
            role="peers",
            fact_key="peers.peer_avg_pe",
            label="同行平均 PE",
            value=peers.get("peer_avg_pe"),
            severity="high",
            source=source,
            report_period=None,
            as_of=retrieved,
            published_at=peers.get("published_at"),
            source_mismatch=mismatch,
        )
        add_fact(
            role="peers",
            fact_key="peers.industry_pe_rank",
            label="行业 PE 排名",
            value=peers.get("industry_pe_rank"),
            severity="medium",
            source=source,
            report_period=None,
            as_of=retrieved,
            published_at=peers.get("published_at"),
            source_mismatch=mismatch,
        )
        add_fact(
            role="peers",
            fact_key="peers.peer_count",
            label="同行数量",
            value=peers.get("peer_count"),
            severity="low",
            source=source,
            report_period=None,
            as_of=retrieved,
            published_at=peers.get("published_at"),
            source_mismatch=mismatch,
        )
        peer_pe_list = peers.get("peer_pe_list") or []
        if isinstance(peer_pe_list, list):
            for index, item in enumerate(peer_pe_list):
                add_fact(
                    role="peers",
                    fact_key=f"peers.peer_pe_list[{index}]",
                    label=f"同行成分股 PE[{index}]",
                    value=item,
                    severity="low",
                    source=source,
                    report_period=None,
                    as_of=retrieved,
                    published_at=peers.get("published_at"),
                    source_mismatch=mismatch,
                )
    peers_status, peers_reason = role_quality(
        "peers",
        unavailable=peers_degraded or not isinstance(peers, dict),
        unavailable_reason="peers unavailable",
    )
    role_status.append(
        {
            "role": "peers",
            "degradation_status": peers_status,
            "reason": peers_reason,
        }
    )

    # ── research ──────────────────────────────────────────────────
    research_data = research.get("research")
    research_degraded = "research" in degraded_fields or _is_error_data(research_data)
    if isinstance(research_data, dict) and not research_degraded:
        source = SOURCE_BY_ROLE["research"]
        mismatch = not _code_matches(research_data, requested_code)
        add_fact(
            role="research",
            fact_key="research.consensus_eps",
            label="一致预期 EPS",
            value=research_data.get("consensus_eps"),
            severity="high",
            source=source,
            report_period=None,
            as_of=retrieved,
            published_at=research_data.get("published_at"),
            source_mismatch=mismatch,
        )
        add_fact(
            role="research",
            fact_key="research.target_price",
            label="一致预期目标价",
            value=research_data.get("target_price"),
            severity="high",
            source=source,
            report_period=None,
            as_of=retrieved,
            published_at=research_data.get("published_at"),
            source_mismatch=mismatch,
        )
        add_fact(
            role="research",
            fact_key="research.buy_rating_pct",
            label="看多评级占比",
            value=research_data.get("buy_rating_pct"),
            severity="medium",
            source=source,
            report_period=None,
            as_of=retrieved,
            published_at=research_data.get("published_at"),
            source_mismatch=mismatch,
        )
        add_fact(
            role="research",
            fact_key="research.coverage_count",
            label="研报覆盖数",
            value=research_data.get("coverage_count"),
            severity="low",
            source=source,
            report_period=None,
            as_of=retrieved,
            published_at=research_data.get("published_at"),
            source_mismatch=mismatch,
        )
    research_status, research_reason = role_quality(
        "research",
        unavailable=research_degraded or not isinstance(research_data, dict),
        unavailable_reason="research unavailable",
    )
    role_status.append(
        {
            "role": "research",
            "degradation_status": research_status,
            "reason": research_reason,
        }
    )

    # ── capex_proxy ───────────────────────────────────────────────
    capex = research.get("capex_proxy")
    capex_degraded = "capex_proxy" in degraded_fields or _is_error_data(capex)
    if isinstance(capex, dict) and not capex_degraded:
        source = f"data/cache/{requested_code}/financials.CONSTRUCT_LONG_ASSET"
        report_period = _latest_year(capex)
        mismatch = False
        add_fact(
            role="capex_proxy",
            fact_key="capex_proxy.latest",
            label="资本开支代理最新值",
            value=capex.get("latest"),
            severity="high",
            source=source,
            report_period=report_period,
            as_of=None,
            published_at=capex.get("published_at"),
            source_mismatch=mismatch,
        )
        series = capex.get("series") or []
        if isinstance(series, list):
            for index, item in enumerate(series):
                add_fact(
                    role="capex_proxy",
                    fact_key=f"capex_proxy.series[{index}]",
                    label=f"资本开支代理序列[{index}]",
                    value=item,
                    severity="low",
                    source=source,
                    report_period=report_period,
                    as_of=None,
                    published_at=capex.get("published_at"),
                    source_mismatch=mismatch,
                )
    capex_status, capex_reason = role_quality(
        "capex_proxy",
        unavailable=capex_degraded or not isinstance(capex, dict),
        unavailable_reason="capex_proxy unavailable",
    )
    role_status.append(
        {
            "role": "capex_proxy",
            "degradation_status": capex_status,
            "reason": capex_reason,
        }
    )

    high_severity = [f for f in facts if f.severity == "high"]
    untraceable_high = [f for f in high_severity if not f.traceable]
    fail_closed_details = [
        f"{f.fact_key}: {f.reason or 'missing source/time basis'}"
        for f in untraceable_high
    ]
    fail_closed_details.extend(invalid_high)
    if fail_closed_details and fail_closed:
        details = "; ".join(
            fail_closed_details
        )
        raise FactContractError(f"high severity facts fail closed: {details}")
    failed = bool(fail_closed_details)

    total = len(facts)
    traceable = sum(1 for f in facts if f.traceable)
    stale_count = sum(1 for f in facts if f.freshness == "stale")
    degraded_count = sum(1 for f in facts if f.degradation_status != "clean")
    role_degraded = any(
        item["degradation_status"] != "clean" for item in role_status
    )
    clean = (
        total > 0
        and stale_count == 0
        and degraded_count == 0
        and not role_degraded
        and not failed
    )

    from data.lib.audit_chain import AuditIdentityError, payload_sha256

    try:
        raw_dossier_hash = payload_sha256(
            dossier_without_quality_sidecar(dossier)
        )
    except AuditIdentityError:
        # 非有限 raw 数字先由事实契约标记 failed；不能让 hash 异常遮蔽
        # high severity fail-closed 结果。
        raw_dossier_hash = None
    return {
        "schema_version": FACT_CONTRACT_SCHEMA_VERSION,
        "ticker": requested_code,
        "dossier_sha256": raw_dossier_hash,
        "retrieved_at": retrieved,
        "facts": [f.to_dict() for f in facts],
        "role_status": role_status,
        "total_fact_count": total,
        "traceable_fact_count": traceable,
        "traceable_ratio": (traceable / total) if total else 0.0,
        "high_severity_fact_count": len(high_severity),
        "high_severity_untraceable_count": len(untraceable_high),
        "high_severity_invalid_count": len(invalid_high),
        "high_severity_invalid_reasons": invalid_high,
        "core_fact_count": core_fact_count,
        "core_untraceable_count": core_untraceable_count,
        "stale_fact_count": stale_count,
        "degraded_fact_count": degraded_count,
        "failed": failed,
        "clean": clean,
    }


def derive_quality_status(contract: dict[str, Any]) -> tuple[str, list[str]]:
    """从事实契约导出 dossier 质量状态与可见原因."""
    if contract.get("failed"):
        reasons: list[str] = []
        for fact in contract.get("facts", []):
            if fact.get("reason"):
                reasons.append(fact["reason"])
        reasons.extend(contract.get("high_severity_invalid_reasons", []))
        unique: list[str] = []
        for reason in reasons:
            if reason not in unique:
                unique.append(reason)
        return "failed", unique
    if contract.get("clean"):
        return "clean", []
    reasons: list[str] = []
    for fact in contract.get("facts", []):
        if fact.get("reason"):
            reasons.append(fact["reason"])
    for role in contract.get("role_status", []):
        if role.get("degradation_status") != "clean":
            reasons.append(role.get("reason") or f"{role.get('role')} {role.get('degradation_status')}")
    unique: list[str] = []
    for reason in reasons:
        if reason not in unique:
            unique.append(reason)
    return "degraded", unique


def evaluate_dossier_quality(
    dossier: dict,
    *,
    ticker: str | None = None,
) -> tuple[str, list[str], dict[str, Any]]:
    """从 raw dossier 派生质量状态，不信任 caller-supplied sidecar，也不修改输入."""
    contract = build_fact_contract(dossier, ticker=ticker, fail_closed=False)
    status, reasons = derive_quality_status(contract)
    return status, reasons, contract
