"""L3 LLM 调用层（design.md 决策 2, AD-04）.

按推理等级映射模型：
- heavy（R1-3）→ LLM_MODEL_HEAVY
- moderate（R4）→ LLM_MODEL_MODERATE
- light（L2 scout）→ LLM_MODEL（f1-deviation-fix §7：原 scout/batch.py::call_llm_snapshot
  迁入本模块，重命名为 call_llm_light，与 call_llm 共享 _http_call，统一 token usage 采集）

复用 LLM_API_KEY / LLM_API_BASE（L2/L3 共享）。

token usage 采集（f1-deviation-fix §7 / D6 方案 B，spec council-debate MODIFIED）：
- call_llm / call_llm_light 都返回 (content, usage)，usage 含
  prompt_tokens / completion_tokens / total_tokens（从 API 响应 usage 字段提取，
  当前实现原丢弃该字段）
- L2 scout_batch 与 L3 debate 调用方累加 usage 实测 AD-03 成本（≈¥0.01/只）

异常收窄：httpx.HTTPStatusError / httpx.TimeoutException，超时 120s（重度模型响应慢），重试 1 次。
"""
from __future__ import annotations

import asyncio
import os

import httpx


def _get_model_for_level(reasoning_level: str) -> str:
    """根据推理等级返回对应的模型名称.

    Args:
        reasoning_level: "heavy" / "moderate" / "light"

    Returns:
        模型名称（从环境变量读取）

    Raises:
        ValueError: 环境变量缺失或 reasoning_level 非法
    """
    env_map = {
        "heavy": "LLM_MODEL_HEAVY",
        "moderate": "LLM_MODEL_MODERATE",
        "light": "LLM_MODEL",
    }

    if reasoning_level not in env_map:
        raise ValueError(
            f"invalid reasoning_level: {reasoning_level}, "
            f"expected one of {list(env_map.keys())}"
        )

    env_key = env_map[reasoning_level]

    # fail-fast: 检查通用环境变量
    for key in ("LLM_API_KEY", "LLM_API_BASE"):
        if key not in os.environ:
            raise ValueError(f"missing required env var: {key}")

    # fail-fast: 检查等级特定环境变量
    if env_key not in os.environ:
        raise ValueError(f"missing required env var: {env_key}")

    return os.environ[env_key]


async def _http_call(
    system_prompt: str,
    user_message: str,
    model: str,
    timeout: float = 120.0,
) -> tuple[str, dict]:
    """共享的 OpenAI 兼容 HTTP 调用，返回 (content, usage).

    从 API 响应提取 content 与 usage（prompt_tokens/completion_tokens/total_tokens）。
    重试 1 次（退避 2s），异常收窄为 httpx.HTTPStatusError / httpx.TimeoutException。

    Args:
        system_prompt: System prompt
        user_message: User message
        model: 模型名称
        timeout: 超时秒数（重度模型 120s，轻量 60s）

    Returns:
        (content_str, usage_dict)；若 API 响应未带 usage，usage_dict 为 {}
    """
    api_key = os.environ["LLM_API_KEY"]
    api_base = os.environ["LLM_API_BASE"]

    # 重试逻辑：1 次重试，退避 2s
    last_exc = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{api_base}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": 0.0,  # 消除随机性
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                body = resp.json()
                content = body["choices"][0]["message"]["content"]
                usage = body.get("usage") or {}
                return content, usage
        except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt == 0:
                await asyncio.sleep(2)  # 退避 2s
            else:
                raise last_exc

    # 不应到达
    raise last_exc  # pragma: no cover


async def call_llm(
    system_prompt: str,
    user_message: str,
    reasoning_level: str = "heavy",
) -> tuple[str, dict]:
    """调用 OpenAI 兼容 LLM API（heavy/moderate 推理等级），返回 (content, usage).

    Args:
        system_prompt: System prompt
        user_message: User message（特征数据 + 指令）
        reasoning_level: 推理等级（"heavy" / "moderate"）

    Returns:
        (content, usage)：content 为 LLM 返回的 JSON 字符串，usage 含
        prompt_tokens / completion_tokens / total_tokens（供 AD-03 成本累加）

    Raises:
        ValueError: 环境变量缺失或 reasoning_level 非法（fail-fast）
        httpx.HTTPStatusError: HTTP 错误（重试后仍失败）
        httpx.TimeoutException: 超时（重试后仍失败）

    环境变量：
    - LLM_API_KEY: API 密钥（required）
    - LLM_API_BASE: API base URL（required）
    - LLM_MODEL_HEAVY: 重度推理模型（required when reasoning_level="heavy"）
    - LLM_MODEL_MODERATE: 中度推理模型（required when reasoning_level="moderate"）
    """
    model = _get_model_for_level(reasoning_level)
    return await _http_call(system_prompt, user_message, model, timeout=120.0)


async def call_llm_light(
    snapshot: str,
    system_prompt: str,
) -> tuple[str, dict]:
    """L2 轻量 LLM 调用（原 scout/batch.py::call_llm_snapshot，迁入本模块）.

    使用 LLM_MODEL（AD-04 第三档 light），单只超时 60s，返回 (content, usage)。
    L2 scout_batch 调用方累加 usage 实测 AD-03 成本（≈¥0.01/只）。

    Args:
        snapshot: 特征快照文本（user message）
        system_prompt: System prompt

    Returns:
        (content, usage)：content 为 LLM 返回的 JSON 字符串，usage 含 token 计数

    Raises:
        ValueError: 环境变量缺失（fail-fast）
        httpx.HTTPStatusError / httpx.TimeoutException: 重试后仍失败

    环境变量：
    - LLM_API_KEY / LLM_API_BASE（required）
    - LLM_MODEL: 轻量模型（required，no default）
    """
    # fail-fast: 复用 _get_model_for_level 的通用 env 检查 + light 特定检查
    model = _get_model_for_level("light")
    return await _http_call(system_prompt, snapshot, model, timeout=60.0)
