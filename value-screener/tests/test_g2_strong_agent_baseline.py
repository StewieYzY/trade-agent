from __future__ import annotations

import copy
import asyncio
import hashlib
import importlib
import json

import httpx

from council import thesis_draft
from test_m0_strong_agent_thesis_draft import _input_envelope


def _sha256(value: object) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _baseline_envelope(
    tmp_path,
    *,
    attempt_index: int = 1,
    diagnostic_bundle=None,
) -> dict:
    thesis_input = _input_envelope(
        tmp_path / "m0-input",
        diagnostic_bundle=diagnostic_bundle,
    )
    input_digest = _sha256(thesis_input)
    return {
        "schema_version": "g2-strong-agent-baseline-input-v1",
        "canonical_ticker": thesis_input["canonical_ticker"],
        "run_id": thesis_input["run_id"],
        "attempt_index": attempt_index,
        "diagnostic_digest": thesis_input["diagnostic_artifact"]["diagnostic"][
            "diagnostic_digest"
        ],
        "dossier_digest": _sha256(thesis_input["dossier"]),
        "input_digest": input_digest,
        "prompt_version": "m0-strong-agent-thesis-draft-prompt-v1",
        "profile_version": thesis_input["profile_version"],
        "model": "strong-test",
        "reasoning_level": "heavy",
        "budget": {
            "max_total_tokens": 1000,
            "max_cost": 1.5,
            "currency": "CNY",
        },
        "input_artifact_identity": {
            "artifact_type": "m0_strong_agent_thesis_draft_input",
            "schema_version": thesis_input["schema_version"],
            "artifact_digest": input_digest,
        },
        "thesis_draft_input": thesis_input,
    }


def test_valid_baseline_input_has_stable_input_identity_and_unique_attempt_identity(
    tmp_path,
):
    baseline = importlib.import_module("council.strong_agent_baseline")
    first_payload = _baseline_envelope(tmp_path, attempt_index=1)
    second_payload = copy.deepcopy(first_payload)
    second_payload["attempt_index"] = 2

    first = baseline.validate_strong_agent_baseline_input(first_payload)
    second = baseline.validate_strong_agent_baseline_input(second_payload)

    assert first.canonical_ticker == "600519.SH"
    assert first.run_id == "m0-run-001"
    assert first.model == "strong-test"
    assert first.reasoning_level == "heavy"
    assert first.budget == {
        "max_total_tokens": 1000,
        "max_cost": 1.5,
        "currency": "CNY",
    }
    assert first.baseline_input_digest == second.baseline_input_digest
    assert first.attempt_id != second.attempt_id
    assert first.attempt_id == baseline.validate_strong_agent_baseline_input(
        first_payload
    ).attempt_id


def test_one_baseline_attempt_reuses_m02_once_and_records_usage_and_output_digest(
    tmp_path, monkeypatch
):
    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path, attempt_index=1)
    calls = []

    async def fake_call(*args, **kwargs):
        calls.append((args, kwargs))
        from test_m0_strong_agent_thesis_draft import _agent_response

        return _agent_response(), {
            "prompt_tokens": 7,
            "completion_tokens": 10,
            "total_tokens": 17,
            "cost": 0.017,
            "currency": "CNY",
        }

    monkeypatch.setattr(thesis_draft, "call_llm", fake_call)
    result = asyncio.run(
        baseline.run_strong_agent_baseline(payload, tmp_path / "baseline")
    )

    assert len(calls) == 1
    args, kwargs = calls[0]
    assert len(args) == 3
    assert isinstance(args[0], str)
    assert isinstance(args[1], str)
    assert "600519.SH" in args[1]
    assert args[2] == "heavy"
    assert kwargs == {"model": "strong-test"}
    record = json.loads(result.record_path.read_text(encoding="utf-8"))
    validated = baseline.validate_strong_agent_baseline_input(payload)
    assert record["record_schema_version"] == "g2-strong-agent-baseline-record-v1"
    assert record["canonical_ticker"] == "600519.SH"
    assert record["run_id"] == "m0-run-001"
    assert record["attempt_index"] == 1
    assert record["attempt_id"].endswith("-attempt-001")
    assert record["baseline_input_digest"] == validated.baseline_input_digest
    assert record["model"] == "strong-test"
    assert record["reasoning_level"] == "heavy"
    assert record["budget"]["max_total_tokens"] == 1000
    assert record["usage"]["total_tokens"] == 17
    assert record["usage"]["cost"] == 0.017
    assert record["provider_call_count"] == 1
    assert record["execution_status"] == "completed"
    assert record["quality_status"] == "warning"
    assert record["failure_kind"] is None
    assert record["output_digest"]
    assert record["thesis_draft_artifact_digest"]
    assert record["engineering_status"] == "experiment_recorded"
    assert record["capability_status"] == "not_evidence"
    assert record["gate_status"] == "not_passed"
    assert result.record_path.parent.name == "attempt-001"


