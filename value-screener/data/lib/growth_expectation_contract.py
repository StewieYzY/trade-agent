"""G2 growth expectation capitalization diagnostic contract.

This module owns only the frozen input/output schema, user assumption
snapshot, model applicability and failure semantics for the deterministic
``growth_expectation_diagnostic`` artifact. It does not compute EPV proxies,
mature-multiple cross-checks, reverse solves or sensitivity values.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from data.lib.identity import canonical_ticker

GROWTH_EXPECTATION_SCHEMA_VERSION = "g2-growth-expectation-contract-v1"
ASSUMPTION_SNAPSHOT_VERSION = "g2-assumption-snapshot-v1"
DIAGNOSTIC_INPUT_SCHEMA_VERSION = "g2-growth-expectation-input-v1"

CALCULATION_STATUSES = ("clean", "degraded", "not_evaluable", "failed")
DIAGNOSTIC_QUALITY_STATUSES = ("warning", "failed")
DECISION_GRADES = ("diagnostic",)

FAILURE_KINDS = ("data_insufficient", "model_not_applicable", "computation_failed")
FAILURE_TO_STATUS = {
    "data_insufficient": "not_evaluable",
    "model_not_applicable": "not_evaluable",
    "computation_failed": "failed",
}

FAILURE_REASON_CODES = (
    "data_missing",
    "data_stale",
    "data_unit_mismatch",
    "data_period_mismatch",
    "data_published_at_missing",
    "data_source_unbound",
    "data_source_provenance_missing",
    "data_source_failed",
    "data_negative_earnings",
    "data_negative_cashflow",
    "data_cyclical_peak",
    "data_discount_rate_ordering",
    "data_capex_ratio_out_of_range",
    "data_currency_scale_mismatch",
    "data_expired",
    "model_out_of_scope",
    "model_precondition_violated",
    "reverse_duration_exceeds_cap",
    "solver_no_solution",
    "solver_non_finite",
)
FAILURE_KIND_REASON_CODES = {
    "data_insufficient": frozenset(
        (
            "data_missing",
            "data_stale",
            "data_unit_mismatch",
            "data_period_mismatch",
            "data_published_at_missing",
            "data_source_unbound",
            "data_source_provenance_missing",
            "data_source_failed",
            "data_negative_earnings",
            "data_negative_cashflow",
            "data_cyclical_peak",
            "data_discount_rate_ordering",
            "data_capex_ratio_out_of_range",
            "data_currency_scale_mismatch",
            "data_expired",
        )
    ),
    "model_not_applicable": frozenset(
        (
            "model_out_of_scope",
            "model_precondition_violated",
            "reverse_duration_exceeds_cap",
        )
    ),
    "computation_failed": frozenset(("solver_no_solution", "solver_non_finite")),
}

SUPPORTED_CURRENCIES = ("CNY", "HKD", "USD")
SUPPORTED_VALUE_SCALES = ("absolute", "thousand", "million", "hundred_million")
FRESHNESS_VALUES = ("fresh", "stale", "unknown")
SOURCE_DEGRADATION_STATUSES = ("clean", "degraded", "failed")
EXPECTATION_OVERDRAFT_LEVELS = (
    "within_credible_range",
    "above_base_case",
    "above_credible_upper_bound",
    "not_evaluable",
)
EXPECTATION_OVERDRAFT_RESULT_LEVELS = EXPECTATION_OVERDRAFT_LEVELS[:3]
REVERSE_MODES = ("fixed_growth_rate", "fixed_duration")

MONETARY_INPUT_FIELDS = (
    "current_market_value",
    "normalized_operating_cashflow",
    "total_capex",
    "normalized_net_profit",
)

REQUIRED_ASSUMPTION_KEYS = (
    "normalized_earnings_basis",
    "maintenance_capex_ratio",
    "cost_of_equity",
    "maintenance_growth",
    "credible_growth_rate",
    "mature_pe",
    "reverse_mode",
)
REVERSE_FIXED_GROWTH_RATE_KEY = "reverse_fixed_growth_rate"
REVERSE_FIXED_DURATION_YEARS_KEY = "reverse_fixed_duration_years"
MAX_REVERSE_DURATION_YEARS = 50
NORMALIZED_EARNINGS_BASES = (
    "normalized_operating_cashflow",
    "normalized_net_profit",
)
ASSUMPTION_UNITS_BY_KEY = {
    "normalized_earnings_basis": "",
    "maintenance_capex_ratio": "ratio",
    "cost_of_equity": "decimal",
    "maintenance_growth": "decimal",
    "credible_growth_rate": "decimal",
    "mature_pe": "x",
    "reverse_mode": "",
    REVERSE_FIXED_GROWTH_RATE_KEY: "decimal",
    REVERSE_FIXED_DURATION_YEARS_KEY: "years",
}

_FINANCIAL_INDUSTRY_KEYWORDS = (
    "bank",
    "insurance",
    "securit",
    "financial",
    "finance",
    "券商",
    "证券",
    "银行",
    "保险",
    "金融",
)

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPORT_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-\d{2}$|^\d{4}Q[1-4]$")


class ContractError(ValueError):
    """Raised when a growth expectation contract field is not trustworthy."""


def _require_text(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} is required")
    return value.strip()


def _require_date(name: str, value: Any) -> str:
    text = _require_text(name, value)
    if not _ISO_DATE_RE.match(text):
        raise ContractError(f"{name} must be an ISO date (YYYY-MM-DD)")
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ContractError(f"{name} must be a valid date") from exc
    return text


def _require_report_period(name: str, value: Any) -> str:
    text = _require_text(name, value)
    if not _REPORT_PERIOD_RE.match(text):
        raise ContractError(f"{name} must be a date (YYYY-MM-DD) or quarter (YYYYQn)")
    if "Q" not in text:
        try:
            date.fromisoformat(text)
        except ValueError as exc:
            raise ContractError(f"{name} must be a valid calendar date") from exc
    return text


def _require_choice(name: str, value: Any, choices: tuple[str, ...]) -> str:
    text = _require_text(name, value)
    if text not in choices:
        raise ContractError(f"{name} is not supported: {text!r}")
    return text


def _require_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ContractError(f"{name} must be finite")
    return number


def _require_non_negative(name: str, value: Any) -> float:
    number = _require_number(name, value)
    if number < 0:
        raise ContractError(f"{name} must be non-negative")
    return number


def _require_positive(name: str, value: Any) -> float:
    number = _require_number(name, value)
    if number <= 0:
        raise ContractError(f"{name} must be positive")
    return number


def _require_optional_non_negative(name: str, value: Any) -> float | None:
    if value is None:
        return None
    return _require_non_negative(name, value)


def _require_optional_positive(name: str, value: Any) -> float | None:
    if value is None:
        return None
    return _require_positive(name, value)


def _require_optional_number(name: str, value: Any) -> float | None:
    if value is None:
        return None
    return _require_number(name, value)


def _require_range(name: str, value: Any) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ContractError(f"{name} must be a two-value range")
    low = _require_number(f"{name}[0]", value[0])
    high = _require_number(f"{name}[1]", value[1])
    if low > high:
        raise ContractError(f"{name} must be ordered low <= high")
    return (low, high)


def _require_non_negative_range(name: str, value: Any) -> tuple[float, float]:
    low, high = _require_range(name, value)
    if low < 0:
        raise ContractError(f"{name} must be non-negative")
    return (low, high)


def _require_optional_range(name: str, value: Any) -> tuple[float, float] | None:
    if value is None:
        return None
    return _require_range(name, value)


def _require_text_tuple(name: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ContractError(f"{name} must be a list")
    return tuple(_require_text(f"{name}[]", item) for item in value)


def _require_choice_tuple(
    name: str,
    value: Any,
    choices: tuple[str, ...],
) -> tuple[str, ...]:
    items = _require_text_tuple(name, value)
    for item in items:
        if item not in choices:
            raise ContractError(f"{name} contains unsupported value: {item!r}")
    return items


def _require_no_unknown_fields(
    name: str,
    value: Mapping[str, Any],
    allowed: tuple[str, ...],
) -> None:
    unknown = sorted(set(value) - set(allowed))
    if unknown:
        raise ContractError(f"{name} contains unknown fields: {unknown}")


def _raise_invalid_structure(name: str, exc: Exception) -> None:
    detail = exc.args[0] if isinstance(exc, KeyError) else str(exc)
    raise ContractError(f"{name} structure is invalid: {detail}") from exc


def _require_digest(name: str, value: Any) -> str:
    text = _require_text(name, value)
    if not _DIGEST_RE.match(text):
        raise ContractError(f"{name} must be a lowercase sha256 digest")
    return text


def _write_normalized(obj: Any, **fields: Any) -> None:
    for name, value in fields.items():
        object.__setattr__(obj, name, value)


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractError("value is not strict JSON") from exc


def _payload_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_financial_industry(industry: str | None) -> bool:
    if not industry or not isinstance(industry, str):
        return False
    normalized = industry.strip().lower()
    return any(keyword in normalized for keyword in _FINANCIAL_INDUSTRY_KEYWORDS)


@dataclass(frozen=True)
class DiagnosticSource:
    source_id: str
    provider: str
    field: str
    raw_field: str
    raw_payload_hash: str
    report_period: str
    as_of: str
    freshness: str
    currency: str
    value_scale: str
    published_at: str
    degradation_status: str

    def __post_init__(self) -> None:
        _write_normalized(
            self,
            source_id=_require_text("source_id", self.source_id),
            provider=_require_text("provider", self.provider),
            field=_require_choice("field", self.field, MONETARY_INPUT_FIELDS),
            raw_field=_require_text("raw_field", self.raw_field),
            report_period=_require_report_period("report_period", self.report_period),
            as_of=_require_date("as_of", self.as_of),
            freshness=_require_choice("freshness", self.freshness, FRESHNESS_VALUES),
            currency=_require_choice("currency", self.currency, SUPPORTED_CURRENCIES),
            value_scale=_require_choice(
                "value_scale", self.value_scale, SUPPORTED_VALUE_SCALES
            ),
            published_at=_require_date("published_at", self.published_at),
            degradation_status=_require_choice(
                "degradation_status",
                self.degradation_status,
                SOURCE_DEGRADATION_STATUSES,
            ),
            raw_payload_hash=_require_digest(
                "raw_payload_hash", self.raw_payload_hash
            ),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DiagnosticSource":
        if not isinstance(value, Mapping):
            raise ContractError("source must be a mapping")
        _require_no_unknown_fields(
            "source",
            value,
            (
                "source_id",
                "provider",
                "field",
                "raw_field",
                "raw_payload_hash",
                "report_period",
                "as_of",
                "freshness",
                "currency",
                "value_scale",
                "published_at",
                "degradation_status",
            ),
        )
        try:
            return cls(
                source_id=value["source_id"],
                provider=value["provider"],
                field=value["field"],
                raw_field=value["raw_field"],
                raw_payload_hash=value["raw_payload_hash"],
                report_period=value["report_period"],
                as_of=value["as_of"],
                freshness=value["freshness"],
                currency=value["currency"],
                value_scale=value["value_scale"],
                published_at=value["published_at"],
                degradation_status=value["degradation_status"],
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("source", exc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "provider": self.provider,
            "field": self.field,
            "raw_field": self.raw_field,
            "raw_payload_hash": self.raw_payload_hash,
            "report_period": self.report_period,
            "as_of": self.as_of,
            "freshness": self.freshness,
            "currency": self.currency,
            "value_scale": self.value_scale,
            "published_at": self.published_at,
            "degradation_status": self.degradation_status,
        }


@dataclass(frozen=True)
class DiagnosticInput:
    schema_version: str
    ticker: str
    valuation_date: str
    report_period: str
    as_of: str
    currency: str
    value_scale: str
    current_market_value: float
    normalized_operating_cashflow: float
    total_capex: float
    normalized_net_profit: float
    sources: tuple[DiagnosticSource, ...]

    def __post_init__(self) -> None:
        if self.schema_version != DIAGNOSTIC_INPUT_SCHEMA_VERSION:
            raise ContractError("unsupported diagnostic input schema_version")
        try:
            canonical = canonical_ticker(self.ticker)
        except (TypeError, ValueError) as exc:
            raise ContractError("ticker is not canonical") from exc
        if canonical != self.ticker:
            raise ContractError("ticker must be canonical")
        _write_normalized(
            self,
            ticker=canonical,
            valuation_date=_require_date("valuation_date", self.valuation_date),
            report_period=_require_report_period("report_period", self.report_period),
            as_of=_require_date("as_of", self.as_of),
            currency=_require_choice("currency", self.currency, SUPPORTED_CURRENCIES),
            value_scale=_require_choice(
                "value_scale", self.value_scale, SUPPORTED_VALUE_SCALES
            ),
        )
        _require_positive("current_market_value", self.current_market_value)
        _require_number(
            "normalized_operating_cashflow", self.normalized_operating_cashflow
        )
        _require_non_negative("total_capex", self.total_capex)
        _require_number("normalized_net_profit", self.normalized_net_profit)
        if not isinstance(self.sources, tuple) or not self.sources:
            raise ContractError("sources must be a non-empty list")
        if any(not isinstance(source, DiagnosticSource) for source in self.sources):
            raise ContractError("sources must contain DiagnosticSource records")
        for source in self.sources:
            if source.report_period != self.report_period:
                raise ContractError("source report_period mismatch")
            if source.as_of != self.as_of:
                raise ContractError("source as_of mismatch")
            if source.currency != self.currency:
                raise ContractError("source currency mismatch")
            if source.value_scale != self.value_scale:
                raise ContractError("source value_scale mismatch")
        self._validate_field_coverage()

    def _validate_field_coverage(self) -> None:
        present = [source.field for source in self.sources]
        missing = sorted(set(MONETARY_INPUT_FIELDS) - set(present))
        if missing:
            raise ContractError(f"missing field-level sources: {missing}")
        duplicate = sorted(
            field
            for field in MONETARY_INPUT_FIELDS
            if present.count(field) > 1
        )
        if duplicate:
            raise ContractError(f"duplicate field-level sources: {duplicate}")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DiagnosticInput":
        if not isinstance(value, Mapping):
            raise ContractError("input must be a mapping")
        _require_no_unknown_fields(
            "input",
            value,
            (
                "schema_version",
                "ticker",
                "valuation_date",
                "report_period",
                "as_of",
                "currency",
                "value_scale",
                "current_market_value",
                "normalized_operating_cashflow",
                "total_capex",
                "normalized_net_profit",
                "sources",
            ),
        )
        try:
            sources = tuple(
                DiagnosticSource.from_dict(item) for item in value["sources"]
            )
            return cls(
                schema_version=value["schema_version"],
                ticker=value["ticker"],
                valuation_date=value["valuation_date"],
                report_period=value["report_period"],
                as_of=value["as_of"],
                currency=value["currency"],
                value_scale=value["value_scale"],
                current_market_value=value["current_market_value"],
                normalized_operating_cashflow=value["normalized_operating_cashflow"],
                total_capex=value["total_capex"],
                normalized_net_profit=value["normalized_net_profit"],
                sources=sources,
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("input", exc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticker": self.ticker,
            "valuation_date": self.valuation_date,
            "report_period": self.report_period,
            "as_of": self.as_of,
            "currency": self.currency,
            "value_scale": self.value_scale,
            "current_market_value": self.current_market_value,
            "normalized_operating_cashflow": self.normalized_operating_cashflow,
            "total_capex": self.total_capex,
            "normalized_net_profit": self.normalized_net_profit,
            "sources": [source.to_dict() for source in self.sources],
        }


def validate_diagnostic_input(value: Mapping[str, Any]) -> DiagnosticInput:
    """Parse and validate a diagnostic input payload."""
    return DiagnosticInput.from_dict(value)


@dataclass(frozen=True)
class Assumption:
    key: str
    value: Any
    unit: str
    source: str
    confirmed_by_user: bool
    version: str

    def __post_init__(self) -> None:
        key = _require_text("key", self.key)
        if isinstance(self.value, list):
            object.__setattr__(self, "value", tuple(self.value))
        _validate_assumption_unit(key, self.unit)
        source = _require_text("source", self.source)
        version = _require_text("version", self.version)
        if not isinstance(self.confirmed_by_user, bool):
            raise ContractError("confirmed_by_user must be a boolean")
        _validate_assumption_value(key, self.value)
        _write_normalized(
            self,
            key=key,
            source=source,
            version=version,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Assumption":
        if not isinstance(value, Mapping):
            raise ContractError("assumption must be a mapping")
        _require_no_unknown_fields(
            "assumption",
            value,
            ("key", "value", "unit", "source", "confirmed_by_user", "version"),
        )
        try:
            return cls(
                key=value["key"],
                value=value["value"],
                unit=value["unit"],
                source=value["source"],
                confirmed_by_user=value["confirmed_by_user"],
                version=value["version"],
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("assumption", exc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "confirmed_by_user": self.confirmed_by_user,
            "version": self.version,
        }


def _validate_assumption_unit(key: str, unit: Any) -> None:
    if key not in ASSUMPTION_UNITS_BY_KEY:
        raise ContractError(f"unsupported assumption key: {key!r}")
    if not isinstance(unit, str):
        raise ContractError("assumption unit must be a string")
    expected = ASSUMPTION_UNITS_BY_KEY[key]
    if unit != expected:
        raise ContractError(f"assumption {key!r} unit must be {expected!r}")


def _validate_assumption_value(key: str, value: Any) -> None:
    if key == "normalized_earnings_basis":
        _require_choice("normalized_earnings_basis", value, NORMALIZED_EARNINGS_BASES)
        return
    if key == "maintenance_capex_ratio":
        low, high = _require_range("maintenance_capex_ratio", value)
        if not (0 <= low and high <= 1):
            raise ContractError("maintenance_capex_ratio must be within [0, 1]")
        return
    if key == "cost_of_equity":
        low, high = _require_range("cost_of_equity", value)
        if low <= 0:
            raise ContractError("cost_of_equity must be positive")
        return
    if key == "maintenance_growth":
        _require_non_negative("maintenance_growth", value)
        return
    if key == "credible_growth_rate":
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ContractError("credible_growth_rate must be a three-value range")
        low = _require_number("credible_growth_rate[0]", value[0])
        mid = _require_number("credible_growth_rate[1]", value[1])
        high = _require_number("credible_growth_rate[2]", value[2])
        if not low <= mid <= high:
            raise ContractError("credible_growth_rate must be ordered")
        return
    if key == "mature_pe":
        low, high = _require_range("mature_pe", value)
        if low <= 0:
            raise ContractError("mature_pe must be positive")
        return
    if key == "reverse_mode":
        _require_choice("reverse_mode", value, REVERSE_MODES)
        return
    if key == REVERSE_FIXED_GROWTH_RATE_KEY:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ContractError(
                "reverse_fixed_growth_rate must be a three-value range"
            )
        low = _require_non_negative(REVERSE_FIXED_GROWTH_RATE_KEY + "[0]", value[0])
        mid = _require_non_negative(REVERSE_FIXED_GROWTH_RATE_KEY + "[1]", value[1])
        high = _require_non_negative(REVERSE_FIXED_GROWTH_RATE_KEY + "[2]", value[2])
        if not low <= mid <= high:
            raise ContractError("reverse_fixed_growth_rate must be ordered")
        return
    if key == REVERSE_FIXED_DURATION_YEARS_KEY:
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            raise ContractError(
                "reverse_fixed_duration_years must be a three-value range"
            )
        low = _require_number(REVERSE_FIXED_DURATION_YEARS_KEY + "[0]", value[0])
        mid = _require_number(REVERSE_FIXED_DURATION_YEARS_KEY + "[1]", value[1])
        high = _require_number(REVERSE_FIXED_DURATION_YEARS_KEY + "[2]", value[2])
        if not (0 < low <= mid <= high <= MAX_REVERSE_DURATION_YEARS):
            raise ContractError(
                f"reverse_fixed_duration_years must be positive, ordered, "
                f"and not exceed {MAX_REVERSE_DURATION_YEARS}"
            )
        return
    raise ContractError(f"unsupported assumption key: {key!r}")


@dataclass(frozen=True)
class AssumptionSnapshot:
    version: str
    created_at: str
    assumptions: tuple[Assumption, ...]

    def __post_init__(self) -> None:
        version = _require_text("version", self.version)
        if version != ASSUMPTION_SNAPSHOT_VERSION:
            raise ContractError("unsupported assumption snapshot version")
        created_at = _require_date("created_at", self.created_at)
        _write_normalized(self, version=version, created_at=created_at)
        if not isinstance(self.assumptions, tuple) or not self.assumptions:
            raise ContractError("assumptions must be a non-empty list")
        if any(not isinstance(item, Assumption) for item in self.assumptions):
            raise ContractError("assumptions must contain Assumption records")
        keys = [assumption.key for assumption in self.assumptions]
        if len(keys) != len(set(keys)):
            raise ContractError("assumptions contain duplicate keys")
        for assumption in self.assumptions:
            if not assumption.confirmed_by_user:
                raise ContractError(
                    f"assumption {assumption.key!r} is not confirmed by user"
                )
        missing = sorted(set(REQUIRED_ASSUMPTION_KEYS) - set(keys))
        if missing:
            raise ContractError(f"missing required assumptions: {missing}")
        allowed_keys = REQUIRED_ASSUMPTION_KEYS + (
            REVERSE_FIXED_GROWTH_RATE_KEY,
            REVERSE_FIXED_DURATION_YEARS_KEY,
        )
        unknown = sorted(set(keys) - set(allowed_keys))
        if unknown:
            raise ContractError(f"unknown assumption keys: {unknown}")
        reverse_mode = next(
            item.value for item in self.assumptions if item.key == "reverse_mode"
        )
        has_growth_rate = REVERSE_FIXED_GROWTH_RATE_KEY in keys
        has_duration = REVERSE_FIXED_DURATION_YEARS_KEY in keys
        if reverse_mode == "fixed_growth_rate":
            if not has_growth_rate or has_duration:
                raise ContractError(
                    "fixed_growth_rate requires reverse_fixed_growth_rate only"
                )
        else:
            if not has_duration or has_growth_rate:
                raise ContractError(
                    "fixed_duration requires reverse_fixed_duration_years only"
                )
        cost_of_equity = next(
            item.value for item in self.assumptions if item.key == "cost_of_equity"
        )
        maintenance_growth = next(
            item.value for item in self.assumptions if item.key == "maintenance_growth"
        )
        if cost_of_equity[0] <= maintenance_growth:
            raise ContractError("cost_of_equity must exceed maintenance_growth")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AssumptionSnapshot":
        if not isinstance(value, Mapping):
            raise ContractError("assumption snapshot must be a mapping")
        _require_no_unknown_fields(
            "assumption snapshot",
            value,
            ("version", "created_at", "assumptions"),
        )
        try:
            assumptions = tuple(
                Assumption.from_dict(item) for item in value["assumptions"]
            )
            return cls(
                version=value["version"],
                created_at=value["created_at"],
                assumptions=assumptions,
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("assumption snapshot", exc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "assumptions": [item.to_dict() for item in self.assumptions],
        }


def validate_assumption_snapshot(value: Mapping[str, Any]) -> AssumptionSnapshot:
    """Parse and validate a user assumption snapshot."""
    return AssumptionSnapshot.from_dict(value)


@dataclass(frozen=True)
class CurrentBusinessValue:
    epv_proxy_range: tuple[float, float]
    mature_multiple_range: tuple[float, float]
    anchor_divergence: str | None

    def __post_init__(self) -> None:
        _require_non_negative_range("epv_proxy_range", self.epv_proxy_range)
        _require_non_negative_range("mature_multiple_range", self.mature_multiple_range)
        if self.anchor_divergence is not None:
            _require_text("anchor_divergence", self.anchor_divergence)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CurrentBusinessValue":
        if not isinstance(value, Mapping):
            raise ContractError("current_business_value must be a mapping")
        _require_no_unknown_fields(
            "current_business_value",
            value,
            ("epv_proxy_range", "mature_multiple_range", "anchor_divergence"),
        )
        try:
            return cls(
                epv_proxy_range=tuple(value["epv_proxy_range"]),
                mature_multiple_range=tuple(value["mature_multiple_range"]),
                anchor_divergence=value.get("anchor_divergence"),
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("current_business_value", exc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "epv_proxy_range": list(self.epv_proxy_range),
            "mature_multiple_range": list(self.mature_multiple_range),
            "anchor_divergence": self.anchor_divergence,
        }


@dataclass(frozen=True)
class ReverseScenario:
    mode: str
    growth_rate: float | None = None
    duration_years: float | None = None
    implied_growth_rate: float | None = None
    implied_high_growth_duration: float | None = None

    def __post_init__(self) -> None:
        _require_choice("mode", self.mode, REVERSE_MODES)
        if self.mode == "fixed_growth_rate":
            _require_non_negative("growth_rate", self.growth_rate)
            implied_duration = _require_non_negative(
                "implied_high_growth_duration", self.implied_high_growth_duration
            )
            if implied_duration > MAX_REVERSE_DURATION_YEARS:
                raise ContractError(
                    f"implied_high_growth_duration must not exceed "
                    f"{MAX_REVERSE_DURATION_YEARS}"
                )
            if self.duration_years is not None or self.implied_growth_rate is not None:
                raise ContractError(
                    "fixed_growth_rate scenario has unexpected duration fields"
                )
        else:
            _require_number("duration_years", self.duration_years)
            if self.duration_years <= 0:
                raise ContractError("duration_years must be positive")
            if self.duration_years > MAX_REVERSE_DURATION_YEARS:
                raise ContractError(
                    f"duration_years must not exceed {MAX_REVERSE_DURATION_YEARS}"
                )
            _require_non_negative("implied_growth_rate", self.implied_growth_rate)
            if self.growth_rate is not None or self.implied_high_growth_duration is not None:
                raise ContractError(
                    "fixed_duration scenario has unexpected growth-rate fields"
                )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ReverseScenario":
        if not isinstance(value, Mapping):
            raise ContractError("reverse scenario must be a mapping")
        _require_no_unknown_fields(
            "reverse scenario",
            value,
            (
                "mode",
                "growth_rate",
                "duration_years",
                "implied_growth_rate",
                "implied_high_growth_duration",
            ),
        )
        try:
            return cls(
                mode=value["mode"],
                growth_rate=value.get("growth_rate"),
                duration_years=value.get("duration_years"),
                implied_growth_rate=value.get("implied_growth_rate"),
                implied_high_growth_duration=value.get("implied_high_growth_duration"),
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("reverse scenario", exc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "growth_rate": self.growth_rate,
            "duration_years": self.duration_years,
            "implied_growth_rate": self.implied_growth_rate,
            "implied_high_growth_duration": self.implied_high_growth_duration,
        }


@dataclass(frozen=True)
class SensitivityScenario:
    assumption_key: str
    value: float
    impact_range: tuple[float, float]

    def __post_init__(self) -> None:
        _require_text("assumption_key", self.assumption_key)
        _require_number("value", self.value)
        _require_range("impact_range", self.impact_range)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SensitivityScenario":
        if not isinstance(value, Mapping):
            raise ContractError("sensitivity scenario must be a mapping")
        _require_no_unknown_fields(
            "sensitivity scenario",
            value,
            ("assumption_key", "value", "impact_range"),
        )
        try:
            return cls(
                assumption_key=value["assumption_key"],
                value=value["value"],
                impact_range=tuple(value["impact_range"]),
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("sensitivity scenario", exc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assumption_key": self.assumption_key,
            "value": self.value,
            "impact_range": list(self.impact_range),
        }


@dataclass(frozen=True)
class DiagnosticProvenance:
    dossier_snapshot: str
    profile_version: str
    formula_version: str
    assumption_snapshot_version: str

    def __post_init__(self) -> None:
        _require_text("dossier_snapshot", self.dossier_snapshot)
        _require_text("profile_version", self.profile_version)
        _require_text("formula_version", self.formula_version)
        if self.assumption_snapshot_version != ASSUMPTION_SNAPSHOT_VERSION:
            raise ContractError("assumption_snapshot_version is unsupported")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DiagnosticProvenance":
        if not isinstance(value, Mapping):
            raise ContractError("provenance must be a mapping")
        _require_no_unknown_fields(
            "provenance",
            value,
            (
                "dossier_snapshot",
                "profile_version",
                "formula_version",
                "assumption_snapshot_version",
            ),
        )
        try:
            return cls(
                dossier_snapshot=value["dossier_snapshot"],
                profile_version=value["profile_version"],
                formula_version=value["formula_version"],
                assumption_snapshot_version=value["assumption_snapshot_version"],
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("provenance", exc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dossier_snapshot": self.dossier_snapshot,
            "profile_version": self.profile_version,
            "formula_version": self.formula_version,
            "assumption_snapshot_version": self.assumption_snapshot_version,
        }


@dataclass(frozen=True)
class GrowthExpectationDiagnostic:
    schema_version: str
    ticker: str
    valuation_date: str
    report_period: str
    as_of: str | None
    currency: str
    value_scale: str
    calculation_status: str
    quality_status: str
    decision_grade: str
    failure_kind: str | None
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    current_market_value: float | None
    assumption_snapshot: AssumptionSnapshot | None
    current_business_value: CurrentBusinessValue | None
    priced_growth_value_range: tuple[float, float] | None
    priced_growth_share_range: tuple[float, float] | None
    reverse_scenarios: tuple[ReverseScenario, ...]
    credible_growth_range: tuple[float, float] | None
    expectation_gap: tuple[float, float] | None
    expectation_overdraft: str | None
    sensitivity: tuple[SensitivityScenario, ...]
    evidence: tuple[str, ...]
    provenance: DiagnosticProvenance | None
    input_digest: str | None

    def __post_init__(self) -> None:
        if self.schema_version != GROWTH_EXPECTATION_SCHEMA_VERSION:
            raise ContractError("unsupported growth expectation schema version")
        try:
            canonical = canonical_ticker(self.ticker)
        except (TypeError, ValueError) as exc:
            raise ContractError("ticker is not canonical") from exc
        if canonical != self.ticker:
            raise ContractError("ticker must be canonical")
        _require_date("valuation_date", self.valuation_date)
        _require_report_period("report_period", self.report_period)
        if self.as_of is not None:
            _require_date("as_of", self.as_of)
        _require_choice("currency", self.currency, SUPPORTED_CURRENCIES)
        _require_choice("value_scale", self.value_scale, SUPPORTED_VALUE_SCALES)
        _require_choice("calculation_status", self.calculation_status, CALCULATION_STATUSES)
        _require_choice("quality_status", self.quality_status, DIAGNOSTIC_QUALITY_STATUSES)
        _require_choice("decision_grade", self.decision_grade, DECISION_GRADES)

        if self.failure_kind is not None:
            _require_choice("failure_kind", self.failure_kind, FAILURE_KINDS)
        reason_codes = _require_choice_tuple(
            "reason_codes", self.reason_codes, FAILURE_REASON_CODES
        )
        reasons = _require_text_tuple("reasons", self.reasons)
        warnings = _require_text_tuple("warnings", self.warnings)
        evidence = _require_text_tuple("evidence", self.evidence)
        object.__setattr__(self, "reason_codes", reason_codes)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "evidence", evidence)

        if self.assumption_snapshot is not None:
            if not isinstance(self.assumption_snapshot, AssumptionSnapshot):
                raise ContractError("assumption_snapshot has an invalid type")
        if self.current_business_value is not None:
            if not isinstance(self.current_business_value, CurrentBusinessValue):
                raise ContractError("current_business_value has an invalid type")
        if self.provenance is not None:
            if not isinstance(self.provenance, DiagnosticProvenance):
                raise ContractError("provenance has an invalid type")
        if not isinstance(self.reverse_scenarios, tuple) or any(
            not isinstance(item, ReverseScenario) for item in self.reverse_scenarios
        ):
            raise ContractError("reverse_scenarios must contain ReverseScenario records")
        if not isinstance(self.sensitivity, tuple) or any(
            not isinstance(item, SensitivityScenario) for item in self.sensitivity
        ):
            raise ContractError("sensitivity must contain SensitivityScenario records")
        _require_optional_positive("current_market_value", self.current_market_value)
        _require_optional_range("priced_growth_value_range", self.priced_growth_value_range)
        _require_optional_range("priced_growth_share_range", self.priced_growth_share_range)
        _require_optional_range("credible_growth_range", self.credible_growth_range)
        _require_optional_range("expectation_gap", self.expectation_gap)
        if self.credible_growth_range is not None and self.credible_growth_range[0] < 0:
            raise ContractError("credible_growth_range must be non-negative")
        if self.expectation_overdraft is not None:
            _require_choice(
                "expectation_overdraft",
                self.expectation_overdraft,
                EXPECTATION_OVERDRAFT_LEVELS,
            )
        if self.input_digest is not None:
            _require_digest("input_digest", self.input_digest)

        _validate_status_semantics(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GrowthExpectationDiagnostic":
        if not isinstance(value, Mapping):
            raise ContractError("diagnostic must be a mapping")
        _require_no_unknown_fields(
            "diagnostic",
            value,
            (
                "schema_version",
                "ticker",
                "valuation_date",
                "report_period",
                "as_of",
                "currency",
                "value_scale",
                "calculation_status",
                "quality_status",
                "decision_grade",
                "failure_kind",
                "reason_codes",
                "reasons",
                "warnings",
                "current_market_value",
                "assumptions",
                "assumption_snapshot",
                "current_business_value",
                "priced_growth_value_range",
                "priced_growth_share_range",
                "reverse_scenarios",
                "credible_growth_range",
                "expectation_gap",
                "expectation_overdraft",
                "sensitivity",
                "evidence",
                "provenance",
                "input_digest",
            ),
        )
        try:
            assumption_snapshot = (
                AssumptionSnapshot.from_dict(value["assumption_snapshot"])
                if value.get("assumption_snapshot") is not None
                else None
            )
            current_business_value = (
                CurrentBusinessValue.from_dict(value["current_business_value"])
                if value.get("current_business_value") is not None
                else None
            )
            reverse_scenarios = tuple(
                ReverseScenario.from_dict(item) for item in value.get("reverse_scenarios", [])
            )
            sensitivity = tuple(
                SensitivityScenario.from_dict(item) for item in value.get("sensitivity", [])
            )
            provenance = (
                DiagnosticProvenance.from_dict(value["provenance"])
                if value.get("provenance") is not None
                else None
            )
            priced_growth_value_range = (
                tuple(value["priced_growth_value_range"])
                if value.get("priced_growth_value_range") is not None
                else None
            )
            priced_growth_share_range = (
                tuple(value["priced_growth_share_range"])
                if value.get("priced_growth_share_range") is not None
                else None
            )
            credible_growth_range = (
                tuple(value["credible_growth_range"])
                if value.get("credible_growth_range") is not None
                else None
            )
            expectation_gap = (
                tuple(value["expectation_gap"])
                if value.get("expectation_gap") is not None
                else None
            )
            instance = cls(
                schema_version=value["schema_version"],
                ticker=value["ticker"],
                valuation_date=value["valuation_date"],
                report_period=value["report_period"],
                as_of=value.get("as_of"),
                currency=value["currency"],
                value_scale=value["value_scale"],
                calculation_status=value["calculation_status"],
                quality_status=value["quality_status"],
                decision_grade=value["decision_grade"],
                failure_kind=value.get("failure_kind"),
                reason_codes=value.get("reason_codes", []),
                reasons=value.get("reasons", []),
                warnings=value.get("warnings", []),
                current_market_value=value.get("current_market_value"),
                assumption_snapshot=assumption_snapshot,
                current_business_value=current_business_value,
                priced_growth_value_range=priced_growth_value_range,
                priced_growth_share_range=priced_growth_share_range,
                reverse_scenarios=reverse_scenarios,
                credible_growth_range=credible_growth_range,
                expectation_gap=expectation_gap,
                expectation_overdraft=value.get("expectation_overdraft"),
                sensitivity=sensitivity,
                evidence=value.get("evidence", []),
                provenance=provenance,
                input_digest=value.get("input_digest"),
            )
        except (KeyError, TypeError) as exc:
            _raise_invalid_structure("diagnostic", exc)
        if "assumptions" in value:
            if instance.assumption_snapshot is None:
                raise ContractError("assumptions requires assumption_snapshot")
            if not isinstance(value["assumptions"], Mapping):
                raise ContractError("assumptions must be a mapping")
            normalized = {
                key: (tuple(item) if isinstance(item, list) else item)
                for key, item in value["assumptions"].items()
            }
            if normalized != instance.assumptions:
                raise ContractError("assumptions does not match assumption_snapshot")
        return instance

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticker": self.ticker,
            "valuation_date": self.valuation_date,
            "report_period": self.report_period,
            "as_of": self.as_of,
            "currency": self.currency,
            "value_scale": self.value_scale,
            "calculation_status": self.calculation_status,
            "quality_status": self.quality_status,
            "decision_grade": self.decision_grade,
            "failure_kind": self.failure_kind,
            "reason_codes": list(self.reason_codes),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "current_market_value": self.current_market_value,
            "assumptions": self.assumptions,
            "assumption_snapshot": (
                self.assumption_snapshot.to_dict()
                if self.assumption_snapshot is not None
                else None
            ),
            "current_business_value": (
                self.current_business_value.to_dict()
                if self.current_business_value is not None
                else None
            ),
            "priced_growth_value_range": (
                list(self.priced_growth_value_range)
                if self.priced_growth_value_range is not None
                else None
            ),
            "priced_growth_share_range": (
                list(self.priced_growth_share_range)
                if self.priced_growth_share_range is not None
                else None
            ),
            "reverse_scenarios": [
                scenario.to_dict() for scenario in self.reverse_scenarios
            ],
            "credible_growth_range": (
                list(self.credible_growth_range)
                if self.credible_growth_range is not None
                else None
            ),
            "expectation_gap": (
                list(self.expectation_gap)
                if self.expectation_gap is not None
                else None
            ),
            "expectation_overdraft": self.expectation_overdraft,
            "sensitivity": [scenario.to_dict() for scenario in self.sensitivity],
            "evidence": list(self.evidence),
            "provenance": self.provenance.to_dict() if self.provenance is not None else None,
            "input_digest": self.input_digest,
        }

    @property
    def assumptions(self) -> dict[str, Any] | None:
        if self.assumption_snapshot is None:
            return None
        return {
            item.key: item.value
            for item in self.assumption_snapshot.assumptions
        }


def _validate_status_semantics(diagnostic: "GrowthExpectationDiagnostic") -> None:
    status = diagnostic.calculation_status
    numeric_conclusions = (
        diagnostic.current_market_value is not None
        or diagnostic.current_business_value is not None
        or diagnostic.priced_growth_value_range is not None
        or diagnostic.priced_growth_share_range is not None
        or bool(diagnostic.reverse_scenarios)
        or diagnostic.credible_growth_range is not None
        or diagnostic.expectation_gap is not None
        or bool(diagnostic.sensitivity)
    )

    if status in ("clean", "degraded"):
        if diagnostic.failure_kind is not None:
            raise ContractError(f"{status} result must not have failure_kind")
        if diagnostic.reason_codes:
            raise ContractError(f"{status} result must have empty reason_codes")
        if diagnostic.quality_status != "warning":
            raise ContractError(f"{status} result requires quality_status='warning'")
        if diagnostic.decision_grade != "diagnostic":
            raise ContractError("decision_grade must be 'diagnostic'")
        if diagnostic.assumption_snapshot is None:
            raise ContractError(f"{status} result requires assumption_snapshot")
        if diagnostic.provenance is None:
            raise ContractError(f"{status} result requires provenance")
        if diagnostic.input_digest is None:
            raise ContractError(f"{status} result requires input_digest")
        if diagnostic.current_market_value is None:
            raise ContractError(f"{status} result requires current_market_value")
        if diagnostic.as_of is None:
            raise ContractError(f"{status} result requires as_of")
        if diagnostic.current_business_value is None:
            raise ContractError(f"{status} result requires current_business_value")
        if diagnostic.priced_growth_value_range is None:
            raise ContractError(f"{status} result requires priced_growth_value_range")
        if diagnostic.priced_growth_share_range is None:
            raise ContractError(f"{status} result requires priced_growth_share_range")
        if not diagnostic.reverse_scenarios:
            raise ContractError(f"{status} result requires reverse_scenarios")
        if diagnostic.credible_growth_range is None:
            raise ContractError(f"{status} result requires credible_growth_range")
        if diagnostic.expectation_gap is None:
            raise ContractError(f"{status} result requires expectation_gap")
        if diagnostic.expectation_overdraft not in EXPECTATION_OVERDRAFT_RESULT_LEVELS:
            raise ContractError(
                f"{status} result requires a resolved expectation_overdraft"
            )
        if not diagnostic.sensitivity:
            raise ContractError(f"{status} result requires sensitivity")
        _validate_reverse_mode_exclusivity(diagnostic)

    if status == "clean":
        if diagnostic.reasons:
            raise ContractError("clean result must have empty reasons")
        if diagnostic.warnings:
            raise ContractError("clean result must have empty warnings")

    if status == "degraded":
        if not diagnostic.warnings:
            raise ContractError("degraded result requires warnings")

    if status in ("not_evaluable", "failed"):
        if diagnostic.failure_kind is None:
            raise ContractError(f"{status} result requires failure_kind")
        if not diagnostic.reason_codes:
            raise ContractError(f"{status} result requires reason_codes")
        if not diagnostic.reasons:
            raise ContractError(f"{status} result requires reasons")
        if FAILURE_TO_STATUS[diagnostic.failure_kind] != status:
            raise ContractError(
                f"failure_kind {diagnostic.failure_kind!r} is inconsistent "
                f"with {status}"
            )
        allowed_codes = FAILURE_KIND_REASON_CODES[diagnostic.failure_kind]
        invalid_codes = sorted(set(diagnostic.reason_codes) - allowed_codes)
        if invalid_codes:
            raise ContractError(
                f"reason_codes inconsistent with failure_kind: {invalid_codes}"
            )
        if diagnostic.provenance is None:
            raise ContractError(f"{status} result requires provenance")
        if diagnostic.input_digest is None:
            raise ContractError(f"{status} result requires input_digest")
        if numeric_conclusions:
            raise ContractError(f"{status} result must not contain numeric conclusions")
        if diagnostic.expectation_overdraft not in (None, "not_evaluable"):
            raise ContractError(
                f"{status} result requires expectation_overdraft "
                "to be null or 'not_evaluable'"
            )

    if status == "failed":
        if diagnostic.quality_status != "failed":
            raise ContractError("failed result requires quality_status='failed'")
        if diagnostic.provenance is None:
            raise ContractError("failed result requires provenance")
        if diagnostic.assumption_snapshot is None:
            raise ContractError("failed result requires assumption_snapshot")

    if status == "not_evaluable":
        if diagnostic.quality_status != "warning":
            raise ContractError("not_evaluable result requires quality_status='warning'")


def _validate_reverse_mode_exclusivity(diagnostic: "GrowthExpectationDiagnostic") -> None:
    if not diagnostic.reverse_scenarios:
        return
    modes = {scenario.mode for scenario in diagnostic.reverse_scenarios}
    if len(modes) != 1:
        raise ContractError("reverse_scenarios must share one reverse mode")
    if diagnostic.assumption_snapshot is None:
        return
    reverse_mode = next(
        item.value
        for item in diagnostic.assumption_snapshot.assumptions
        if item.key == "reverse_mode"
    )
    if next(iter(modes)) != reverse_mode:
        raise ContractError("reverse_scenarios mode must match assumption reverse_mode")
    if reverse_mode == "fixed_growth_rate":
        fixed_rates = next(
            item.value
            for item in diagnostic.assumption_snapshot.assumptions
            if item.key == REVERSE_FIXED_GROWTH_RATE_KEY
        )
        scenario_rates = {scenario.growth_rate for scenario in diagnostic.reverse_scenarios}
        if scenario_rates != set(fixed_rates):
            raise ContractError(
                "reverse scenarios must cover reverse_fixed_growth_rate scenarios"
            )
    else:
        fixed_durations = next(
            item.value
            for item in diagnostic.assumption_snapshot.assumptions
            if item.key == REVERSE_FIXED_DURATION_YEARS_KEY
        )
        scenario_durations = {
            scenario.duration_years for scenario in diagnostic.reverse_scenarios
        }
        if scenario_durations != set(fixed_durations):
            raise ContractError(
                "reverse scenarios must cover reverse_fixed_duration_years scenarios"
            )


def validate_diagnostic(value: Mapping[str, Any]) -> GrowthExpectationDiagnostic:
    """Parse and validate a growth expectation diagnostic payload."""
    return GrowthExpectationDiagnostic.from_dict(value)


def compute_input_digest(
    *,
    ticker: str,
    input_payload: Mapping[str, Any],
    assumption_snapshot: Mapping[str, Any],
    formula_version: str,
    dossier_snapshot: str,
    profile_version: str,
) -> str:
    """Return the canonical digest binding the full diagnostic identity."""
    parsed_input = DiagnosticInput.from_dict(input_payload).to_dict()
    parsed_snapshot = AssumptionSnapshot.from_dict(assumption_snapshot).to_dict()
    binding = {
        "ticker": canonical_ticker(ticker),
        "dossier_snapshot": _require_text("dossier_snapshot", dossier_snapshot),
        "profile_version": _require_text("profile_version", profile_version),
        "input": parsed_input,
        "assumption_snapshot": parsed_snapshot,
        "formula_version": _require_text("formula_version", formula_version),
        "assumption_snapshot_version": ASSUMPTION_SNAPSHOT_VERSION,
    }
    return _payload_sha256(binding)


def validate_diagnostic_binding(
    value: Mapping[str, Any],
    *,
    ticker: str,
    input_payload: Mapping[str, Any],
    assumption_snapshot: Mapping[str, Any],
    formula_version: str,
    dossier_snapshot: str,
    profile_version: str,
) -> GrowthExpectationDiagnostic:
    """Validate a diagnostic and confirm it binds to the exact input payload."""
    diagnostic = validate_diagnostic(value)
    try:
        canonical = canonical_ticker(ticker)
    except (TypeError, ValueError) as exc:
        raise ContractError("ticker is not canonical") from exc
    if diagnostic.provenance is None:
        raise ContractError("provenance is required for input_digest binding")
    if diagnostic.ticker != canonical:
        raise ContractError("diagnostic ticker mismatch")
    if diagnostic.provenance.dossier_snapshot != dossier_snapshot:
        raise ContractError("provenance dossier_snapshot mismatch")
    if diagnostic.provenance.profile_version != profile_version:
        raise ContractError("provenance profile_version mismatch")
    if diagnostic.provenance.formula_version != formula_version:
        raise ContractError("provenance formula_version mismatch")
    if diagnostic.provenance.assumption_snapshot_version != ASSUMPTION_SNAPSHOT_VERSION:
        raise ContractError("provenance assumption_snapshot_version mismatch")
    expected = compute_input_digest(
        ticker=canonical,
        input_payload=input_payload,
        assumption_snapshot=assumption_snapshot,
        formula_version=formula_version,
        dossier_snapshot=dossier_snapshot,
        profile_version=profile_version,
    )
    if diagnostic.input_digest != expected:
        raise ContractError("input_digest does not match bound input")
    parsed_input = validate_diagnostic_input(input_payload)
    if parsed_input.ticker != canonical:
        raise ContractError("input ticker mismatch")
    if diagnostic.valuation_date != parsed_input.valuation_date:
        raise ContractError("valuation_date mismatch")
    if diagnostic.report_period != parsed_input.report_period:
        raise ContractError("report_period mismatch")
    if diagnostic.as_of is not None and diagnostic.as_of != parsed_input.as_of:
        raise ContractError("as_of mismatch")
    if diagnostic.currency != parsed_input.currency:
        raise ContractError("currency mismatch")
    if diagnostic.value_scale != parsed_input.value_scale:
        raise ContractError("value_scale mismatch")
    if (
        diagnostic.current_market_value is not None
        and diagnostic.current_market_value != parsed_input.current_market_value
    ):
        raise ContractError("current_market_value mismatch")
    if diagnostic.calculation_status in ("clean", "degraded"):
        if any(
            source.degradation_status == "failed" for source in parsed_input.sources
        ):
            raise ContractError(
                f"{diagnostic.calculation_status} result cannot use failed sources"
            )
    if diagnostic.calculation_status == "clean":
        if any(source.freshness != "fresh" for source in parsed_input.sources):
            raise ContractError("clean result requires all sources fresh")
        if any(
            source.degradation_status != "clean" for source in parsed_input.sources
        ):
            raise ContractError("clean result requires clean source degradation_status")
    parsed_snapshot = validate_assumption_snapshot(assumption_snapshot)
    if (
        diagnostic.assumption_snapshot is not None
        and diagnostic.assumption_snapshot.to_dict() != parsed_snapshot.to_dict()
    ):
        raise ContractError("assumption snapshot does not match bound input")
    return diagnostic


@dataclass(frozen=True)
class ApplicabilityVerdict:
    applicable: bool
    calculation_status: str | None
    failure_kind: str | None
    reason_codes: tuple[str, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "applicable": self.applicable,
            "calculation_status": self.calculation_status,
            "failure_kind": self.failure_kind,
            "reason_codes": list(self.reason_codes),
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
        }


def evaluate_applicability(
    input: DiagnosticInput,
    *,
    industry: str | None = None,
    normalized_earnings: float | None = None,
) -> ApplicabilityVerdict:
    """Evaluate the deterministic model-applicability gate.

    ``input`` SHALL be a validated ``DiagnosticInput``, so unit/report-period
    alignment is derived from its field-level sources instead of being passed
    as trusted boolean flags by callers.
    """
    if not isinstance(input, DiagnosticInput):
        return ApplicabilityVerdict(
            applicable=False,
            calculation_status="not_evaluable",
            failure_kind="data_insufficient",
            reason_codes=("data_missing",),
            reasons=("a validated DiagnosticInput is required",),
            warnings=(),
        )
    if _is_financial_industry(industry):
        return ApplicabilityVerdict(
            applicable=False,
            calculation_status="not_evaluable",
            failure_kind="model_not_applicable",
            reason_codes=("model_out_of_scope",),
            reasons=("financial industry is outside the V0 model",),
            warnings=(),
        )
    if (
        normalized_earnings is None
        or isinstance(normalized_earnings, bool)
        or not isinstance(normalized_earnings, (int, float))
        or not math.isfinite(normalized_earnings)
        or normalized_earnings <= 0
    ):
        return ApplicabilityVerdict(
            applicable=False,
            calculation_status="not_evaluable",
            failure_kind="data_insufficient",
            reason_codes=("data_missing",),
            reasons=("positive finite normalized earnings are required",),
            warnings=(),
        )
    failed_fields = sorted(
        source.field for source in input.sources if source.degradation_status == "failed"
    )
    if failed_fields:
        return ApplicabilityVerdict(
            applicable=False,
            calculation_status="not_evaluable",
            failure_kind="data_insufficient",
            reason_codes=("data_source_failed",),
            reasons=(f"failed source fields: {failed_fields}",),
            warnings=(),
        )
    warnings: list[str] = []
    if not industry or not isinstance(industry, str) or not industry.strip():
        warnings.append("industry_unknown")
    units_aligned = all(
        source.currency == input.currency and source.value_scale == input.value_scale
        for source in input.sources
    )
    periods_aligned = all(
        source.report_period == input.report_period and source.as_of == input.as_of
        for source in input.sources
    )
    if not units_aligned:
        warnings.append("units_alignment_unverified")
    if not periods_aligned:
        warnings.append("periods_alignment_unverified")
    return ApplicabilityVerdict(
        applicable=True,
        calculation_status=None,
        failure_kind=None,
        reason_codes=(),
        reasons=(),
        warnings=tuple(warnings),
    )
