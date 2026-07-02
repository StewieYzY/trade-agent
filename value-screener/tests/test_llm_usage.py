"""Tests for call_llm token usage 采集（f1-deviation-fix §7, D6 方案 B）.

spec council-debate MODIFIED: token usage 采集——call_llm SHALL 返回 (content, usage)，
usage 含 prompt_tokens / completion_tokens / total_tokens，从 API 响应 usage 字段提取
（当前实现丢弃该字段，只返回 JSON 字符串）。

实现方案（用户决策 2026-07-02）：
- call_llm_snapshot 从 scout/batch.py 移到 council/llm.py，重命名为 call_llm_light
- call_llm（heavy/moderate）与 call_llm_light（light）共享 _http_call
- 两函数都返回 (content, usage)，L2 batch 与 L3 debate 调用方累加 usage
- AD-04 推理等级补第三档 light → LLM_MODEL
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from council.llm import call_llm, call_llm_light


def _make_httpx_mock(usage: dict, content: str):
    """构造一个 fake httpx.Response，含 usage + choices[0].message.content."""

    class _FakeResp:
        def __init__(self):
            self._json = {
                "choices": [{"message": {"content": content}}],
                "usage": usage,
            }

        def raise_for_status(self):
            pass

        def json(self):
            return self._json

    return _FakeResp()


@pytest.fixture
def env_vars(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_API_BASE", "http://test.local")
    monkeypatch.setenv("LLM_MODEL", "test-light-model")
    monkeypatch.setenv("LLM_MODEL_HEAVY", "test-heavy-model")
    monkeypatch.setenv("LLM_MODEL_MODERATE", "test-moderate-model")


@pytest.mark.anyio
async def test_call_llm_returns_content_and_usage(env_vars):
    """task 7.1/7.2: call_llm 返回 (content, usage)，usage 字段完整."""
    usage = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
    content = json.dumps({"signal": "bullish"}, ensure_ascii=False)
    fake_resp = _make_httpx_mock(usage, content)

    with patch("council.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value = mock_client

        result = await call_llm("sys", "user", "heavy")

    # 必须是 tuple
    assert isinstance(result, tuple)
    assert len(result) == 2
    content_out, usage_out = result
    assert content_out == content
    # usage 字段完整
    assert usage_out["prompt_tokens"] == 100
    assert usage_out["completion_tokens"] == 50
    assert usage_out["total_tokens"] == 150


@pytest.mark.anyio
async def test_call_llm_light_returns_content_and_usage(env_vars):
    """call_llm_light（原 call_llm_snapshot）也返回 (content, usage)."""
    usage = {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100}
    content = json.dumps({"verdict": "deep_dive"}, ensure_ascii=False)
    fake_resp = _make_httpx_mock(usage, content)

    with patch("council.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value =mock_client

        content_out, usage_out = await call_llm_light("snapshot", "sys")

    assert content_out == content
    assert usage_out["prompt_tokens"] == 80
    assert usage_out["total_tokens"] == 100


@pytest.mark.anyio
async def test_call_llm_usage_missing_in_response_defaults_to_empty(env_vars):
    """API 响应不含 usage 时（兼容性）→ usage 为 {} 不崩溃，content 正常返回."""
    content = json.dumps({"signal": "bullish"}, ensure_ascii=False)

    class _FakeRespNoUsage:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": content}}]}  # 无 usage

    with patch("council.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=_FakeRespNoUsage())
        mock_client_cls.return_value = mock_client

        content_out, usage_out = await call_llm("sys", "user", "heavy")

    assert content_out == content
    assert usage_out == {}


@pytest.mark.anyio
async def test_call_llm_light_model_env_var(env_vars):
    """call_llm_light 用 LLM_MODEL 环境变量（AD-04 第三档 light）."""
    fake_resp = _make_httpx_mock({"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, "{}")

    with patch("council.llm.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=fake_resp)
        mock_client_cls.return_value = mock_client

        await call_llm_light("snap", "sys")

    # post 调用的 json 参数中 model 应为 LLM_MODEL 的值
    call_kwargs = mock_client.post.call_args.kwargs
    assert call_kwargs["json"]["model"] == "test-light-model"


@pytest.mark.anyio
async def test_call_llm_light_missing_env_fails_fast(monkeypatch):
    """call_llm_light 缺 LLM_MODEL 时 fail-fast ValueError."""
    monkeypatch.setenv("LLM_API_KEY", "k")
    monkeypatch.setenv("LLM_API_BASE", "http://x")
    # LLM_MODEL 未设
    with pytest.raises(ValueError, match="LLM_MODEL"):
        await call_llm_light("snap", "sys")