def _run_records(tmp_path, monkeypatch, responses, usages):
    baseline = importlib.import_module("council.strong_agent_baseline")
    calls = []
    response_iter = iter(zip(responses, usages))

    async def fake_call(*args, **kwargs):
        calls.append((args, kwargs))
        response, usage = next(response_iter)
        return response, usage

    monkeypatch.setattr(thesis_draft, "call_llm", fake_call)
    records = []
    for index in range(len(responses)):
        payload = _baseline_envelope(
            tmp_path / f"input-{index}",
            attempt_index=index + 1,
        )
        result = asyncio.run(
            baseline.run_strong_agent_baseline(
                payload,
                tmp_path / "baseline",
            )
        )
        records.append(
            json.loads(result.record_path.read_text(encoding="utf-8"))
        )
    return baseline, records, calls


def test_identical_repeated_records_are_stable_without_provider_comparison(
    tmp_path, monkeypatch
):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline, records, calls = _run_records(
        tmp_path,
        monkeypatch,
        [_agent_response(), _agent_response()],
        [
            {"prompt_tokens": 7, "completion_tokens": 10, "total_tokens": 17},
            {"prompt_tokens": 7, "completion_tokens": 10, "total_tokens": 17},
        ],
    )

    comparison = baseline.compare_strong_agent_baseline_records(records)

    assert len(calls) == 2
    assert comparison["comparison_status"] == "stable"
    assert comparison["attempt_count"] == 2
    assert comparison["stable_field_results"]["canonical_ticker"] is True
    assert comparison["stable_field_results"]["baseline_input_digest"] is True
    assert comparison["output_digest_changes"] == []
    assert comparison["quality_changes"] == []
    assert comparison["usage_deltas"]["total_tokens"] == 0
    assert comparison["structural_failures"] == []


def test_repeated_records_report_allowed_output_quality_and_usage_drift(
    tmp_path, monkeypatch
):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline, records, _ = _run_records(
        tmp_path,
        monkeypatch,
        [
            _agent_response(core_thesis="第一版研究判断"),
            _agent_response(
                core_thesis="第二版研究判断",
                risks=["新增风险"],
            ),
        ],
        [
            {
                "prompt_tokens": 7,
                "completion_tokens": 10,
                "total_tokens": 17,
                "cost": 0.017,
            },
            {
                "prompt_tokens": 8,
                "completion_tokens": 12,
                "total_tokens": 20,
                "cost": 0.020,
            },
        ],
    )

    comparison = baseline.compare_strong_agent_baseline_records(records)

    assert comparison["comparison_status"] == "drifted"
    assert comparison["output_digest_changes"] == [
        {
            "attempt_index": 1,
            "from": records[0]["output_digest"],
            "to": records[1]["output_digest"],
        }
    ]
    assert comparison["quality_changes"] == []
    assert comparison["usage_deltas"] == {
        "prompt_tokens": 1,
        "completion_tokens": 2,
        "total_tokens": 3,
        "cost": 0.003,
    }
    assert "output_digest" in comparison["allowed_drift_fields"]
    assert "usage" in comparison["allowed_drift_fields"]


def test_comparison_rejects_mismatched_stable_identity_as_structural_failure(
    tmp_path, monkeypatch
):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline, records, _ = _run_records(
        tmp_path,
        monkeypatch,
        [_agent_response(), _agent_response()],
        [{"total_tokens": 17}, {"total_tokens": 17}],
    )
    records[1]["model"] = "different-model"
    records[1]["record_digest"] = baseline.compute_baseline_record_digest(
        records[1]
    )

    comparison = baseline.compare_strong_agent_baseline_records(records)

    assert comparison["comparison_status"] == "structural_failure"
    assert comparison["structural_failures"] == [
        "stable field mismatch: model"
    ]


