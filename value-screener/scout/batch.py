"""Scout 并发 LLM 调用（design.md §1 决策 2 + §4, tasks 3.1-3.7）.

OpenAI 兼容 httpx 直连，temperature=0，20 并发/批。
单只超时 60s，失败重试 1 次（退避 2s）。
异常收窄：只捕获 httpx.HTTPStatusError / httpx.TimeoutException。

并发策略（design.md §4）：
- asyncio.Semaphore(20) 控制并发（避免 API rate limit）
- 单只超时 60s（httpx.AsyncClient(timeout=60.0)）
- 失败重试 1 次（退避 2s）
- 异常不阻塞整批（跳过该 ticker，标记为 error）

输出过滤（design.md §4 输出过滤）：
- 只返回 verdict == "deep_dive" 的候选（供 L3 消费）
- top-20 cap（按 confidence 降序取前 20，AD-03 成本闸门 200→20）
"""
from __future__ import annotations

import asyncio
import os
from datetime import date

import httpx

from .input_assembly import assemble_snapshot
from .parse import parse_scout_output, apply_buffer_zone
from .prompt import SCOUT_SYSTEM_PROMPT, format_snapshot
from .quality import ScoutCache


async def call_llm_snapshot(snapshot: str, system_prompt: str) -> str:
    """调用 OpenAI 兼容 LLM API，返回 JSON 字符串.

    Args:
        snapshot: 特征快照文本（user message）
        system_prompt: System prompt（缺省用 SCOUT_SYSTEM_PROMPT）

    Returns:
        LLM 返回的 JSON 字符串

    Raises:
        ValueError: 环境变量缺失（fail-fast）
        httpx.HTTPStatusError: HTTP 错误（重试后仍失败）
        httpx.TimeoutException: 超时（重试后仍失败）

    环境变量（design.md §1 决策 2）：
    - LLM_API_KEY: API 密钥（required）
    - LLM_API_BASE: API base URL（required）
    - LLM_MODEL: 模型名称（required，no default）
    """
    # fail-fast: 显式检查环境变量
    for key in ("LLM_API_KEY", "LLM_API_BASE", "LLM_MODEL"):
        if key not in os.environ:
            raise ValueError(f"missing required env var: {key}")

    api_key = os.environ["LLM_API_KEY"]
    api_base = os.environ["LLM_API_BASE"]
    model = os.environ["LLM_MODEL"]

    # 重试逻辑：1 次重试，退避 2s
    last_exc = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
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
                            {"role": "user", "content": snapshot},
                        ],
                        "temperature": 0.0,  # design.md §3.1 消除随机性
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


async def scout_batch(candidates: list[dict], force: bool = False) -> list[dict]:
    """并发对 ~200 只股票做 LLM 初筛，返回 deep_dive 短名单.

    Args:
        candidates: L1 输出的 candidates 列表（S5 schema），每项含 ticker 字段
        force: 是否跳过缓存（缺省 False）

    Returns:
        deep_dive 候选列表（按 confidence 降序，top-20 cap），每项含：
        {
            "ticker": str,
            "verdict": "deep_dive",
            "confidence": int,
            "one_liner": str,
            "red_flags": list[str],
            "green_flags": list[str],
            "anti_trap_flags": list[str],
        }

    处理流程：
    1. 检查缓存（ScoutCache.get，TTL=24h）
    2. 组装特征快照（assemble_snapshot + format_snapshot）
    3. 并发调用 LLM（Semaphore(20)）
    4. 解析输出 + 应用缓冲带
    5. 写入缓存（ScoutCache.set）
    6. 过滤 deep_dive + top-20 cap
    """
    cache = ScoutCache()
    today = date.today().isoformat()
    semaphore = asyncio.Semaphore(20)

    results = []

    async def process_one(candidate: dict) -> dict | None:
        ticker = candidate.get("ticker")
        if not ticker:
            return None

        try:
            # 1. 检查缓存（除非 force=True）
            if not force:
                cached = cache.get(ticker, today)
                if cached is not None:
                    return {
                        "ticker": ticker,
                        "verdict": cached.get("verdict"),
                        "confidence": cached.get("confidence", 0),
                        "one_liner": cached.get("one_liner", ""),
                        "red_flags": cached.get("red_flags", []),
                        "green_flags": cached.get("green_flags", []),
                        "anti_trap_flags": cached.get("anti_trap_flags", []),
                        "low_confidence_anomaly": cached.get("low_confidence_anomaly", False),
                        "from_cache": True,
                    }

            # 2. 组装特征快照
            features = assemble_snapshot(ticker)

            # Insufficient data guard
            if "error" in features:
                return {
                    "ticker": ticker,
                    "verdict": "error",
                    "error": features.get("error"),
                    "missing_fields": features.get("missing_fields", []),
                }

            snapshot_text = format_snapshot(features)

            # 3. 并发调用 LLM
            async with semaphore:
                try:
                    raw_json = await call_llm_snapshot(snapshot_text, SCOUT_SYSTEM_PROMPT)
                except (httpx.HTTPStatusError, httpx.TimeoutException, ValueError) as e:
                    return {
                        "ticker": ticker,
                        "verdict": "error",
                        "error": str(e),
                    }

            # 4. 解析输出 + 应用缓冲带
            parsed = parse_scout_output(raw_json)
            final_verdict, is_anomaly = apply_buffer_zone(parsed["verdict"], parsed["confidence"])

            result = {
                "ticker": ticker,
                "verdict": final_verdict,
                "confidence": parsed["confidence"],
                "one_liner": parsed["one_liner"],
                "red_flags": parsed["red_flags"],
                "green_flags": parsed["green_flags"],
                "anti_trap_flags": parsed["anti_trap_flags"],
                "low_confidence_anomaly": is_anomaly,
            }

            # 5. 写入缓存（失败不丢结果）
            try:
                cache.set(ticker, today, result, features)
            except OSError:
                pass  # 缓存写入失败不影响结果返回

            return result

        except Exception as e:
            # 兜底：非预期异常（脏数据/类型错位等）不静默丢弃
            return {
                "ticker": ticker,
                "verdict": "error",
                "error": f"unexpected: {e}",
            }

    # 并发处理所有候选
    tasks = [process_one(c) for c in candidates]
    raw_results = await asyncio.gather(*tasks)

    # 过滤 None（ticker 缺失或 insufficient data 等）
    results = [r for r in raw_results if r is not None]

    # 6. 过滤 deep_dive + top-20 cap
    deep_dive = [r for r in results if r.get("verdict") == "deep_dive"]
    deep_dive.sort(key=lambda x: x.get("confidence", 0), reverse=True)
    return deep_dive[:20]
