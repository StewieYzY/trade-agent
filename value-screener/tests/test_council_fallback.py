"""G2 strong single-agent fallback foundation contract tests."""
from __future__ import annotations

import asyncio
import json
from collections import UserDict
from pathlib import Path

import httpx
import pytest

from council import fallback
from council.schema import AgentOutput


def _dossier(ticker: str = "600009.SH") -> dict:
    return {
        "core_snapshot": {
            "ticker": ticker,
            "name": "测试公司",
            "market_cap": 1000000000,
            "pe_ttm": 20.0,
            "roe_3y": [10.0, 11.0, 12.0],
            "net_margin": 8.0,
        },
        "research_dossier": {
            "main_business": {"by_industry": [{"industry": "测试行业"}]},
            "peers": {"peer_avg_pe": 22.0},
            "research": {"consensus_eps": 1.2},
        },
    }


def _agent_output(**overrides) -> AgentOutput:
    data = {
        "signal": "neutral",
        "conviction": 50,
        "core_thesis": "基于当前可核验事实保持中性",
        "key_metrics": ["PE 20.0", "ROE 12.0"],
        "risks": ["估值与需求变化"],
        "what_would_change_my_mind": "补充连续期经营数据",
        "out_of_circle": False,
    }
    data.update(overrides)
    return AgentOutput.from_dict("buffett", data)


def _raw_output(**overrides) -> str:
    return json.dumps(_agent_output(**overrides).to_dict(), ensure_ascii=False)


@pytest.mark.parametrize(
    ("ticker", "features"),
    [
        ("600009.SH", {}),
        ("600009.SH", {"error": "insufficient_data"}),
        ("600009.SH", {"core_snapshot": {"ticker": "600009.SH"}, "research_dossier": {}}),
        ("600009.SH", _dossier("600519.SH")),
    ],
)
def test_invalid_fallback_input_has_zero_side_effect(
    tmp_path, monkeypatch, ticker, features
):
    async def forbidden_call(*_args, **_kwargs):
        raise AssertionError("fallback must not call LLM")

    monkeypatch.setattr(fallback, "call_llm", forbidden_call)

    with pytest.raises(ValueError, match="no_evidence|insufficient_data|ticker"):
        asyncio.run(
            fallback.run_fallback(
                ticker=ticker,
                features=features,
                output_root=tmp_path,
                run_id="invalid-input",
            )
        )

    assert not (tmp_path / "invalid-input").exists()


@pytest.mark.parametrize(
    "features",
    [
        {**_dossier(), "core_snapshot": {**_dossier()["core_snapshot"], "ticker": None}},
        {
            **_dossier(),
            "core_snapshot": {**_dossier()["core_snapshot"], "ticker": "   "},
        },
        {
            **_dossier(),
            "core_snapshot": {
                k: v for k, v in _dossier()["core_snapshot"].items() if k != "ticker"
            },
        },
        {
            **_dossier(),
            "research_dossier": {
                **_dossier()["research_dossier"],
                "peers": {"ticker": "600519.SH", "peer_avg_pe": 22.0},
            },
        },
        {
            **_dossier(),
            "pledge": {"ticker": "600519.SH", "pledge_ratio": 8.0},
        },
        {
            **_dossier(),
            "core_snapshot": {
                **_dossier()["core_snapshot"],
                "metadata": {"symbol": "600519.SH"},
            },
        },
        {
            **_dossier(),
            "core_snapshot": {
                **_dossier()["core_snapshot"],
                "metadata": UserDict({"symbol": "600519.SH"}),
            },
        },
        {
            **_dossier(),
            "research_dossier": UserDict(
                {
                    **_dossier()["research_dossier"],
                    "peers": UserDict({"symbol": "600519.SH"}),
                }
            ),
        },
    ],
    ids=[
        "core-ticker-missing",
        "core-ticker-empty",
        "core-ticker-omitted",
        "optional-section-mismatch",
        "top-level-optional-section-mismatch",
        "nested-core-identity-mismatch",
        "mapping-core-identity-mismatch",
        "mapping-research-identity-mismatch",
    ],
)
def test_explicit_dossier_identity_is_required_and_consistent(
    tmp_path, monkeypatch, features
):
    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("fallback must fail before LLM")

    monkeypatch.setattr(fallback, "call_llm", forbidden_call)
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    with pytest.raises(ValueError, match="ticker"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009.SH",
                features=features,
                output_root=tmp_path,
                run_id="identity-rejected",
            )
        )

    assert calls == []
    assert not (tmp_path / "identity-rejected").exists()


def test_explicit_dossier_identity_is_preserved_for_normal_run(
    tmp_path, monkeypatch
):
    async def fake_call(*_args, **_kwargs):
        return _raw_output(), {}

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009",
            features=_dossier(),
            output_root=tmp_path,
            run_id="identity-accepted",
        )
    )

    assert result["ticker"] == "600009.SH"
    assert result["synthesis"]["ticker"] == "600009.SH"