def test_record_and_comparison_renderers_are_deterministic_and_isolated(
    tmp_path, monkeypatch
):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline, records, _ = _run_records(
        tmp_path,
        monkeypatch,
        [_agent_response(), _agent_response(core_thesis="第二版")],
        [{"total_tokens": 17}, {"total_tokens": 18}],
    )
    comparison = baseline.compare_strong_agent_baseline_records(records)

    record_json = baseline.render_baseline_record_json(records[0])
    record_json_again = baseline.render_baseline_record_json(records[0])
    record_markdown = baseline.render_baseline_record_markdown(records[0])
    comparison_json = baseline.render_baseline_comparison_json(comparison)
    comparison_markdown = baseline.render_baseline_comparison_markdown(
        comparison
    )

    assert record_json == record_json_again
    assert json.loads(record_json) == records[0]
    assert "attempt-001" in record_markdown
    assert "not_evidence" in record_markdown
    assert comparison_json == baseline.render_baseline_comparison_json(comparison)
    assert json.loads(comparison_json) == comparison
    assert "不是 G2 Capability Gate evidence" in comparison_markdown

    output_dir = tmp_path / "comparison-output"
    paths = baseline.write_baseline_comparison(records, output_dir)
    assert paths.json_path == output_dir / "comparison.json"
    assert paths.markdown_path == output_dir / "comparison.md"
    first_json = paths.json_path.read_bytes()
    first_markdown = paths.markdown_path.read_bytes()
    second_paths = baseline.write_baseline_comparison(records, output_dir)
    assert second_paths.json_path.read_bytes() == first_json
    assert second_paths.markdown_path.read_bytes() == first_markdown
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "comparison.json",
        "comparison.md",
    ]


def test_provider_failure_is_recorded_as_failed_without_fake_success(
    tmp_path, monkeypatch
):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path, attempt_index=1)
    calls = []

    async def fake_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise httpx.HTTPError("provider unavailable")

    monkeypatch.setattr(thesis_draft, "call_llm", fake_call)
    result = asyncio.run(
        baseline.run_strong_agent_baseline(payload, tmp_path / "failed")
    )
    record = json.loads(result.record_path.read_text(encoding="utf-8"))

    assert len(calls) == 1
    assert record["execution_status"] == "failed"
    assert record["quality_status"] == "failed"
    assert record["failure_kind"] == "transport"
    assert record["agent_signal"] == "skip"
    assert record["output_digest"]
    assert record["provider_call_count"] == 1


def test_agent_skip_and_blocked_diagnostic_remain_non_directional_records(
    tmp_path, monkeypatch
):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path / "skip", attempt_index=1)

    async def fake_skip(*args, **kwargs):
        return _agent_response(
            signal="skip",
            conviction=0,
            out_of_circle=True,
        ), {"total_tokens": 9}

    monkeypatch.setattr(thesis_draft, "call_llm", fake_skip)
    skipped = asyncio.run(
        baseline.run_strong_agent_baseline(payload, tmp_path / "skip-out")
    )
    skipped_record = json.loads(skipped.record_path.read_text(encoding="utf-8"))
    assert skipped_record["execution_status"] == "skipped"
    assert skipped_record["agent_signal"] == "skip"
    assert skipped_record["agent_out_of_circle"] is True

    failed_payload = _baseline_envelope(
        tmp_path / "diagnostic",
        diagnostic_bundle=__import__(
            "test_m0_frozen_input_growth_diagnostic",
            fromlist=["_bundle"],
        )._bundle(market_value=1_000_000.0),
        attempt_index=1,
    )
    diagnostic = asyncio.run(
        baseline.run_strong_agent_baseline(
            failed_payload,
            tmp_path / "diagnostic-out",
        )
    )
    diagnostic_record = json.loads(
        diagnostic.record_path.read_text(encoding="utf-8")
    )
    assert diagnostic_record["execution_status"] == "failed"
    assert diagnostic_record["quality_status"] == "failed"
    assert diagnostic_record["failure_kind"] == "diagnostic_blocked"
    assert diagnostic_record["diagnostic_status"] == "failed"


def test_dossier_preflight_writes_zero_call_structural_failure_record(
    tmp_path, monkeypatch
):
    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path)
    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("dossier preflight must not call provider")

    monkeypatch.setattr(thesis_draft, "call_llm", forbidden_call)
    monkeypatch.setattr(
        thesis_draft,
        "evaluate_dossier_quality",
        lambda *_args, **_kwargs: ("failed", ["high severity fact failed"], {}),
    )

    result = asyncio.run(
        baseline.run_strong_agent_baseline(payload, tmp_path / "preflight")
    )
    record = json.loads(result.record_path.read_text(encoding="utf-8"))

    assert calls == []
    assert record["provider_call_count"] == 0
    assert record["execution_status"] == "failed"
    assert record["failure_kind"] == "structural"
    assert record["output_digest"] is None
    assert "dossier quality is failed" in record["status_reasons"][0]


def test_input_digest_mismatch_is_audited_without_provider_call(
    tmp_path, monkeypatch
):
    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path)
    payload["dossier_digest"] = "0" * 64
    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("invalid identity must not call provider")

    monkeypatch.setattr(thesis_draft, "call_llm", forbidden_call)
    result = asyncio.run(
        baseline.run_strong_agent_baseline(payload, tmp_path / "mismatch")
    )
    record = json.loads(result.record_path.read_text(encoding="utf-8"))

    assert calls == []
    assert record["failure_kind"] == "structural"
    assert record["provider_call_count"] == 0
    assert record["execution_status"] == "failed"
    assert record["canonical_ticker"] == "600519.SH"


