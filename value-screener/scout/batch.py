"""Scout 并发 LLM 调用（design.md §1 决策 2 + §4, tasks 3.1-3.7）.

OpenAI 兼容 httpx 直连，temperature=0，20 并发/批。
单只超时 60s，失败重试 1 次（退避 2s）。
异常收窄：只捕获 httpx.HTTPStatusError / httpx.TimeoutException。

并发策略（design.md §4）：
- asyncio.Semaphore(20) 控制并发（避免 API rate limit）
- 单只超时 60s（httpx.AsyncClient(timeout=60.0)）
- 失败重试 1 次（退避 2s）
- 异常不阻塞整批（跳过该 ticker，标记为 error）

输出契约（g1-l2-full-result-contract）：
- 返回三元组 (full_results, usage_summary, failure_summary)，full_results 含每只输入
  的 verdict 分类（deep_dive/watch/skip/error），不再只留 deep_dive
- shortlist 由消费方从 full_results 派生（deep_dive 按 confidence 降序取前 20，AD-03 成本闸门 200→20）
"""
from __future__ import annotations

import asyncio
from datetime import date

import httpx

from council.llm import call_llm_light
from .input_assembly import assemble_snapshot
from .parse import parse_scout_output, apply_buffer_zone
from .prompt import SCOUT_SYSTEM_PROMPT, format_snapshot
from .quality import ScoutCache


# call_llm_snapshot 已迁至 council/llm.py 并重命名为 call_llm_light（f1-deviation-fix §7）。
# council.llm 作为 L2/L3 共享的 LLM 调用层，统一 token usage 采集（AD-03）。
# 保留本名作向后兼容别名（如有外部调用）。
call_llm_snapshot = call_llm_light