@pytest.mark.parametrize(
    "error_value",
    [
        "api_key=unit-test-secret",
        "token=unit-test-secret",
        "Bearer x",
        "Token x",
        "Authorization: Bearer unit-test-secret",
        "https://user:unit-test-secret@example.test/v1",
        {
            "headers": {"Authorization": "Bearer unit-test-secret"},
            "query": {"api_key": "unit-test-secret", "token": "unit-test-secret"},
        },
        [
            {"nested": {"api_key": "unit-test-secret"}},
            "token=unit-test-secret",
        ],
    ],
    ids=[
        "api-key",
        "token",
        "bare-bearer",
        "bare-token",
        "authorization",
        "url-credential",
        "mapping",
        "nested",
    ],
)
def test_fallback_redacts_sensitive_error_content(tmp_path, monkeypatch, error_value):
    async def fake_call(*_args, **_kwargs):
        raise RuntimeError(error_value)

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path,
            run_id="redacted-error",
        )
    )
    serialized = (
        (tmp_path / "redacted-error" / "result.json").read_text(encoding="utf-8")
        + (tmp_path / "redacted-error" / "manifest.json").read_text(encoding="utf-8")
    )

    assert result["quality_status"] == "blocked"
    assert "unit-test-secret" not in serialized
    assert "<redacted>" in serialized


@pytest.mark.parametrize(
    ("error_value", "expected_error"),
    [
        (
            "upstream failed: (Bearer x)",
            "RuntimeError: upstream failed: (Bearer <redacted>)",
        ),
        (
            'upstream failed: "bearer x".',
            'RuntimeError: upstream failed: "Bearer <redacted>".',
        ),
        (
            "upstream failed: [Token x], retry",
            "RuntimeError: upstream failed: [Token <redacted>], retry",
        ),
        (
            "provider error (Bearer x)",
            "RuntimeError: provider error (Bearer <redacted>)",
        ),
        (
            "upstream failed; Token x: retry",
            "RuntimeError: upstream failed; Token <redacted>: retry",
        ),
        (
            "upstream failed: Bearer x\nretry",
            "RuntimeError: upstream failed: Bearer <redacted>\nretry",
        ),
        (
            "upstream failed: Bearer x\t",
            "RuntimeError: upstream failed: Bearer <redacted>\t",
        ),
        (
            "upstream failed: [Token x],retry",
            "RuntimeError: upstream failed: [Token <redacted>],retry",
        ),
        (
            "upstream failed Bearer x",
            "RuntimeError: upstream failed Bearer <redacted>",
        ),
        (
            "Authorization: Bearer x],retry",
            "RuntimeError: Authorization: Bearer <redacted>],retry",
        ),
    ],
    ids=[
        "parenthesized",
        "quoted-with-period",
        "bracketed-with-comma",
        "parenthesized-without-colon",
        "semicolon-with-colon-terminator",
        "newline-terminator",
        "tab-terminator",
        "adjacent-punctuation",
        "space-left-boundary",
        "authorization-wrapped-token",
    ],
)
def test_fallback_redacts_embedded_short_credentials_from_artifacts(
    tmp_path, monkeypatch, error_value, expected_error
):
    """Bug caught: wrapped short credentials bypass the shared redactor."""
    async def fake_call(*_args, **_kwargs):
        raise RuntimeError(error_value)

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path,
            run_id="wrapped-short-credential",
        )
    )
    serialized = (
        (tmp_path / "wrapped-short-credential" / "result.json").read_text(
            encoding="utf-8"
        )
        + (tmp_path / "wrapped-short-credential" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["quality_status"] == "blocked"
    assert error_value not in result["error"]
    assert error_value not in serialized
    assert result["error"] == expected_error
    assert "<redacted>" in serialized


@pytest.mark.parametrize(
    "credential_text",
    [
        "Bearer x",
        "bearer x",
        "(Bearer x)",
        '"bearer x".',
        "[Token x], retry",
    ],
    ids=[
        "bare-bearer",
        "lowercase-bearer",
        "parenthesized-bearer",
        "quoted-bearer",
        "bracketed-token",
    ],
)
def test_fallback_redacts_short_credentials_from_malformed_raw_artifacts(
    tmp_path, monkeypatch, credential_text
):
    raw_response = f"not-json upstream failed: {credential_text}"

    async def fake_call(*_args, **_kwargs):
        return raw_response, {}

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path,
            run_id="wrapped-short-raw",
        )
    )
    serialized = (
        (tmp_path / "wrapped-short-raw" / "result.json").read_text(encoding="utf-8")
        + (tmp_path / "wrapped-short-raw" / "manifest.json").read_text(encoding="utf-8")
    )

    assert result["quality_status"] == "blocked"
    assert credential_text not in result["raw"]
    assert credential_text not in serialized
    assert "<redacted>" in result["raw"]


