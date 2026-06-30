"""L3 校准测试（design.md 决策 5, spec council-debate 校准契约）.

校准用例（巴菲特）：
- 看多：600519.SH（贵州茅台）——品牌定价权 + 简单商业模式
- 看空：600900.SH（长江电力）——重资产公用事业，巴菲特不偏好

断言：
- 看多案例：signal == "bullish"
- 看空案例：signal != "bullish"（允许 bearish / neutral / skip）

校准测试调用 assemble_council_features 取真实特征数据，不 mock。
"""
from __future__ import annotations

import asyncio
import sys

from council.debate import run_debate


# 校准用例定义（统一 assert_op + expected_signal 结构）
CALIBRATION_CASES = [
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
]


async def run_calibration() -> bool:
    """运行巴菲特校准测试.

    Returns:
        True 表示全部通过，False 表示有失败

    副作用：
        输出每个用例的 signal/conviction 和通过/失败状态
    """
    all_passed = True

    for case in CALIBRATION_CASES:
        ticker = case["ticker"]
        name = case["name"]

        try:
            # 调用辩论编排器（单 agent 模式）
            result = await run_debate(ticker, force=True)
            actual_signal = result.final_verdict
            actual_conviction = result.rounds[0][0].conviction if result.rounds[0] else 0

            # 判断通过/失败（统一使用 assert_op + expected_signal）
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
            print(f"[{status}] {name} ({ticker}): {expected_desc}")
            print(f"  actual: signal={actual_signal!r}, conviction={actual_conviction}")
            print(f"  reason: {case['reason']}")

            if not passed:
                all_passed = False

        except Exception as e:
            print(f"[FAILED] {name} ({ticker}): exception {e}")
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
