"""L3 LLM 调用层（design.md 决策 2, AD-04）.

按推理等级映射模型：
- heavy（R1-3）→ LLM_MODEL_HEAVY
- moderate（R4）→ LLM_MODEL_MODERATE

复用 LLM_API_KEY / LLM_API_BASE（与 L2 共享），新增 LLM_MODEL_HEAVY / LLM_MODEL_MODERATE。

异常收窄：httpx.HTTPStatusError / httpx.TimeoutException，超时 120s（重度模型响应慢），重试 1 次。
"""
from __future__ import annotations

import asyncio
import os

import httpx


def _get_model_for_level(reasoning_level: str) -> str:
    """根据推理等级返回对应的模型名称.

    Args:
        reasoning_level: "heavy" 或 "moderate"

    Returns:
        模型名称（从环境变量读取）

    Raises:
        ValueError: 环境变量缺失或 reasoning_level 非法
    """
    env_map = {
        "heavy": "LLM_MODEL_HEAVY",
        "moderate": "LLM_MODEL_MODERATE",
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


async def call_llm(
    system_prompt: str,
    user_message: str,
    reasoning_level: str = "heavy",
) -> str:
    """调用 OpenAI 兼容 LLM API，返回 JSON 字符串.

    Args:
        system_prompt: System prompt
        user_message: User message（特征数据 + 指令）
        reasoning_level: 推理等级（"heavy" / "moderate"）

    Returns:
        LLM 返回的 JSON 字符串

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
    api_key = os.environ["LLM_API_KEY"]
    api_base = os.environ["LLM_API_BASE"]

    # 重试逻辑：1 次重试，退避 2s
    last_exc = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
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
                return resp.json()["choices"][0]["message"]["content"]
        except (httpx.HTTPStatusError, httpx.TimeoutException) as e:
            last_exc = e
            if attempt == 0:
                await asyncio.sleep(2)  # 退避 2s
            else:
                raise last_exc

    # 不应到达
    raise last_exc
