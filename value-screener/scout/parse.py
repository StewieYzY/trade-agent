"""Scout 输出解析 & 缓冲带逻辑（design.md §3.2, tasks 2.1-2.4）.

解析 LLM JSON 输出，应用 verdict 覆盖逻辑：
- confidence >= 60: 信任 LLM verdict
- 40 <= confidence < 60: 强制覆盖为 "watch"（缓冲带）
- confidence < 40: 强制覆盖为 "watch" + 标记低置信度异常

verdict 覆盖优先级（design.md §3.2）：LLM 输出的 verdict 仅在 confidence >= 60 时生效；
缓冲带和低置信度区间一律覆盖为 watch，确保所有通过 L1 的股票都有 L2 判断。
"""
from __future__ import annotations

import json


def parse_scout_output(raw_json: str) -> dict:
    """解析 LLM JSON 输出，验证字段合法性.

    Args:
        raw_json: LLM 返回的 JSON 字符串

    Returns:
        {
            "verdict": "deep_dive" | "watch" | "skip",
            "confidence": int (0-100),
            "one_liner": str,
            "red_flags": list[str],
            "green_flags": list[str],
            "anti_trap_flags": list[str],
        }
        解析失败时返回 {"verdict": "watch", "confidence": 0, "parse_error": True}

    验证规则：
    - verdict 必须为 deep_dive/watch/skip 之一
    - confidence 必须为 0-100 整数
    - flags 必须为字符串列表
    """
    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return {"verdict": "watch", "confidence": 0, "parse_error": True}

    if not isinstance(data, dict):
        return {"verdict": "watch", "confidence": 0, "parse_error": True}

    # 提取字段（缺省值）
    verdict = data.get("verdict")
    confidence = data.get("confidence")
    one_liner = data.get("one_liner", "")
    red_flags = data.get("red_flags", [])
    green_flags = data.get("green_flags", [])
    anti_trap_flags = data.get("anti_trap_flags", [])

    # 验证 verdict
    if verdict not in ("deep_dive", "watch", "skip"):
        verdict = "watch"

    # 验证 confidence
    if not isinstance(confidence, int) or confidence < 0 or confidence > 100:
        confidence = 0

    # 验证 flags 类型
    if not isinstance(red_flags, list) or not all(isinstance(f, str) for f in red_flags):
        red_flags = []
    if not isinstance(green_flags, list) or not all(isinstance(f, str) for f in green_flags):
        green_flags = []
    if not isinstance(anti_trap_flags, list) or not all(isinstance(f, str) for f in anti_trap_flags):
        anti_trap_flags = []

    return {
        "verdict": verdict,
        "confidence": confidence,
        "one_liner": str(one_liner)[:50],  # 截断至 50 字
        "red_flags": red_flags,
        "green_flags": green_flags,
        "anti_trap_flags": anti_trap_flags,
    }


def apply_buffer_zone(verdict: str, confidence: int) -> tuple[str, bool]:
    """应用缓冲带逻辑，返回 (final_verdict, is_low_confidence_anomaly).

    Args:
        verdict: LLM 输出的 verdict（deep_dive/watch/skip）
        confidence: LLM 输出的 confidence（0-100）

    Returns:
        (final_verdict, is_low_confidence_anomaly)
        - final_verdict: 覆盖后的 verdict
        - is_low_confidence_anomaly: confidence < 40 时为 True

    覆盖规则：
    - confidence >= 60: 信任 verdict（不覆盖）
    - 40 <= confidence < 60: 强制覆盖为 "watch"
    - confidence < 40: 强制覆盖为 "watch" + 标记异常
    """
    if confidence >= 60:
        return verdict, False
    elif confidence >= 40:
        return "watch", False
    else:
        return "watch", True
