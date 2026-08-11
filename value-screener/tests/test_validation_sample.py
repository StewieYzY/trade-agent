"""G1 300-sample validation 的离线 contract-fixture 测试。"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _selector_module():
    return importlib.import_module("data.lib.validation_sample")


def _record(
    ticker: str,
    *,
    name: str = "普通股份",
    market_cap: float | None = 100e8,
    pe_ttm: float | None = 12.0,
    chg_60d: float | None = 5.0,
    status: str = "complete",
    field_statuses: dict[str, str] | None = None,
) -> dict:
    return {
        "ticker": ticker,
        "name": name,
        "market_cap": market_cap,
        "pe_ttm": pe_ttm,
        "chg_60d": chg_60d,
        "status": status,
        "field_statuses": field_statuses or {},
        "provenance": {
            "source": "fixture/reference",
            "as_of": "2026-08-07",
            "retrieved_at": "2026-08-07T00:00:00+00:00",
        },
    }


def _industry_mapping(
    mapping: dict[str, str],
    *,
    status: str = "complete",
) -> dict:
    return {
        "status": status,
        "mapping": mapping,
        "attempted_sources": ["fixture/reference"],
        "provenance": {
            "source": "fixture/reference",
            "as_of": "2026-08-07",
            "retrieved_at": "2026-08-07T00:00:00+00:00",
        },
    }


def _run(records: list[dict], industries: dict, **kwargs) -> dict:
    module = _selector_module()
    return module.select_validation_sample(
        records,
        industries,
        run_id="fixture-sample-run",
        profile_version="g1-fixture-v1",
        as_of="2026-08-07",
        **kwargs,
    )


class _IndustryMapResult(dict):
    """当前 main data.lib.industry_mapper.IndustryMapResult 的最小形状。"""

    def __init__(self, mapping, *, status="available", attempted_sources=None):
        super().__init__(mapping)
        self.status = status
        self.attempted_sources = attempted_sources or []


def test_selector_accepts_industry_map_result_and_preserves_canonical_statuses():
    """Bug caught: current status vocabulary/direct mapper shape are coerced away."""
    records = [
        _record(
            "600001",
            market_cap=40e8,
            pe_ttm=-2.0,
            chg_60d=5.0,
            status="available",
            field_statuses={
                "market_cap": "available",
                "pe_ttm": "available",
                "chg_60d": "available",
            },
        ),
        _record(
            "000002",
            market_cap=40e8,
            pe_ttm=-2.0,
            chg_60d=5.0,
            status="partial",
            field_statuses={
                "market_cap": "partial",
                "pe_ttm": "partial",
                "chg_60d": "partial",
            },
        ),
        _record(
            "000003",
            market_cap=40e8,
            pe_ttm=-2.0,
            chg_60d=5.0,
            status="permission_denied",
            field_statuses={
                "market_cap": "permission_denied",
                "pe_ttm": "permission_denied",
                "chg_60d": "permission_denied",
            },
        ),
        _record("000004", market_cap=40e8, pe_ttm=-2.0, chg_60d=5.0),
    ]
    industries = _IndustryMapResult(
        {
            "600001.SH": "银行",
            "000002.SZ": "白酒",
            "000003.SZ": "白酒",
        },
        status="partial",
        attempted_sources=["eastmoney"],
    )

    result = _run(records, industries, seed=3)

    selected = {item["ticker"]: item for item in result["sample"]}
    assert selected["600001.SH"]["status"] == "available"
    assert selected["600001.SH"]["industry_status"] == "complete"
    assert selected["000002.SZ"]["status"] == "partial"
    assert selected["000002.SZ"]["industry_status"] == "complete"
    assert selected["000003.SZ"]["status"] == "permission_denied"
    assert selected["000003.SZ"]["industry_status"] == "complete"
    assert selected["000004.SZ"]["industry_status"] == "partial"
    assert result["design"]["industry_mapping_status"] == "partial"
    assert result["provenance"]["attempted_sources"] == ["eastmoney"]
    assert result["design"]["strata"]["risk:smallcap_h3"]["unavailable_reasons"] == {
        "partial": 1,
        "permission_denied": 1,
    }


def test_selector_preserves_stale_field_status():
    """Bug caught: staged runtime/canonical consumer treat stale as explicit unavailable."""
    records = [
        _record(
            "600001",
            market_cap=40e8,
            pe_ttm=-2.0,
            chg_60d=5.0,
            field_statuses={
                "market_cap": "stale",
                "pe_ttm": "stale",
                "chg_60d": "stale",
            },
        )
    ]

    result = _run(
        records,
        _industry_mapping({"600001.SH": "银行"}),
        seed=3,
    )

    selected = {item["ticker"]: item for item in result["sample"]}
    assert selected["600001.SH"]["field_statuses"]["market_cap"] == "stale"
    assert result["design"]["strata"]["risk:smallcap_h3"]["unavailable_reasons"] == {
        "stale": 1
    }


def test_source_failed_mapping_entries_do_not_promote_industry_identity():
    """Bug caught: a failed industry source is not rescued by stale/present entries."""
    records = [_record("600001"), _record("000002")]
    industries = _industry_mapping({"600001.SH": "银行"}, status="source_failed")

    result = _run(records, industries, seed=3)

    selected = {item["ticker"]: item for item in result["sample"]}
    assert selected["600001.SH"]["industry"] == "_unmapped"
    assert selected["600001.SH"]["industry_status"] == "source_failed"
    assert result["design"]["real_industry_coverage"] == 0
    assert result["design"]["full_market_qualified_size"] == 0


def test_invalid_industry_value_is_not_record_not_found():
    """Bug caught: blank/non-string industry is invalid, not a clean record absence."""
    records = [_record("600001"), _record("000002")]
    industries = _industry_mapping({"600001.SH": "", "000002.SZ": None})

    result = _run(records, industries, seed=3)

    selected = {item["ticker"]: item for item in result["sample"]}
    assert selected["600001.SH"]["industry_status"] == "invalid_value"
    assert selected["000002.SZ"]["industry_status"] == "invalid_value"
    assert result["design"]["real_industry_coverage"] == 0
    assert result["design"]["full_market_qualified_size"] == 0


def test_selector_is_deterministic_and_merges_duplicate_strata():
    """Bug caught: reader order or overlapping strata changes output/duplicates ticker."""
    records = [
        _record("600001", name="ST 重叠", market_cap=40e8, pe_ttm=-2.0, chg_60d=90.0),
        _record("600001.SH", name="ST 重叠", market_cap=40e8, pe_ttm=-2.0, chg_60d=90.0),
        _record("000002", chg_60d=3.0),
        _record("000003", chg_60d=2.0),
    ]
    industries = _industry_mapping(
        {
            "600001.SH": "银行",
            "000002.SZ": "白酒",
            "000003.SZ": "白酒",
        }
    )

    forward = _run(records, industries, seed=7)
    backward = _run(list(reversed(records)), industries, seed=7)

    assert forward == backward
    selected = {item["ticker"]: item for item in forward["sample"]}
    assert list(selected) == sorted(selected)
    assert [item["ticker"] for item in forward["sample"]].count("600001.SH") == 1
    assert selected["600001.SH"]["strata"] == [
        "industry:银行",
        "risk:st_h1",
        "risk:smallcap_h3",
        "risk:negative_pe_h8",
        "risk:overheat_60d",
    ]


def test_selector_exposes_unmapped_and_unavailable_risk_values_without_defaults():
    """Bug caught: missing/invalid fields become zero or silently count as coverage."""
    records = [
        _record("600001", market_cap=None, field_statuses={"market_cap": "invalid_value"}),
        _record("000002", pe_ttm=None, field_statuses={"pe_ttm": "record_not_found"}),
        _record("000003", chg_60d=None, status="degraded", field_statuses={"chg_60d": "source_failed"}),
        _record("000004", chg_60d=80.0),
    ]
    industries = _industry_mapping(
        {
            "600001.SH": "银行",
            "000002.SZ": "白酒",
            "000003.SZ": "白酒",
        }
    )

    result = _run(records, industries, seed=11)

    selected = {item["ticker"]: item for item in result["sample"]}
    assert selected["000004.SZ"]["industry"] == "_unmapped"
    assert result["design"]["real_industry_coverage"] == 2
    assert result["design"]["unmapped_count"] == 1
    assert result["design"]["strata"]["risk:smallcap_h3"]["unavailable_reasons"] == {
        "invalid_value": 1
    }
    assert result["design"]["strata"]["risk:negative_pe_h8"]["unavailable_reasons"] == {
        "record_not_found": 1
    }
    assert result["design"]["strata"]["risk:overheat_60d"]["unavailable_reasons"] == {
        "source_failed": 1
    }
    assert selected["000003.SZ"]["status"] == "degraded"


def test_selector_preserves_mapping_source_failure_without_counting_unmapped_as_industry():
    """Bug caught: failed industry source is misreported as successful unmapped data."""
    records = [_record("600001"), _record("000002")]
    industries = _industry_mapping({}, status="source_failed")

    result = _run(records, industries, seed=3)

    assert result["design"]["industry_mapping_status"] == "source_failed"
    assert result["design"]["real_industry_coverage"] == 0
    assert result["design"]["unmapped_count"] == 2
    assert {item["industry_status"] for item in result["sample"]} == {"source_failed"}
    assert result["provenance"]["attempted_sources"] == ["fixture/reference"]


@pytest.mark.parametrize(
    ("count", "expected_eligible", "expected_semantics"),
    [
        (299, False, "insufficient/development"),
        (300, True, "full_market"),
    ],
)
def test_full_market_semantics_require_at_least_300_unique_valid_tickers(
    count: int,
    expected_eligible: bool,
    expected_semantics: str,
):
    """Bug caught: duplicates or a subset are reported as a full-market sample."""
    records = [
        _record(f"{600000 + index:06d}")
        for index in range(count)
    ]
    industries = _industry_mapping(
        {f"{600000 + index:06d}.SH": "银行" for index in range(count)}
    )
    module = _selector_module()
    config = module.SampleSelectionConfig(
        industry_quota_total=count,
        industry_cap=count,
        risk_st_max=0,
        risk_smallcap_max=0,
        risk_negative_pe_max=0,
        risk_overheat_max=0,
    )

    result = _run(records, industries, config=config)

    assert result["design"]["sample_size"] == count
    assert result["design"]["full_market_eligible"] is expected_eligible
    assert result["design"]["sample_size_semantics"] == expected_semantics


def test_full_market_threshold_cannot_be_lowered_below_300():
    """Bug caught: caller lowers the full-market threshold below the G1 contract."""
    module = _selector_module()
    config = module.SampleSelectionConfig(minimum_full_market_size=299)

    with pytest.raises(ValueError, match="at least 300"):
        _run([_record("600001")], _industry_mapping({"600001.SH": "银行"}), config=config)


@pytest.mark.parametrize("mapping_status", ["complete", "source_failed"])
def test_unmapped_records_cannot_unlock_full_market_semantics(mapping_status: str):
    """Bug caught: unmapped or failed industry records are counted toward the 300 Gate."""
    count = 300
    records = [_record(f"{600000 + index:06d}") for index in range(count)]
    industries = _industry_mapping({}, status=mapping_status)
    module = _selector_module()
    config = module.SampleSelectionConfig(
        industry_quota_total=count,
        industry_cap=count,
        risk_st_max=0,
        risk_smallcap_max=0,
        risk_negative_pe_max=0,
        risk_overheat_max=0,
    )

    result = _run(records, industries, config=config)

    assert result["design"]["sample_size"] == 300
    assert result["design"]["full_market_qualified_size"] == 0
    assert result["design"]["full_market_eligible"] is False
    assert result["design"]["sample_size_semantics"] == "insufficient/development"


def test_fixture_envelope_carries_identity_and_isolated_provenance():
    """Bug caught: fixture output lacks replay identity or looks like live evidence."""
    result = _run(
        [_record("600001"), _record("000002")],
        _industry_mapping({"600001.SH": "银行", "000002.SZ": "白酒"}),
    )

    assert result["schema_version"] == "g1-validation-sample/v1"
    assert result["artifact_type"] == "fixture/reference"
    assert result["mode"] == "simulated/development"
    assert result["run_id"] == "fixture-sample-run"
    assert result["profile_version"] == "g1-fixture-v1"
    assert result["as_of"] == "2026-08-07"
    assert len(result["input_ticker_set_hash"]) == 12
    assert result["provenance"]["not_live_provider_evidence"] is True
    assert "provider_qualification" not in result
    assert "canonical_promotion" not in result


def test_selector_accepts_reader_iterable_without_external_imports_or_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """Bug caught: offline selector reaches provider code or writes runtime artifacts."""
    import builtins

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".", 1)[0] in {"akshare", "httpx", "openai"}:
            raise AssertionError(f"offline selector imported forbidden dependency: {name}")
        return real_import(name, *args, **kwargs)

    def reader():
        yield _record("600001")
        yield _record("000002")

    sys.modules.pop("data.lib.validation_sample", None)
    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.chdir(tmp_path)

    result = _run(
        reader(),
        _industry_mapping({"600001.SH": "银行", "000002.SZ": "白酒"}),
    )

    assert [item["ticker"] for item in result["sample"]] == ["000002.SZ", "600001.SH"]
    assert list(tmp_path.iterdir()) == []