def test_fallback_redacts_short_credentials_from_schema_valid_artifacts(
    tmp_path, monkeypatch
):
    raw_response = _raw_output(core_thesis="upstream failed: (Bearer x)")

    async def fake_call(*_args, **_kwargs):
        return raw_response, {"note": "upstream failed: [Token x], retry"}

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path,
            run_id="wrapped-short-schema",
        )
    )
    serialized = (
        (tmp_path / "wrapped-short-schema" / "result.json").read_text(encoding="utf-8")
        + (tmp_path / "wrapped-short-schema" / "manifest.json").read_text(encoding="utf-8")
    )

    assert result["quality_status"] == "passed"
    assert "Bearer x" not in serialized
    assert "Token x" not in serialized
    assert result["usage"]["note"] == "upstream failed: [Token <redacted>], retry"
    assert result["agent_output"]["core_thesis"] == (
        "upstream failed: (Bearer <redacted>)"
    )


def test_fallback_redacts_sensitive_malformed_raw_response(tmp_path, monkeypatch):
    raw_response = (
        'not-json api_key=unit-test-secret token=unit-test-secret '
        'Authorization: Bearer unit-test-secret '
        "https://user:unit-test-secret@example.test/v1"
    )

    async def fake_call(*_args, **_kwargs):
        return raw_response, {}

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path,
            run_id="redacted-raw",
        )
    )
    serialized = (
        (tmp_path / "redacted-raw" / "result.json").read_text(encoding="utf-8")
        + (tmp_path / "redacted-raw" / "manifest.json").read_text(encoding="utf-8")
    )

    assert result["quality_status"] == "blocked"
    assert result["raw"] != raw_response
    assert "unit-test-secret" not in serialized
    assert "<redacted>" in serialized


def test_fallback_redacts_schema_valid_output_and_usage(tmp_path, monkeypatch):
    payload = _agent_output(
        core_thesis="api_key=unit-test-secret",
        extra={"password": "unit-test-secret", "nested": {"token": "unit-test-secret"}},
    ).to_dict()
    raw_response = json.dumps(payload, ensure_ascii=False)

    async def fake_call(*_args, **_kwargs):
        return raw_response, {
            "token": "unit-test-secret",
            "nested": {"client_secret": "unit-test-secret"},
        }

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path,
            run_id="redacted-schema-valid",
        )
    )
    serialized = (tmp_path / "redacted-schema-valid" / "result.json").read_text(
        encoding="utf-8"
    )

    assert result["quality_status"] == "passed"
    assert "unit-test-secret" not in serialized
    assert result["usage"]["token"] == "<redacted>"
    assert result["agent_output"]["extra"]["password"] == "<redacted>"
    assert result["agent_output"]["extra"]["nested"]["token"] == "<redacted>"


def test_protected_output_root_is_rejected_before_none_features_preflight(
    monkeypatch,
):
    protected_root = Path(__file__).resolve().parents[1] / "watchlist"
    preflight_calls = []

    def forbidden_preflight(*args, **kwargs):
        preflight_calls.append((args, kwargs))
        raise AssertionError("protected path must be rejected before dossier preflight")

    monkeypatch.setattr(fallback, "_prepare_council_input", forbidden_preflight)
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    with pytest.raises(ValueError, match="protected production output root"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009.SH",
                features=None,
                output_root=protected_root,
                run_id="path-order",
            )
        )

    assert preflight_calls == []


@pytest.mark.parametrize("root_name", ["cache", "watchlist", "debate", "snapshots"])
def test_fallback_rejects_protected_roots_before_side_effects(
    tmp_path, monkeypatch, root_name
):
    protected_root = Path(__file__).resolve().parents[1] / (
        "data/cache" if root_name == "cache" else f"{root_name}"
    )
    if root_name == "snapshots":
        protected_root = Path(__file__).resolve().parents[1] / "data/snapshots"

    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("fallback must reject protected root before LLM")

    monkeypatch.setattr(fallback, "call_llm", forbidden_call)
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    with pytest.raises(ValueError, match="protected production output root"):
        asyncio.run(
            fallback.run_fallback(
                ticker="600009.SH",
                features=_dossier(),
                output_root=protected_root / "run-001",
                run_id="protected-root",
            )
        )

    assert calls == []
    assert not (protected_root / "run-001" / "protected-root").exists()


