"""f3f authorized live LLM harness tests (no real LLM in tests)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.repro_out.f3f_live_repro_exp import (
    build_live_user_message,
    insufficient_features,
    model_configuration,
    run_live_experiment,
)


def _env(tmp_path: Path) -> Path:
    path = tmp_path / ".env"
    path.write_text(
        "LLM_API_KEY=x\n"
        "LLM_API_BASE=http://provider.example/base\n"
        "LLM_MODEL=weak\n"
        "LLM_MODEL_HEAVY=strong\n"
        "LLM_MODEL_MODERATE=mid\n",
        encoding="utf-8",
    )
    return path


class TestLiveAuthorization:
    def test_live_requires_explicit_authorization(self, tmp_path: Path):
        with pytest.raises(ValueError, match="authoriz"):
            asyncio.run(
                run_live_experiment(
                    tmp_path / "out",
                    _env(tmp_path),
                    authorize_live=False,
                )
            )

    def test_live_requires_env_keys(self, tmp_path: Path):
        env = tmp_path / ".env"
        env.write_text("LLM_API_KEY=x\n", encoding="utf-8")

        with pytest.raises(ValueError, match="env"):
            asyncio.run(
                run_live_experiment(
                    tmp_path / "out",
                    env,
                    authorize_live=True,
                )
            )


class TestInputs:
    def test_insufficient_features_and_user_message(self):
        features = insufficient_features()
        message = build_live_user_message("600900.SH", features)

        assert features == {}
        assert "特征数据" in message

    def test_model_configuration_has_heavy_model(self):
        config = model_configuration(
            {
                "LLM_API_KEY": "x",
                "LLM_API_BASE": "http://example",
                "LLM_MODEL": "weak",
                "LLM_MODEL_HEAVY": "strong",
                "LLM_MODEL_MODERATE": "mid",
            }
        )

        assert config["heavy_model"] == "strong"
        assert config["reasoning_levels"] == ["heavy", "moderate"]
