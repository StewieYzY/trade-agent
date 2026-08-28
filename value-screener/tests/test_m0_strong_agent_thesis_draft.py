from __future__ import annotations

import asyncio
import copy
import json

import httpx
import pytest
from typer.testing import CliRunner

from cli import app
from data.lib.frozen_growth_diagnostic import run_frozen_input_growth_diagnostic
from council import thesis_draft
from council.thesis_draft import (
    ThesisDraftInputError,
    run_strong_agent_thesis_draft,
    validate_thesis_draft_artifact,
)
from council import llm
from test_m0_frozen_input_growth_diagnostic import _bundle


def _dossier(ticker: str = "600519.SH") -> dict:
    return {
        "core_snapshot": {
            "ticker": ticker,
            "name": "测试公司",
            "market_cap": 1000000000,
            "pe_ttm": 20.0,
            "roe_3y": [10.0, 11.0, 12.0],
            "net_margin": 8.0,
        },
        "core_fact_provenance": {
            field: {
                "source": "fixture.core",
                "report_period": "2025-12-31",
                "as_of": "2026-08-24",
            }
            for field in ("market_cap", "pe_ttm", "roe_3y", "net_margin")
        },
        "research_dossier": {
            "main_business": {
                "by_industry": [{"industry": "测试行业", "revenue_share": 1.0}]
            },
            "peers": {"peer_avg_pe": 22.0},
            "research": {"consensus_eps": 1.2},
            "capex_proxy": {"__error__": True, "reason": "fixture unavailable"},
            "degraded_fields": [],
        },
    }


def _agent_response(**overrides) -> str:
    payload = {
        "signal": "bullish",
        "conviction": 80,
        "core_thesis": "主营业务清晰且经营质量有一定持续性，但价格仍需结合诊断复核。",
        "key_metrics": ["PE 20.0", "ROE 12.0"],
        "risks": ["需求变化", "估值回落"],
        "what_would_change_my_mind": "连续两期核心经营指标恶化",
        "out_of_circle": False,
        "historical_parallel": None,
        "new_evidence": ["ROE 近三期保持为正"],
        "evidence_exhausted": False,
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _input_envelope(tmp_path, *, diagnostic_bundle=None, dossier=None) -> dict:
    bundle = diagnostic_bundle or _bundle()
    diagnostic_result = run_frozen_input_growth_diagnostic(
        bundle,
        tmp_path / "diagnostic",
    )
    artifact = json.loads(diagnostic_result.json_path.read_text(encoding="utf-8"))
    return {
        "schema_version": "m0-strong-agent-thesis-draft-input-v1",
        "canonical_ticker": bundle["canonical_ticker"],
        "run_id": bundle["run_id"],
        "dossier_snapshot": bundle["dossier_snapshot"],
        "profile_version": bundle["profile_version"],
        "diagnostic_artifact": artifact,
        "dossier": dossier or _dossier(bundle["canonical_ticker"]),
    }


def _run(envelope, output_dir, monkeypatch, response=None, *, model="strong-test"):
    calls = []

    async def fake_call(*args, **kwargs):
        calls.append((args, kwargs))
        if isinstance(response, BaseException):
            raise response
        return response or _agent_response(), {"total_tokens": 17}

    monkeypatch.setattr(thesis_draft, "call_llm", fake_call)
    artifacts = asyncio.run(
        run_strong_agent_thesis_draft(
            envelope,
            output_dir,
            model=model,
        )
    )
    return artifacts, calls


def test_valid_input_makes_one_strong_call_and_writes_reviewable_artifacts(
    tmp_path, monkeypatch
):
    envelope = _input_envelope(tmp_path)

    artifacts, calls = _run(envelope, tmp_path / "draft", monkeypatch)

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[2] == "heavy"
    assert kwargs == {"model": "strong-test"}
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "strong_agent_thesis_draft"
    assert payload["artifact_schema_version"] == "m0-strong-agent-thesis-draft-v1"
    assert payload["canonical_ticker"] == "600519.SH"
    assert payload["run_id"] == "m0-run-001"
    assert payload["diagnostic_digest"] == envelope["diagnostic_artifact"]["diagnostic"]["diagnostic_digest"]
    assert payload["agent_output"]["signal"] == "bullish"
    assert payload["agent_output"]["core_thesis"]
    assert payload["agent_output"]["key_metrics"] == ["PE 20.0", "ROE 12.0"]
    assert payload["agent_output"]["risks"] == ["需求变化", "估值回落"]
    assert payload["quality_status"] == "warning"
    assert payload["capability_status"] == "mvp_evidence"
    assert payload["gate_status"] == "not_passed"
    validated = validate_thesis_draft_artifact(payload, envelope)
    assert validated["agent_output"]["signal"] == "bullish"
    markdown = artifacts.markdown_path.read_text(encoding="utf-8")
    assert "人工复核" in markdown
    assert "当前无法证明" in markdown
    assert "不是正式 InvestmentThesis" in markdown


def test_same_input_and_response_have_identical_artifacts(tmp_path, monkeypatch):
    first_input = _input_envelope(tmp_path / "one")
    second_input = copy.deepcopy(first_input)

    first, _ = _run(first_input, tmp_path / "out-one", monkeypatch)
    second, _ = _run(second_input, tmp_path / "out-two", monkeypatch)

    first_payload = json.loads(first.json_path.read_text(encoding="utf-8"))
    second_payload = json.loads(second.json_path.read_text(encoding="utf-8"))
    assert first_payload == second_payload
    assert first.markdown_path.read_text(encoding="utf-8") == second.markdown_path.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value.pop("run_id"),
        lambda value: value.update(canonical_ticker="600036.SH"),
        lambda value: value["diagnostic_artifact"].update(run_id="other-run"),
        lambda value: value["diagnostic_artifact"].update(
            artifact_digest="0" * 64
        ),
        lambda value: value["dossier"]["core_snapshot"].update(ticker="600036.SH"),
    ],
)
def test_invalid_identity_or_digest_fails_before_llm_and_files(
    tmp_path, monkeypatch, mutator
):
    envelope = _input_envelope(tmp_path)
    mutator(envelope)
    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid input must not call LLM")

    monkeypatch.setattr(thesis_draft, "call_llm", forbidden_call)
    output_dir = tmp_path / "draft"

    with pytest.raises(ThesisDraftInputError):
        asyncio.run(run_strong_agent_thesis_draft(envelope, output_dir))

    assert calls == []
    assert not output_dir.exists()


