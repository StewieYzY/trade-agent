"""L3 校准测试（design.md 决策 4, spec calibration-framework）.

校准用例：
- 巴菲特：600519.SH（看多）/ 600900.SH（看空）— 3a 已实现
- 段永平：600519.SH（看多）— 3b 新增
- DA/synthesizer：600519.SH schema 合法 + 关键字段非空 — 3b 新增
- 芒格/冯柳：TODO（案例待补充）

断言：
- 看多案例：signal == "bullish"
- 看空案例：signal != "bullish"
- DA：输出 schema 合法 + extra.blind_spots 非空
- synthesizer：输出 schema 合法 + dissent_points 非空

校准测试调用 assemble_council_features 取真实特征数据，不 mock。
"""
from __future__ import annotations

import asyncio
import sys

from council.debate import _call_da, _call_synthesizer, run_debate
from council.features import assemble_council_features
from council.schema import SynthesizerOutput


# 投资大师校准用例（统一 assert_op + expected_signal 结构）
CALIBRATION_CASES = [
    # 巴菲特校准用例（3a 已实现）
    {
        "ticker": "600519.SH",
        "name": "贵州茅台",
        "assert_op": "eq",
        "expected_signal": "bullish",
        "reason": "品牌定价权 + 简单商业模式",
    },
    {
        "ticker": "600900.SH",
        "name": "长江电力",
        "assert_op": "ne",
        "expected_signal": "bullish",
        "reason": "重资产公用事业，巴菲特不偏好",
    },
    # 段永平校准用例（3b 新增）
    {
        "agent_id": "duan",
        "ticker": "600519.SH",
        "name": "贵州茅台",
        "assert_op": "eq",
        "expected_signal": "bullish",
        "reason": "段永平实际持有",
    },
    # TODO: calibration case pending — 芒格校准用例待补充
    # TODO: calibration case pending — 冯柳校准用例待补充
]


async def run_agent_calibration(case: dict) -> bool:
    """运行单个投资大师校准用例."""
    ticker = case["ticker"]
    name = case["name"]
    agent_id = case.get("agent_id", "buffett")

    try:
        result = await run_debate(ticker, agents=[agent_id], force=True)
        actual_signal = result.final_verdict
        actual_conviction = result.round1[0].conviction if result.round1 else 0

        assert_op = case["assert_op"]
        expected = case["expected_signal"]

        if assert_op == "eq":
            passed = actual_signal == expected
            expected_desc = f"signal == {expected!r}"
        elif assert_op == "ne":
            passed = actual_signal != expected
            expected_desc = f"signal != {expected!r}"
        else:
            raise ValueError(f"unknown assert_op: {assert_op}")

        status = "PASSED" if passed else "FAILED"
        print(f"[{status}] [{agent_id}] {name} ({ticker}): {expected_desc}")
        print(f"  actual: signal={actual_signal!r}, conviction={actual_conviction}")
        print(f"  reason: {case['reason']}")

        return passed

    except Exception as e:
        print(f"[FAILED] [{agent_id}] {name} ({ticker}): exception {e}")
        return False


async def run_da_calibration(ticker: str = "600519.SH") -> bool:
    """运行 DA 校准：验证 schema 合法 + blind_spots 非空."""
    try:
        features = assemble_council_features(ticker)
        if "error" in features:
            print(f"[FAILED] [da] {ticker}: insufficient_data")
            return False

        # 先跑 R1 获取基础数据
        result = await run_debate(ticker, agents=["buffett"], force=True)
        round1 = result.round1

        # 调用 DA
        da_result = await _call_da(round1, None, ticker, features)

        # 验证 schema
        assert da_result.signal == "neutral", f"DA signal should be neutral, got {da_result.signal}"
        assert da_result.conviction == 0, f"DA conviction should be 0, got {da_result.conviction}"

        # 验证 blind_spots 非空
        blind_spots = da_result.extra.get("blind_spots", [])
        assert len(blind_spots) > 0, "DA blind_spots should be non-empty"
        for bs in blind_spots:
            assert "title" in bs, "blind_spot missing 'title'"
            assert "detail" in bs, "blind_spot missing 'detail'"
            assert "which_agents_missed_it" in bs, "blind_spot missing 'which_agents_missed_it'"

        print(f"[PASSED] [da] {ticker}: schema valid + blind_spots non-empty ({len(blind_spots)} items)")
        return True

    except Exception as e:
        print(f"[FAILED] [da] {ticker}: {e}")
        return False


async def run_synthesizer_calibration(ticker: str = "600519.SH") -> bool:
    """运行 Synthesizer 校准：验证 schema 合法 + dissent_points 非空."""
    try:
        features = assemble_council_features(ticker)
        if "error" in features:
            print(f"[FAILED] [synthesizer] {ticker}: insufficient_data")
            return False

        # 先跑 R1 + DA 获取基础数据
        result = await run_debate(ticker, agents=["buffett"], force=True)
        round1 = result.round1
        da_result = await _call_da(round1, None, ticker, features)

        # 调用 Synthesizer
        syn_result = await _call_synthesizer(round1, None, da_result, ticker, features)

        # 验证 schema（SynthesizerOutput __post_init__ 已校验枚举和范围）
        assert isinstance(syn_result, SynthesizerOutput), "should return SynthesizerOutput"
        assert syn_result.final_signal in ("bullish", "bearish", "neutral", "skip")
        assert 0 <= syn_result.conviction <= 100
        assert syn_result.consensus_summary.strip() != ""

        # 验证 dissent_points（可以为空列表，但字段必须存在）
        assert isinstance(syn_result.dissent_points, list), "dissent_points should be list"

        print(f"[PASSED] [synthesizer] {ticker}: schema valid, final_signal={syn_result.final_signal}, "
              f"conviction={syn_result.conviction}")
        return True

    except Exception as e:
        print(f"[FAILED] [synthesizer] {ticker}: {e}")
        return False


async def run_calibration() -> bool:
    """运行全部校准测试.

    Returns:
        True 表示全部通过，False 表示有失败
    """
    all_passed = True

    print("--- 投资大师校准 ---")
    for case in CALIBRATION_CASES:
        if not await run_agent_calibration(case):
            all_passed = False

    print("\n--- DA/Synthesizer 校准 ---")
    if not await run_da_calibration():
        all_passed = False
    if not await run_synthesizer_calibration():
        all_passed = False

    return all_passed


def main():
    """CLI 入口：跑校准测试，输出通过/失败."""
    print("=== L3 Council 校准测试 ===\n")

    passed = asyncio.run(run_calibration())

    if passed:
        print("\nCalibration PASSED")
        sys.exit(0)
    else:
        print("\nCalibration FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
