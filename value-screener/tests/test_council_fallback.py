"""G2 strong single-agent fallback foundation contract tests."""
from __future__ import annotations

import asyncio
import json
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
