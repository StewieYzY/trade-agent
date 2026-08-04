"""现有 AkShare fetcher chain 的 qualification adapter。

这是基线 consumer-chain probe，不把 fetcher 内部的 fallback 结果伪装成
单一 provider 的独立证明。需要精确到 provider 的比较时，必须再注入显式
provider adapter；当前模块只复用项目已经存在的、经过测试的 fetcher contract。
"""
from __future__ import annotations

from typing import Any

from scripts.provider_qualification import ProviderAdapter, ProbeCase


def _latest(values: Any) -> Any:
    if isinstance(values, (list, tuple)):
        return values[-1] if values else None
    return values


def _numeric_meta(unit: str = "CNY") -> dict[str, str]:
    return {"unit": unit, "currency": "CNY"}


def _financial_payload(data: dict, section: str, fields: tuple[str, ...]) -> dict:
    years = data.get("years") or []
    section_data = data.get(section) or {}
    payload: dict[str, Any] = {
        "report_period": str(years[-1]) if years else None,
        "_fields": {
            "report_period": {"as_of": str(years[-1]) if years else None},
        },
    }
    for field in fields:
        values = section_data.get(field)
        payload[field] = _latest(values)
        payload["_fields"][field] = _numeric_meta()
    return payload


def _invoke(case: ProbeCase) -> dict:
    code = case.ticker.split(".")[0]

    if case.method in {"static_info", "quote", "calc_indexes"}:
        from data.fetchers.basic import BasicFetcher

        data = BasicFetcher().fetch(code)
        payload = {
            "code": data.get("code"),
            "name": data.get("name"),
            "market": case.market,
            "last_price": data.get("price"),
            "previous_close": None,
            "volume": None,
            "turnover_rate": None,
            "pe_ttm": data.get("pe"),
            "pb": data.get("pb"),
            "dividend_yield": None,
            "_fields": {
                "last_price": _numeric_meta("CNY/share"),
                "pe_ttm": {"unit": "multiple"},
                "pb": {"unit": "multiple"},
            },
        }
        return payload

    if case.method == "historical_kline":
        from data.fetchers.kline import KlineFetcher

        data = KlineFetcher().fetch(code)
        dates = data.get("dates") or []
        return {
            "dates": dates,
            "close": data.get("close"),
            "volume": data.get("volume"),
            "turnover_rate": data.get("turnover_rate"),
            "_fields": {
                "dates": {"as_of": str(dates[-1]) if dates else None},
                "close": _numeric_meta("CNY/share"),
                "volume": _numeric_meta("shares"),
                "turnover_rate": {"unit": "%"},
            },
        }

    if case.method in {"income_statement", "balance_sheet", "cash_flow"}:
        from data.fetchers.financials import FinancialsFetcher

        data = FinancialsFetcher().fetch(code)
        section = {
            "income_statement": "income",
            "balance_sheet": "balance_sheet",
            "cash_flow": "cash_flow",
        }[case.method]
        aliases = {
            "income_statement": ("revenue", "net_profit"),
            "balance_sheet": ("TOTAL_ASSETS", "TOTAL_CURRENT_LIAB", "GOODWILL"),
            "cash_flow": ("NETCASH_OPERATE", "CONSTRUCT_LONG_ASSET"),
        }
        return _financial_payload(data, section, aliases[case.method])

    if case.method == "historical_valuation":
        from data.fetchers.valuation import ValuationFetcher

        data = ValuationFetcher().fetch(code)
        return {
            "as_of": None,
            "pe_ttm": data.get("pe_ttm"),
            "pb": data.get("pb"),
            "_fields": {
                "pe_ttm": {"unit": "multiple"},
                "pb": {"unit": "multiple"},
            },
        }

    # Existing project bindings do not expose a ticker-aligned industry valuation
    # or consensus contract. Do not call a full-market mean or fabricate a value.
    raise NotImplementedError(
        f"{case.method} is not exposed as a ticker-aligned baseline contract"
    )


def get_provider_adapters() -> list[ProviderAdapter]:
    return [
        ProviderAdapter(
            provider_family="baseline",
            provider="akshare-existing-fetcher-chain",
            invoke=_invoke,
            available=True,
            documentation_status="implemented-consumer-chain",
            availability_reason="uses existing project fetchers; source-level provider remains nested",
        )
    ]
