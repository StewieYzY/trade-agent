"""Council 显式输入的语义 preflight 回归测试。"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from council.debate import _validate_council_input, run_debate


def _valid_dossier(ticker: str = "002156.SZ") -> dict:
    return {
        "core_snapshot": {
            "ticker": ticker,
            "name": "通富微电",
            "market_cap": 10000000000,
            "pe_ttm": 20.0,
            "roe_3y": [10.0, 11.0, 12.0],
            "net_margin": 5.0,
        },
        "research_dossier": {
            "main_business": {
                "code": ticker.split(".")[0],
                "main_business_text": "集成电路封装测试",
            },
            "degraded_fields": [],
        },
        "pledge": None,
    }


def _invalid_cases() -> list[tuple[str, dict, str]]:
    return [
        (
            "explicit error shell",
            {"error": "insufficient_data", "missing_fields": ["pe_ttm"]},
            "insufficient_data",
        ),
        (
            "empty core snapshot",
            {
                "core_snapshot": {},
                "research_dossier": {"main_business": {"code": "002156"}},
            },
            "no_evidence",
        ),
        (
            "non-dict core snapshot",
            {
                "core_snapshot": [],
                "research_dossier": {"main_business": {"code": "002156"}},
            },
            "no_evidence",
        ),
        (
            "missing financial floor",
            {
                "core_snapshot": {
                    "name": "通富微电",
                    "market_cap": 10000000000,
                    "pe_ttm": None,
                    "roe_3y": [],
                    "net_margin": None,
                },
                "research_dossier": {"main_business": {"code": "002156"}},
            },
            "insufficient_data",
        ),
        (
            "main business error shell",
            {
                "core_snapshot": {
                    "name": "通富微电",
                    "market_cap": 10000000000,
                    "pe_ttm": 20.0,
                    "roe_3y": [10.0, 11.0, 12.0],
                    "net_margin": 5.0,
                },
                "research_dossier": {
                    "main_business": {"__error__": True, "reason": "source_failed"},
                },
            },
            "no_evidence",
        ),
        (
            "main business identity only",
            {
                "core_snapshot": {
                    "name": "通富微电",
                    "market_cap": 10000000000,
                    "pe_ttm": 20.0,
                    "roe_3y": [10.0, 11.0, 12.0],
                    "net_margin": 5.0,
                },
                "research_dossier": {"main_business": {"code": "002156"}},
            },
            "no_evidence",
        ),
        (
            "core time series contains only nulls",
            {
                "core_snapshot": {
                    "name": "通富微电",
                    "market_cap": 10000000000,
                    "pe_ttm": 20.0,
                    "roe_3y": [None, None, None],
                    "net_margin": 5.0,
                },
                "research_dossier": {
                    "main_business": {
                        "code": "002156",
                        "main_business_text": "集成电路封装测试",
                    },
                },
            },
            "insufficient_data",
        ),
        (
            "ticker mismatch",
            {
                "core_snapshot": {
                    "ticker": "600009.SH",
                    "name": "上海机场",
                    "market_cap": 10000000000,
                    "pe_ttm": 20.0,
                    "roe_3y": [10.0, 11.0, 12.0],
                    "net_margin": 5.0,
                },
                "research_dossier": {"main_business": {"code": "600009"}},
            },
            "no_evidence",
        ),
    ]


def test_explicit_dossier_high_severity_missing_time_basis_fails_closed():
    """显式 dossier 的高严重度事实缺时间基准 → 进入 preflight 即 fail closed."""
    from council.fact_grounding import FactContractError
    dossier = _valid_dossier()
    dossier["research_dossier"]["main_business"] = {
        "code": "002156",
        "by_industry": [{"name": "封装测试", "revenue": 1.0, "revenue_ratio": 1.0}],
    }
    with pytest.raises(FactContractError, match="time basis|report_period"):
        _validate_council_input("002156.SZ", dossier)


def test_explicit_dossier_fake_fact_contract_still_fails_closed():
    """caller 注入伪造 fact_contract 不能绕过 raw payload 的事实契约校验."""
    from council.fact_grounding import FactContractError
    dossier = _valid_dossier()
    dossier["research_dossier"]["main_business"] = {
        "code": "002156",
        "by_industry": [{"name": "封装测试", "revenue": 1.0, "revenue_ratio": 1.0}],
    }
    dossier["fact_contract"] = {
        "clean": True,
        "failed": False,
        "facts": [],
        "role_status": [],
    }
    with pytest.raises(FactContractError, match="time basis|report_period"):
        _validate_council_input("002156.SZ", dossier)


def test_explicit_dossier_quality_is_evaluable_without_mutating_input():
    """显式 dossier 可派生 quality status，且 preflight 不修改原始输入 payload."""
    from council.fact_grounding import evaluate_dossier_quality
    dossier = _valid_dossier()
    _validate_council_input("002156.SZ", dossier)
    assert "fact_contract" not in dossier
    status, reasons, _ = evaluate_dossier_quality(dossier, ticker="002156.SZ")
    assert status == "failed"
    assert any("core_snapshot" in reason for reason in reasons)


def test_explicit_dossier_preflight_returns_recomputed_quality_sidecar():
    """显式 dossier 经过 preflight 后，prompt 可消费重算的质量 sidecar."""
    from council.fact_grounding import FactContractError

    dossier = _valid_dossier()
    dossier["research_dossier"]["main_business"] = {
        "code": "002156",
        "by_industry": [{"name": "封装测试", "revenue": 1.0, "revenue_ratio": 1.0}],
    }
    with pytest.raises(FactContractError, match="time basis|report_period"):
        _validate_council_input("002156.SZ", dossier)


@pytest.mark.anyio
@pytest.mark.parametrize(("case_name", "features", "error_prefix"), _invalid_cases())
async def test_invalid_explicit_features_fail_before_all_council_side_effects(
    case_name,
    features,
    error_prefix,
    tmp_path,
    monkeypatch,
):
    """非空错误/空壳输入也必须在 cache 和 LLM 之前 fail closed。"""
    monkeypatch.chdir(tmp_path)

    with patch(
        "council.debate.build_research_dossier",
        side_effect=AssertionError("must not build dossier"),
    ) as mock_dossier, patch(
        "council.debate._check_cache",
        side_effect=AssertionError("must not check cache"),
    ) as mock_cache, patch(
        "council.debate.call_agent",
        new_callable=AsyncMock,
        side_effect=AssertionError("must not call agent"),
    ) as mock_agent, patch(
        "council.debate.call_llm",
        new_callable=AsyncMock,
        side_effect=AssertionError("must not call llm"),
    ) as mock_llm, patch(
        "council.debate._call_da",
        new_callable=AsyncMock,
        side_effect=AssertionError("must not call da"),
    ) as mock_da, patch(
        "council.debate._call_synthesizer",
        new_callable=AsyncMock,
        side_effect=AssertionError("must not call synthesizer"),
    ) as mock_synth, patch(
        "council.debate._write_council_output",
        side_effect=AssertionError("must not write watchlist"),
    ) as mock_write:
        with pytest.raises(ValueError, match=error_prefix):
            await run_debate("002156.SZ", features=features, force=False)

    mock_dossier.assert_not_called()
    mock_cache.assert_not_called()
    mock_agent.assert_not_called()
    mock_llm.assert_not_called()
    mock_da.assert_not_called()
    mock_synth.assert_not_called()
    mock_write.assert_not_called()
    assert not (tmp_path / "debate").exists()
    assert not (tmp_path / "watchlist").exists()


@pytest.mark.anyio
async def test_valid_explicit_dossier_reaches_existing_cache_path():
    """preflight 通过的 dossier 保持既有 cache 行为。"""
    cached_success = object()
    with patch("council.debate._check_cache", return_value=cached_success) as mock_cache:
        result = await run_debate("002156.SZ", features=_valid_dossier(), force=False)

    assert result is cached_success
    mock_cache.assert_called_once_with(
        "002156.SZ",
        expected_execution_mode="council",
    )


@pytest.mark.anyio
async def test_none_features_builds_then_validates_before_cache():
    """`features=None` 仍由 builder 生成 dossier，再进入 cache。"""
    cached_success = object()
    with patch(
        "council.debate.build_research_dossier",
        return_value=_valid_dossier(),
    ) as mock_dossier, patch(
        "council.debate._check_cache",
        return_value=cached_success,
    ) as mock_cache:
        result = await run_debate("002156.SZ", features=None, force=False)

    assert result is cached_success
    mock_dossier.assert_called_once_with("002156.SZ")
    mock_cache.assert_called_once_with(
        "002156.SZ",
        expected_execution_mode="council",
    )


@pytest.mark.anyio
async def test_complete_legacy_flat_snapshot_is_normalized_before_cache():
    """完整旧扁平快照不能直送 prompt，必须先经 dossier builder 规范化。"""
    flat_snapshot = _valid_dossier()["core_snapshot"]
    cached_success = object()
    with patch(
        "council.debate.build_research_dossier",
        return_value=_valid_dossier(),
    ) as mock_dossier, patch(
        "council.debate._check_cache",
        return_value=cached_success,
    ) as mock_cache:
        result = await run_debate("002156.SZ", features=flat_snapshot, force=False)

    assert result is cached_success
    mock_dossier.assert_called_once_with("002156.SZ", core_snapshot=flat_snapshot)
    mock_cache.assert_called_once_with(
        "002156.SZ",
        expected_execution_mode="council",
    )


@pytest.mark.anyio
async def test_invalid_explicit_features_never_return_a_successful_cache():
    """无效 caller input 不能被同 ticker 的历史成功 cache 掩盖。"""
    invalid_features = {"error": "insufficient_data", "missing_fields": ["roe_3y"]}
    cached_success = object()

    with patch("council.debate._check_cache", return_value=cached_success) as mock_cache:
        with pytest.raises(ValueError, match="insufficient_data"):
            await run_debate("002156.SZ", features=invalid_features, force=False)

    mock_cache.assert_not_called()


@pytest.mark.anyio
async def test_top_level_optional_identity_mismatch_fails_before_council_side_effects():
    features = _valid_dossier()
    features["pledge"] = {"ticker": "600519.SH", "pledge_ratio": 8.0}

    with patch(
        "council.debate._check_cache",
        side_effect=AssertionError("must fail before cache"),
    ) as mock_cache, patch(
        "council.debate.call_agent",
        new_callable=AsyncMock,
        side_effect=AssertionError("must fail before agent"),
    ) as mock_agent:
        with pytest.raises(ValueError, match="ticker mismatch"):
            await run_debate("002156.SZ", features=features, force=False)

    mock_cache.assert_not_called()
    mock_agent.assert_not_called()


@pytest.mark.anyio
@pytest.mark.parametrize("ticker_value", [None, ""])
async def test_explicit_core_ticker_missing_or_empty_fails_before_council_cache(
    ticker_value,
):
    features = _valid_dossier()
    if ticker_value is None:
        features["core_snapshot"].pop("ticker")
    else:
        features["core_snapshot"]["ticker"] = ticker_value

    with patch(
        "council.debate._check_cache",
        side_effect=AssertionError("must fail before cache"),
    ) as mock_cache:
        with pytest.raises(ValueError, match="ticker"):
            await run_debate("002156.SZ", features=features, force=False)

    mock_cache.assert_not_called()