async def scout_batch(candidates: list[dict], force: bool = False) -> tuple[list[dict], dict, dict]:
    """并发对 ~200 只股票做 LLM 初筛，返回 (full_results, usage_summary, failure_summary).

    Args:
        candidates: L1 输出的 candidates 列表（S5 schema），每项含 ticker 字段
        force: 是否跳过缓存（缺省 False）

    Returns:
        (full_results, usage_summary, failure_summary)：
        - full_results: 每只输入一条结果（长度 == N，含 watch/skip/error/degraded，
          不再只留 deep_dive），每项含 ticker/verdict/confidence/one_liner/red_flags/
          green_flags/anti_trap_flags/low_confidence_anomaly，degraded 票含 degraded/
          degraded_reason，error 票含 error/missing_fields。
          shortlist 由消费方派生为 [r for r in full_results if verdict=="deep_dive"]
          按 confidence 降序取前 20（受既有 Top-20 Cap requirement 约束）。
        - usage_summary: 本次实跑的 token usage 汇总（f1-deviation-fix §7 / P1 修复），
          累加**所有** LLM 调用（含 deep_dive/watch/skip/error 路径，非仅 deep_dive），
          结构 {call_count, cache_hits, prompt_tokens, completion_tokens, total_tokens}。
          cache hit 不产生新调用（不计入 call_count），单独计 cache_hits。
          AD-03 成本验证用 call_count × 单只 token + cache_hits 推算全量成本。
        - failure_summary: 失败与分布汇总（g1-l2-full-result-contract），结构
          {errors:[{ticker,reason,stage}], skips, watches, degraded, unhandled_exceptions}。
          errors 可定位失败 ticker 与原因；degraded 单独计不进 errors；
          unhandled_exceptions == 0（兜底异常计入 errors 而非中断整批）。

    处理流程：
    1. 检查缓存（ScoutCache.get，TTL=24h）
    2. 组装特征快照（assemble_snapshot + format_snapshot）
    3. 并发调用 LLM（Semaphore(20)）
    4. 解析输出 + 应用缓冲带
    5. 写入缓存（ScoutCache.set）
    6. 汇总 failure_summary（errors/skips/watches/degraded/unhandled_exceptions）
    """
    cache = ScoutCache()
    today = date.today().isoformat()
    semaphore = asyncio.Semaphore(20)

    # f1-deviation-fix §7 / P1 修复：累加所有 LLM 调用的 usage（非仅 deep_dive）
    usage_summary = {
        "call_count": 0,        # 本次实际产生的 LLM 调用数（非 cache hit）
        "cache_hits": 0,         # cache 命中数（不产生新调用）
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    # g1-l2-full-result-contract：failure_summary 汇总失败与分布
    # errors 可定位 ticker/reason/stage；degraded 单独计不进 errors；
    # unhandled_exceptions 计兜底异常（MUST 为 0，因兜底已捕获并计入 errors）。
    failure_summary = {
        "errors": [],            # [{ticker, reason, stage}, ...]
        "skips": 0,              # verdict=="skip" 计数
        "watches": 0,            # verdict=="watch" 计数（含 degraded→watch 的票）
        "degraded": 0,           # degraded==True 计数（不进 errors，单独计）
        "unhandled_exceptions": 0,  # 兜底异常计数，MUST 为 0
    }

    def _accumulate(usage: dict | None) -> None:
        """累加单次调用的 usage 到 usage_summary."""
        if not usage:
            return
        usage_summary["call_count"] += 1
        usage_summary["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
        usage_summary["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
        usage_summary["total_tokens"] += int(usage.get("total_tokens", 0) or 0)

    async def process_one(candidate: dict, input_index: int) -> dict:
        # g1-l2-full-result-contract review 修复：输入校验移进 try 块，
        # 缺 ticker / 非 dict 输入返回符合 full-result 契约的 error result（含 input_index
        # 定位原始输入），不返回 None（保证 full_results 长度 == 输入 N），不逃逸整批。
        try:
            if not isinstance(candidate, dict):
                raise TypeError(f"candidate 非 dict: {type(candidate).__name__}")
            ticker = candidate.get("ticker")
            if not ticker:
                # 缺 ticker → error result（进 full_results + failure_summary.errors），
                # ticker=None 不伪造（避免与真实 ticker 混淆），用 input_index 定位原始输入。
                return {
                    "ticker": None,
                    "input_index": input_index,
                    "verdict": "error",
                    "error": "missing ticker",
                    "stage": "input_validation",
                    "one_liner": "输入缺 ticker 字段",
                    "red_flags": [],
                    "green_flags": [],
                    "anti_trap_flags": [],
                    "low_confidence_anomaly": False,
                }

            # 1. 检查缓存（除非 force=True）
            if not force:
                cached = cache.get(ticker, today)
                if cached is not None:
                    usage_summary["cache_hits"] += 1  # cache 命中，不产生新调用
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

            # 2. 组装特征快照（f2 §6: L2 降级模式——financials 不齐但 critical 齐时降级）
            features = assemble_snapshot(ticker, degrade_on_financials_gap=True)

            # Insufficient data guard（critical 缺失 → fail-fast，不降级）
            # g1-l2-full-result-contract review 修复：error result 补全 full-result 契约字段
            if "error" in features:
                return {
                    "ticker": ticker,
                    "verdict": "error",
                    "error": features.get("error"),
                    "missing_fields": features.get("missing_fields", []),
                    "one_liner": f"数据不足：{features.get('error')}",
                    "red_flags": [],
                    "green_flags": [],
                    "anti_trap_flags": [],
                    "low_confidence_anomaly": False,
                }

            # f2 §6.3 L2 降级：critical 齐但 financials 不齐 → 标 watch + confidence_cap=50
            # + degraded，不调 LLM（数据不全调 LLM 会编造 + 省钱），不进 deep_dive 短名单。
            # 用 `is True` 严格判断，避免 MagicMock/非 bool 假阳性触发降级。
            if features.get("degraded") is True:
                return {
                    "ticker": ticker,
                    "verdict": "watch",  # 强制 watch，不进 deep_dive
                    "confidence": 50,  # confidence_cap=50
                    "one_liner": f"L2 降级：{features.get('degraded_reason', 'financials 不齐')}",
                    "red_flags": [],
                    "green_flags": [],
                    "anti_trap_flags": [],
                    "low_confidence_anomaly": False,
                    "degraded": True,
                    "degraded_reason": features.get("degraded_reason"),
                    "usage": None,  # 未调 LLM
                }

            snapshot_text = format_snapshot(features)

            # 3. 并发调用 LLM（f1-deviation-fix §7：返回 (content, usage)，累加 usage 实测 AD-03）
            # 注：通过模块级别名 call_llm_snapshot 调用，便于测试 patch（与历史测试兼容）
            async with semaphore:
                try:
                    raw_json, usage = await call_llm_snapshot(snapshot_text, SCOUT_SYSTEM_PROMPT)
                except (httpx.HTTPStatusError, httpx.TimeoutException, ValueError) as e:
                    # g1-l2-full-result-contract review 修复：error result 补全契约字段
                    return {
                        "ticker": ticker,
                        "verdict": "error",
                        "error": str(e),
                        "one_liner": f"LLM 调用失败：{e}",
                        "red_flags": [],
                        "green_flags": [],
                        "anti_trap_flags": [],
                        "low_confidence_anomaly": False,
                    }

            # P1 修复：累加本次调用的 usage（无论 verdict 是 deep_dive/watch/skip）
            _accumulate(usage)

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
                "usage": usage or None,  # 保留单只 usage（向后兼容），汇总以 usage_summary 为准
            }

            # 5. 写入缓存（失败不丢结果）
            try:
                cache.set(ticker, today, result, features)
            except OSError:
                pass  # 缓存写入失败不影响结果返回

            return result

        except Exception as e:
            # 兜底：非预期异常（脏数据/类型错位等）不静默丢弃
            # g1-l2-full-result-contract：该只进 errors（已处理）。
            # unhandled_exceptions 计的是逃逸出 asyncio.gather 的异常——当前兜底 catch all
            # 保证不逃逸，故该字段恒为 0（spec 要求整批无未处理异常的断言字段）。
            # review 修复：兜底现在能 catch 到输入校验的 TypeError（已移进 try），补全契约字段。
            return {
                "ticker": candidate.get("ticker") if isinstance(candidate, dict) else None,
                "input_index": input_index,
                "verdict": "error",
                "error": f"unexpected: {e}",
                "stage": "unexpected_exception",
                "one_liner": f"非预期异常：{e}",
                "red_flags": [],
                "green_flags": [],
                "anti_trap_flags": [],
                "low_confidence_anomaly": False,
            }

    # 并发处理所有候选（带 input_index，便于缺 ticker / 坏输入的 error result 定位原始输入）
    tasks = [process_one(c, i) for i, c in enumerate(candidates)]
    raw_results = await asyncio.gather(*tasks)

    # process_one 现在对所有输入（含缺 ticker / 非 dict）都返回符合契约的 result，
    # 不再返回 None；保留 None 过滤仅作未来路径的防御性兜底。
    results = [r for r in raw_results if r is not None]

    # g1-l2-full-result-contract：汇总 failure_summary（errors/skips/watches/degraded）
    # shortlist 不再在此返回——由消费方从 full_results 派生（受既有 Top-20 Cap 约束）。
    # full_results 长度 == 输入 N（缺 ticker / 坏输入的 error result 仍在，不再被丢弃）。
    for r in results:
        verdict = r.get("verdict")
        if verdict == "error":
            # error result 自带 stage（input_validation / scout LLM 调用 / unexpected_exception），
            # 优先用 result 的 stage；无则回退 "scout"。
            failure_summary["errors"].append({
                "ticker": r.get("ticker"),
                "input_index": r.get("input_index"),
                "reason": r.get("error", "unknown"),
                "stage": r.get("stage", "scout"),
            })
        elif verdict == "skip":
            failure_summary["skips"] += 1
        elif verdict == "watch":
            failure_summary["watches"] += 1
        # degraded 票 verdict==watch（已计 watches），单独计 degraded 子集
        if r.get("degraded") is True:
            failure_summary["degraded"] += 1

    return results, usage_summary, failure_summary