def test_fallback_rejects_protected_root_ancestor_and_symlink_before_side_effects(
    tmp_path, monkeypatch
):
    protected_root = Path(__file__).resolve().parents[1] / "watchlist"
    symlink_root = tmp_path / "watchlist-link"
    symlink_root.symlink_to(protected_root, target_is_directory=True)
    calls = []

    async def forbidden_call(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("fallback must reject protected root before LLM")

    monkeypatch.setattr(fallback, "call_llm", forbidden_call)
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    for output_root in (protected_root.parent, symlink_root / "run-001"):
        with pytest.raises(ValueError, match="protected production output root"):
            asyncio.run(
                fallback.run_fallback(
                    ticker="600009.SH",
                    features=_dossier(),
                    output_root=output_root,
                    run_id="protected-root",
                )
            )

    assert calls == []


def test_fallback_calls_one_strong_agent_and_does_not_write_council_outputs(
    tmp_path, monkeypatch
):
    calls = []

    async def fake_call(system_prompt, user_message, reasoning_level, *, model=None):
        calls.append(
            {
                "system_prompt": system_prompt,
                "user_message": user_message,
                "reasoning_level": reasoning_level,
                "model": model,
            }
        )
        return _raw_output(), {"total_tokens": 7}

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_API_BASE", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path,
            run_id="single-call",
            model="strong-override",
        )
    )

    assert len(calls) == 1
    assert calls[0]["reasoning_level"] == "heavy"
    assert calls[0]["model"] == "strong-override"
    assert result["quality_status"] == "passed"
    assert result["synthesis"]["signal"] == "neutral"
    assert result["usage"] == {"total_tokens": 7}
    assert not (tmp_path / "watchlist").exists()
    assert not (tmp_path / "debate").exists()


@pytest.mark.parametrize(
    ("raw_or_error", "want_failure_kind"),
    [
        ('{"new_evidence": "wrong-type"}', "schema"),
        (httpx.TimeoutException("provider timeout"), "transport"),
    ],
)
def test_schema_or_transport_failure_blocks_directional_synthesis(
    tmp_path, monkeypatch, raw_or_error, want_failure_kind
):
    async def fake_call(*_args, **_kwargs):
        if isinstance(raw_or_error, Exception):
            raise raw_or_error
        return raw_or_error, {}

    monkeypatch.setattr(fallback, "call_llm", fake_call)
    monkeypatch.setattr(fallback, "_build_user_message", lambda *args, **kwargs: "user")
    monkeypatch.setattr(fallback, "get_prompt_builder", lambda _agent: lambda: "system")
    monkeypatch.setenv("LLM_API_BASE", "https://provider.example/v1")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "strong-from-env")

    result = asyncio.run(
        fallback.run_fallback(
            ticker="600009.SH",
            features=_dossier(),
            output_root=tmp_path,
            run_id=f"blocked-{want_failure_kind}",
        )
    )

    assert result["quality_status"] == "blocked"
    assert result["failure_kind"] == want_failure_kind
    assert result["synthesis"]["signal"] == "skip"
    assert result["synthesis"]["conviction"] == 0


@pytest.mark.parametrize(
    "output",
    [
        _agent_output(key_metrics=["ROE 99.0"]),
        _agent_output(core_thesis="munger 看好这只股票"),
    ],
)
def test_fact_checker_blocks_grounding_or_crosstalk(output):
    report = fallback.check_agent_facts(output, _dossier())

    assert report["status"] == "blocked"
    assert report["issues"]


def test_synthesis_copies_passed_fields_and_blocks_without_new_facts():
    output = _agent_output()
    passed = fallback.build_fallback_synthesis(
        ticker="600009.SH",
        agent_id="buffett",
        output=output,
        fact_check={"status": "passed", "issues": []},
    )
    blocked = fallback.build_fallback_synthesis(
        ticker="600009.SH",
        agent_id="buffett",
        output=output,
        fact_check={"status": "blocked", "issues": ["fabricated metric"]},
    )

    assert passed["quality_status"] == "passed"
    assert passed["signal"] == output.signal
    assert passed["key_metrics"] == output.key_metrics
    assert passed["what_would_change_my_mind"] == output.what_would_change_my_mind
    assert blocked["quality_status"] == "blocked"
    assert blocked["signal"] == "skip"
    assert blocked["conviction"] == 0
    assert blocked["key_metrics"] == []
    assert blocked["pending_verification"] == ["fabricated metric"]


def test_fallback_call_llm_call_shape_matches_real_signature(monkeypatch):
    """fallback 调用 call_llm 的实参形状必须能绑定真实 council.llm.call_llm 签名.

    防回归先例：fallback.py 传 model= 关键字，而 call_llm 曾不接受该参数，
    mock 假签名（fake_call）掩盖了真实 TypeError。用 inspect.bind 对真实签名校验。
    """
    import inspect

    from council import llm

    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_API_BASE", "http://x")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "heavy-model")

    sig = inspect.signature(llm.call_llm)
    # 与 fallback.run_fallback 内部调用点（council/fallback.py::call_llm(...)）同形
    sig.bind("system", "user", "heavy", model="explicit-model")