@pytest.mark.parametrize(
    "response",
    [
        httpx.HTTPError("provider failed"),
        '{"signal":"bullish"}',
    ],
)
def test_llm_transport_or_schema_failure_is_a_single_safe_skip_draft(
    tmp_path, monkeypatch, response
):
    envelope = _input_envelope(tmp_path)

    artifacts, calls = _run(
        envelope,
        tmp_path / "draft",
        monkeypatch,
        response=response,
    )

    assert len(calls) == 1
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["quality_status"] == "failed"
    assert payload["agent_output"]["signal"] == "skip"
    assert payload["agent_output"]["conviction"] == 0
    assert payload["agent_output"]["core_thesis"]
    assert payload["failure_kind"] in {"transport", "schema"}
    assert payload["quality_reasons"]


def test_failed_diagnostic_cannot_be_upgraded_to_directional_agent_output(
    tmp_path, monkeypatch
):
    failed_bundle = _bundle(market_value=1_000_000.0)
    envelope = _input_envelope(tmp_path, diagnostic_bundle=failed_bundle)

    artifacts, _ = _run(
        envelope,
        tmp_path / "draft",
        monkeypatch,
        response=_agent_response(signal="bullish", conviction=99),
    )

    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["diagnostic_status"] == "failed"
    assert payload["agent_output"]["signal"] == "skip"
    assert payload["agent_output"]["conviction"] == 0
    assert payload["quality_status"] == "failed"
    assert payload["diagnostic"]["priced_growth_value_range"] is None


def test_out_of_circle_agent_is_visible_but_not_published_as_clean(
    tmp_path, monkeypatch
):
    envelope = _input_envelope(tmp_path)

    artifacts, _ = _run(
        envelope,
        tmp_path / "draft",
        monkeypatch,
        response=_agent_response(
            signal="skip",
            conviction=0,
            out_of_circle=True,
            risks=["业务超出能力圈"],
        ),
    )

    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["agent_output"]["signal"] == "skip"
    assert payload["agent_output"]["out_of_circle"] is True
    assert payload["quality_status"] == "warning"
    assert "业务超出能力圈" in payload["agent_output"]["risks"]


@pytest.mark.parametrize(
    "response_overrides",
    [
        {"signal": "skip", "conviction": 77},
        {"signal": "bullish", "conviction": 91, "out_of_circle": True},
    ],
)
def test_skip_or_out_of_circle_is_normalized_to_safe_agent_output(
    tmp_path, monkeypatch, response_overrides
):
    envelope = _input_envelope(tmp_path)

    artifacts, _ = _run(
        envelope,
        tmp_path / "draft",
        monkeypatch,
        response=_agent_response(**response_overrides),
    )

    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["agent_output"]["signal"] == "skip"
    assert payload["agent_output"]["conviction"] == 0