def test_malformed_record_comparison_is_complete_and_provider_free(
    tmp_path, monkeypatch
):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline, records, _ = _run_records(
        tmp_path,
        monkeypatch,
        [_agent_response(), _agent_response()],
        [{"total_tokens": 17}, {"total_tokens": 17}],
    )
    malformed = copy.deepcopy(records[1])
    malformed.pop("record_digest")

    def forbidden_call(*args, **kwargs):
        raise AssertionError("comparison must not invoke provider")

    monkeypatch.setattr(thesis_draft, "call_llm", forbidden_call)
    comparison = baseline.compare_strong_agent_baseline_records(
        [records[0], malformed]
    )

    assert comparison["comparison_status"] == "structural_failure"
    assert "baseline record missing fields" in comparison["structural_failures"][0]
    assert comparison["comparison_digest"]
    assert json.loads(baseline.render_baseline_comparison_json(comparison)) == comparison


def test_usage_over_budget_is_visible_as_degraded_record(tmp_path, monkeypatch):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path)

    async def over_budget_call(*args, **kwargs):
        return _agent_response(), {
            "prompt_tokens": 600,
            "completion_tokens": 500,
            "total_tokens": 1100,
            "cost": 2.0,
            "currency": "CNY",
        }

    monkeypatch.setattr(thesis_draft, "call_llm", over_budget_call)
    result = asyncio.run(
        baseline.run_strong_agent_baseline(payload, tmp_path / "over-budget")
    )
    record = json.loads(result.record_path.read_text(encoding="utf-8"))

    assert record["execution_status"] == "degraded"
    assert record["quality_status"] == "warning"
    assert record["usage"]["total_tokens"] == 1100
    assert record["usage"]["cost"] == 2.0
    assert "usage exceeded fixed baseline budget" in record["status_reasons"]


def test_budget_can_omit_optional_cost_limit(tmp_path):
    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path)
    payload["budget"] = {"max_total_tokens": 1000}

    validated = baseline.validate_strong_agent_baseline_input(payload)

    assert validated.budget == {
        "max_total_tokens": 1000,
        "max_cost": None,
        "currency": None,
    }


def test_unsafe_run_identity_does_not_create_output_side_effect(
    tmp_path, monkeypatch
):
    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path)
    payload["run_id"] = "../escape"
    output_dir = tmp_path / "unsafe"

    async def forbidden_call(*args, **kwargs):
        raise AssertionError("unsafe input must not call provider")

    monkeypatch.setattr(thesis_draft, "call_llm", forbidden_call)
    try:
        asyncio.run(baseline.run_strong_agent_baseline(payload, output_dir))
    except baseline.StrongAgentBaselineError:
        pass
    else:
        raise AssertionError("unsafe run_id must be rejected")

    assert not output_dir.exists()


def test_record_validator_rejects_forged_attempt_identity(tmp_path, monkeypatch):
    from test_m0_strong_agent_thesis_draft import _agent_response

    baseline, records, _ = _run_records(
        tmp_path,
        monkeypatch,
        [_agent_response(), _agent_response()],
        [{"total_tokens": 17}, {"total_tokens": 17}],
    )
    forged = copy.deepcopy(records[0])
    forged["attempt_id"] = "forged-attempt"
    forged["record_digest"] = baseline.compute_baseline_record_digest(forged)

    try:
        baseline.validate_baseline_record(forged)
    except baseline.StrongAgentBaselineError as exc:
        assert "attempt_id" in str(exc)
    else:
        raise AssertionError("forged attempt_id must be rejected")


def test_failed_m02_status_is_not_overwritten_by_budget_degraded(
    tmp_path, monkeypatch
):
    baseline = importlib.import_module("council.strong_agent_baseline")
    payload = _baseline_envelope(tmp_path)

    async def malformed_over_budget_call(*args, **kwargs):
        return '{"signal":"bullish"}', {
            "total_tokens": 1100,
            "cost": 2.0,
            "currency": "CNY",
        }

    monkeypatch.setattr(thesis_draft, "call_llm", malformed_over_budget_call)
    result = asyncio.run(
        baseline.run_strong_agent_baseline(
            payload,
            tmp_path / "failed-over-budget",
        )
    )
    record = json.loads(result.record_path.read_text(encoding="utf-8"))

    assert record["quality_status"] == "failed"
    assert record["execution_status"] == "failed"
    assert record["failure_kind"] == "schema"
    assert record["usage"]["total_tokens"] == 1100
    assert "usage exceeded fixed baseline budget" in record["status_reasons"]