@pytest.mark.parametrize(
    "key_metrics",
    [
        [999.0],
        [{"metric": 999.0}],
    ],
)
def test_non_string_key_metrics_cannot_bypass_grounding(
    tmp_path, monkeypatch, key_metrics
):
    envelope = _input_envelope(tmp_path)

    artifacts, _ = _run(
        envelope,
        tmp_path / "draft",
        monkeypatch,
        response=_agent_response(key_metrics=key_metrics),
    )

    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["quality_status"] == "failed"
    assert payload["agent_output"]["signal"] == "skip"
    assert payload["agent_output"]["conviction"] == 0


def test_failed_dossier_quality_blocks_llm_before_output_dir_creation(
    tmp_path, monkeypatch
):
    envelope = _input_envelope(tmp_path)
    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("failed dossier must not call LLM")

    monkeypatch.setattr(thesis_draft, "call_llm", forbidden_call)
    monkeypatch.setattr(
        thesis_draft,
        "evaluate_dossier_quality",
        lambda *_args, **_kwargs: ("failed", ["high severity fact failed"], {}),
    )
    output_dir = tmp_path / "draft"

    with pytest.raises(ThesisDraftInputError, match="quality"):
        asyncio.run(run_strong_agent_thesis_draft(envelope, output_dir))

    assert calls == []
    assert not output_dir.exists()


def test_fabricated_metric_and_forbidden_stable_fields_are_not_published(
    tmp_path, monkeypatch
):
    envelope = _input_envelope(tmp_path)

    artifacts, _ = _run(
        envelope,
        tmp_path / "draft",
        monkeypatch,
        response=_agent_response(
            key_metrics=["PE 999.0"],
            target_price=1234.5,
            view_signal="buy",
            investment_eligibility="investable",
        ),
    )

    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    assert payload["quality_status"] == "failed"
    assert payload["agent_output"]["signal"] == "skip"
    assert payload["agent_output"]["conviction"] == 0
    assert "target_price" not in payload["agent_output"]
    assert "view_signal" not in payload["agent_output"]
    assert "investment_eligibility" not in payload["agent_output"]
    assert any("fabricated" in reason or "schema" in reason for reason in payload["quality_reasons"])


def test_nested_diagnostic_tampering_is_rejected_after_outer_digest_recomputed(
    tmp_path, monkeypatch
):
    envelope = _input_envelope(tmp_path)
    artifacts, _ = _run(envelope, tmp_path / "draft", monkeypatch)
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    payload["diagnostic"]["credible_growth_range"] = [0.0, 0.0]
    payload["artifact_digest"] = thesis_draft.compute_thesis_draft_artifact_digest(payload)

    with pytest.raises(ThesisDraftInputError, match="diagnostic"):
        validate_thesis_draft_artifact(payload, envelope)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda value: value["agent_output"].update(key_metrics=[999.0]),
        lambda value: value["agent_output"].update(target_price=1234.5),
        lambda value: value["agent_output"].update(
            signal="skip",
            conviction=77,
        ),
    ],
)
def test_artifact_validator_rechecks_m0_agent_output_semantics(
    tmp_path, monkeypatch, mutator
):
    envelope = _input_envelope(tmp_path)
    artifacts, _ = _run(envelope, tmp_path / "draft", monkeypatch)
    payload = json.loads(artifacts.json_path.read_text(encoding="utf-8"))
    mutator(payload)
    payload["artifact_digest"] = thesis_draft.compute_thesis_draft_artifact_digest(payload)

    with pytest.raises(ThesisDraftInputError, match="agent_output|schema|grounding"):
        validate_thesis_draft_artifact(payload, envelope)


def test_call_llm_once_does_not_retry_http_requests(monkeypatch):
    requests = []

    class FailingResponse:
        def raise_for_status(self):
            request = httpx.Request("POST", "https://example.test/v1/chat/completions")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("failed", request=request, response=response)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            requests.append(1)
            return FailingResponse()

    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "https://example.test")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-test")
    monkeypatch.setattr(llm.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(
            llm.call_llm_once("system", "user", reasoning_level="heavy")
        )

    assert len(requests) == 1


def test_cli_reads_explicit_input_and_does_not_initialize_provider(
    tmp_path, monkeypatch
):
    envelope = _input_envelope(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(envelope, ensure_ascii=False), encoding="utf-8")

    async def fake_call(*args, **kwargs):
        return _agent_response(), {}

    monkeypatch.setattr(thesis_draft, "call_llm", fake_call)

    def forbidden_fetcher(*args, **kwargs):
        raise AssertionError("CLI must not initialize provider")

    monkeypatch.setattr("cli._get_fetcher", forbidden_fetcher)
    result = CliRunner().invoke(
        app,
        [
            "strong-agent-thesis-draft",
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "output"),
            "--model",
            "strong-test",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "600519.SH-m0-run-001.json" in result.stdout
    assert (tmp_path / "output" / "600519.SH-m0-run-001.json").is_file()
    assert (tmp_path / "output" / "600519.SH-m0-run-001.md").is_file()
