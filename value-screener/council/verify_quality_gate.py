#!/usr/bin/env python3
"""L3 辩论增量验证脚本（AD-09 质量门）.

验证任务：
- 7.1 机制门验证：确认 10 次 LLM 调用成功、DA blind_spots 结构合法、synthesizer 输出完整
- 7.2 质量门验证：人工检查 R1 core_thesis 差异、R2 修订、DA 盲点覆盖
- 7.3 成本验证：记录 token 消耗和费用
- 7.4 质量门不通过回退路径：提供调优建议

使用方法：
    python verify_quality_gate.py --ticker 600519.SH
    python verify_quality_gate.py --ticker 600519.SH --force  # 强制重跑
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

from council.debate import run_debate
from council.features import assemble_council_features
from council.schema import AgentOutput


# ── 可导入的校验函数（f1-deviation-fix §6, G4）──────────────────────────
# 把核心校验逻辑抽成可单测函数，CLI 的 argparse+print 部分只做包装。
# spec debate-quality-gate: R1 输出引用真实特征校验（反向校验）+ 环形引用检测。


def verify_r1_feature_grounding(output: AgentOutput, features: dict) -> tuple[bool, list[str]]:
    """R1 反向特征校验：key_metrics 里的数字必须在 features 任一字段值中出现.

    spec debate-quality-gate Requirement: R1 输出不得含 features 中不存在的凭空数字。
    反向校验比正向（NLP 模糊匹配）可靠——提取 key_metrics 里的数字，检查是否在
    features 任一字段值中出现；含凭空数字则标记幻觉。

    Args:
        output: R1 AgentOutput（含 key_metrics）
        features: assemble_council_features 返回的 features dict

    Returns:
        (ok, issues)：ok=True 通过，issues 为问题列表（空则通过）
    """
    issues: list[str] = []
    # 收集 features 中所有数值（含 list 中的元素、标量），按绝对值 + 容差归一化
    # 用于模糊匹配：R1 常把 -17.84 写成 "17.84"（跌幅取绝对值），或 2.22 写成 "2.2"（四舍五入）
    feature_numbers: list[float] = []
    for v in features.values():
        if isinstance(v, (int, float)):
            feature_numbers.append(abs(float(v)))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, (int, float)):
                    feature_numbers.append(abs(float(item)))

    def _found_in_features(n: float) -> bool:
        """数字 n 是否在 features 任一字段值中（绝对值 + 0.5 容差，模糊匹配）."""
        target = abs(n)
        return any(abs(fv - target) <= 0.5 for fv in feature_numbers)

    for metric in (output.key_metrics or []):
        # 提取该 metric 里的数据点数字，跳过单位/标签语境的数字：
        # - "60日"/"5年"/"3季" → 紧跟 日/年/季 的是时间窗标签，非数据值
        # - "降至15-20倍" → 紧跟 倍 的是单位/预测，非历史数据值
        for m in re.finditer(r"(\d+\.?\d*)", metric):
            n = m.group(1)
            end = m.end()
            next_char = metric[end:end + 1]
            if next_char in ("日", "年", "季", "倍", "期"):
                continue  # 单位/时间窗标签，跳过
            n_val = float(n)
            if _found_in_features(n_val):
                continue
            # 该数字在 features 中找不到来源 → 凭空
            issues.append(
                f"key_metrics '{metric}' 含数字 {n}，但 features 中无对应字段值"
                f"（疑似凭空编造/数据未注入）"
            )

    return (len(issues) == 0), issues


def detect_circular_reference(
    output: AgentOutput,
    agent_ids: tuple[str, ...] | None = None,
) -> tuple[bool, list[str]]:
    """R1 环形引用检测：core_thesis 出现其他 agent_id 名字 → 幻觉引用.

    spec debate-quality-gate Scenario: 环形引用检测。R1（other_opinions=None，本该隔离）
    的 core_thesis 中出现其他 agent_id 的名字（如 buffett 写 "munger 看好..."），
    则 R1 信息隔离被破坏——R1 无 other_opinions 输入，引用他人只能是模型编造。

    Args:
        output: R1 AgentOutput
        agent_ids: 可选，参与互引检测的 agent_id 集合。缺省时动态从
            `council.agents.AGENT_REGISTRY.keys()` 读取（f1-deviation-fix P3 修复：
            原硬编码 (buffett/munger/duan/feng_liu)，张坤加入时漏检；现动态读取，
            且支持调用方注入便于单测——run_debate 可传当前 agents 列表）。

    Returns:
        (ok, issues)：ok=True 通过，issues 为问题列表
    """
    if agent_ids is None:
        # 延迟 import 避免模块加载时耦合；调用时读 AGENT_REGISTRY（测试可 patch）
        from council.agents import AGENT_REGISTRY
        agent_ids = tuple(AGENT_REGISTRY.keys())

    issues: list[str] = []
    thesis = (output.core_thesis or "").lower()
    self_id = output.name.lower()

    for agent_id in agent_ids:
        aid = agent_id.lower()
        if aid == self_id:
            continue  # 自引不算环形
        if aid in thesis:
            issues.append(
                f"R1 core_thesis 引用其他 agent '{agent_id}'（{output.name} 的 R1 应隔离，"
                f"无 other_opinions 输入，引用他人只能是模型编造）"
            )

    return (len(issues) == 0), issues



async def verify_mechanism_gate(ticker: str, force: bool = False) -> bool:
    """7.1 机制门验证.

    验证：
    - 全天团 4 轮完整运行（R1×4 + R2×4 + R3×1 + R4×1 = 10 次 LLM 调用）
    - DA blind_spots 非空且结构合法（每项含 title/detail/which_agents_missed_it）
    - Synthesizer dissent_points/pending_verification 非空
    """
    print(f"\n{'='*60}")
    print(f"7.1 机制门验证: {ticker}")
    print(f"{'='*60}")

    try:
        result = await run_debate(ticker, force=force)

        # 检查 R1: 4 个 agent
        if not result.round1 or len(result.round1) != 4:
            print(f"[FAILED] R1 应有 4 个 agent 输出，实际 {len(result.round1) if result.round1 else 0}")
            return False
        print(f"[PASSED] R1: {len(result.round1)} 个 agent 完成独立判断")

        # 检查 R2: 4 个 agent
        if not result.round2 or len(result.round2) != 4:
            print(f"[FAILED] R2 应有 4 个 agent 输出，实际 {len(result.round2) if result.round2 else 0}")
            return False
        print(f"[PASSED] R2: {len(result.round2)} 个 agent 完成交叉质疑")

        # 检查 R3: DA
        if not result.round3:
            print("[FAILED] R3: DA 输出为空")
            return False

        blind_spots = result.round3.extra.get("blind_spots", [])
        if not blind_spots:
            print("[FAILED] R3: DA blind_spots 为空")
            return False

        # 验证 blind_spots 结构
        for i, bs in enumerate(blind_spots):
            if "title" not in bs:
                print(f"[FAILED] R3: blind_spots[{i}] 缺少 title")
                return False
            if "detail" not in bs:
                print(f"[FAILED] R3: blind_spots[{i}] 缺少 detail")
                return False
            if "which_agents_missed_it" not in bs:
                print(f"[FAILED] R3: blind_spots[{i}] 缺少 which_agents_missed_it")
                return False

        print(f"[PASSED] R3: DA 输出 {len(blind_spots)} 个盲点，结构合法")

        # 检查 R4: Synthesizer
        if not result.round4:
            print("[FAILED] R4: Synthesizer 输出为空")
            return False

        if not result.round4.dissent_points:
            print("[FAILED] R4: dissent_points 为空")
            return False

        if not result.round4.pending_verification:
            print("[FAILED] R4: pending_verification 为空")
            return False

        print(f"[PASSED] R4: Synthesizer 输出完整")
        print(f"  - dissent_points: {len(result.round4.dissent_points)} 项")
        print(f"  - pending_verification: {len(result.round4.pending_verification)} 项")
        print(f"  - consensus_summary: {result.round4.consensus_summary}")

        print(f"\n[机制门 PASSED] 10 次 LLM 调用全部成功，输出结构完整")
        return True

    except Exception as e:
        print(f"[FAILED] 异常: {e}")
        return False


async def verify_quality_gate(ticker: str, force: bool = False) -> bool:
    """7.2 质量门验证（人工检查）.

    输出以下内容供人工检查：
    - R1 core_thesis 差异（4 个 agent 应有本质差异）
    - R2 修订（至少 2 个 agent conviction ±5 或 core_thesis 修改）
    - DA 盲点覆盖（至少 1 个盲点 which_agents_missed_it 含 ≥3 个 agent）
    """
    print(f"\n{'='*60}")
    print(f"7.2 质量门验证（人工检查）: {ticker}")
    print(f"{'='*60}")

    try:
        result = await run_debate(ticker, force=force)

        # R1 core_thesis 差异
        print("\n[R1 core_thesis 差异检查]")
        theses = []
        for agent in result.round1:
            print(f"\n{agent.name}:")
            print(f"  core_thesis: {agent.core_thesis}")
            print(f"  conviction: {agent.conviction}")
            theses.append(agent.core_thesis)

        # 简单检查是否有重复
        unique_theses = len(set(theses))
        if unique_theses < 3:
            print(f"\n[WARNING] R1 core_thesis 同质化风险: {unique_theses}/4 个唯一论点")
            print("建议: 增强各 agent prompt 的差异点")
        else:
            print(f"\n[INFO] R1 core_thesis: {unique_theses}/4 个唯一论点")

        # f1-deviation-fix §6：R1 特征接地 + 环形引用校验（spec debate-quality-gate）
        print("\n[R1 特征接地 + 环形引用校验]")
        grounding_failures = 0
        circular_failures = 0
        features = assemble_council_features(ticker)
        # features 不足时跳过反向校验（已在 R1 入口 fail-fast，此处 features 可能空）
        if "error" in features:
            print("[INFO] features 不足（insufficient_data），跳过反向特征校验")
            features = {}
        for agent in result.round1:
            ok_ground, ground_issues = verify_r1_feature_grounding(agent, features)
            ok_circ, circ_issues = detect_circular_reference(agent)
            if not ok_ground:
                grounding_failures += 1
                print(f"  [❌ 幻觉] {agent.name}: {ground_issues}")
            if not ok_circ:
                circular_failures += 1
                print(f"  [❌ 环形引用] {agent.name}: {circ_issues}")
        if grounding_failures == 0 and circular_failures == 0:
            print(f"  [PASSED] R1 全部 agent 引用真实特征、无环形引用")
        else:
            print(f"  [WARNING] 接地失败 {grounding_failures} 个，环形引用 {circular_failures} 个"
                  f"——若 features 充足仍失败，触发根因排查（数据未注入或模型幻觉）")

        # R2 修订检查
        print("\n[R2 修订检查]")
        revision_count = 0
        for r1_agent, r2_agent in zip(result.round1, result.round2):
            conviction_diff = abs(r2_agent.conviction - r1_agent.conviction)
            thesis_changed = r2_agent.core_thesis != r1_agent.core_thesis

            if conviction_diff >= 5 or thesis_changed:
                revision_count += 1
                print(f"\n{r1_agent.name}: conviction {r1_agent.conviction} → {r2_agent.conviction} (diff: {conviction_diff})")
                if thesis_changed:
                    print(f"  R1: {r1_agent.core_thesis}")
                    print(f"  R2: {r2_agent.core_thesis}")

        if revision_count < 2:
            print(f"\n[WARNING] R2 修订不足: 仅 {revision_count}/4 个 agent 修订（需 ≥2）")
            print("建议: 在 R2 prompt 中强调交叉质疑的重要性")
        else:
            print(f"\n[INFO] R2 修订: {revision_count}/4 个 agent 有实质修订")

        # DA 盲点覆盖检查
        print("\n[DA 盲点覆盖检查]")
        blind_spots = result.round3.extra.get("blind_spots", [])
        high_coverage_count = 0
        for bs in blind_spots:
            missed_by = bs.get("which_agents_missed_it", [])
            print(f"\n盲点: {bs.get('title')}")
            print(f"  detail: {bs.get('detail')}")
            print(f"  which_agents_missed_it: {missed_by} ({len(missed_by)} 个 agent)")
            if len(missed_by) >= 3:
                high_coverage_count += 1

        if high_coverage_count < 1:
            print(f"\n[WARNING] DA 盲点覆盖不足: 仅 {high_coverage_count} 个盲点被 ≥3 个 agent 忽略（需 ≥1）")
            print("建议: 在 DA prompt 中加 few-shot 示例，强调找共识盲区")
        else:
            print(f"\n[INFO] DA 盲点覆盖: {high_coverage_count} 个盲点被 ≥3 个 agent 忽略")

        print(f"\n[质量门 人工检查完成] 请根据上述输出判断是否通过")
        return True

    except Exception as e:
        print(f"[FAILED] 异常: {e}")
        return False


async def verify_cost(ticker: str, force: bool = False) -> bool:
    """7.3 成本验证.

    记录全天团单股 LLM 调用次数 + token 消耗（f1-deviation-fix §7：call_llm 已采集 usage，
    run_debate 写入辩论记录 md 的 `## Token Usage` 段，此处解析汇总）。
    """
    print(f"\n{'='*60}")
    print(f"7.3 成本验证: {ticker}")
    print(f"{'='*60}")

    try:
        result = await run_debate(ticker, force=force)

        r1_count = len(result.round1) if result.round1 else 0
        r2_count = len(result.round2) if result.round2 else 0
        r3_count = 1 if result.round3 else 0
        r4_count = 1 if result.round4 else 0
        total = r1_count + r2_count + r3_count + r4_count

        print("\n[成本记录]")
        print(f"  R1: {r1_count} 次 LLM 调用（重度推理）")
        print(f"  R2: {r2_count} 次 LLM 调用（重度推理）")
        print(f"  R3: {r3_count} 次 LLM 调用（重度推理，DA）")
        print(f"  R4: {r4_count} 次 LLM 调用（中度推理，Synthesizer）")
        print(f"  总计: {total} 次 LLM 调用")

        # 解析辩论记录 md 的 Token Usage 段（f1-deviation-fix §7）
        usage_summary = _parse_usage_from_debate(result.debate_path)
        if usage_summary:
            print(f"  prompt_tokens 合计: {usage_summary['prompt_tokens']}")
            print(f"  completion_tokens 合计: {usage_summary['completion_tokens']}")
            print(f"  total_tokens 合计: {usage_summary['total_tokens']}")
            # AD-03 粗略费用估算（按 DeepSeek 定价 ≈¥0.001/1k token，仅参考量级）
            est_cost = usage_summary["total_tokens"] / 1000 * 0.001
            print(f"  费用估算: ≈¥{est_cost:.4f}（参考量级，按 ¥0.001/1k token）")
        else:
            print("  token usage: 未采集到（可能为 mock 或 API 未返回 usage 字段）")

        return True

    except Exception as e:
        print(f"[FAILED] 异常: {e}")
        return False


def _parse_usage_from_debate(debate_path: str | Path | None) -> dict | None:
    """从辩论记录 md 解析 `## Token Usage` 段（f1-deviation-fix §7）.

    run_debate 把 usage_log 写成 md 末尾的 JSON 块。返回汇总 dict
    {prompt_tokens, completion_tokens, total_tokens, call_count}，无则 None。
    """
    if not debate_path:
        return None
    p = Path(debate_path)
    if not p.exists():
        return None

    text = p.read_text(encoding="utf-8")
    marker = "## Token Usage"
    idx = text.find(marker)
    if idx < 0:
        return None

    # 找 marker 之后的第一个 ```json ... ``` 块
    json_start = text.find("```json", idx)
    if json_start < 0:
        return None
    json_start = text.find("\n", json_start) + 1
    json_end = text.find("```", json_start)
    if json_end < 0:
        return None
    block = text[json_start:json_end].strip()

    try:
        usage_log = json.loads(block)
    except json.JSONDecodeError:
        return None

    if not isinstance(usage_log, list) or not usage_log:
        return None

    return {
        "call_count": len(usage_log),
        "prompt_tokens": sum(int(u.get("prompt_tokens", 0) or 0) for u in usage_log),
        "completion_tokens": sum(int(u.get("completion_tokens", 0) or 0) for u in usage_log),
        "total_tokens": sum(int(u.get("total_tokens", 0) or 0) for u in usage_log),
    }


def print_fallback_path():
    """7.4 质量门不通过回退路径."""
    print(f"\n{'='*60}")
    print(f"7.4 质量门不通过回退路径")
    print(f"{'='*60}")

    print("""
若质量门不通过，按以下路径调优：

1. R1 core_thesis 同质化
   - 优先调 prompt：增强各 agent 的差异点
   - 巴菲特：强调护城河和安全边际
   - 芒格：强调逆向思考和心理偏差
   - 段永平：强调商业模式和管理层本分
   - 冯柳：强调弱势研究法和认知差

2. R2 修订不足
   - 在 R2 prompt 中强调交叉质疑的重要性
   - 添加示例："如果其他 agent 的观点与你不同，你应该重新审视自己的判断"

3. DA 泛泛而谈
   - 在 DA prompt 中加 few-shot 示例
   - 强调盲点必须具体：
     * 差："管理层风险"
     * 好："管理层去年减持了 15%，且薪酬结构与股东利益不一致"

4. DA 盲点覆盖不足
   - 在 DA prompt 中强调找"共识盲区"
   - 示例："如果 4 个 agent 都看好，你要找他们都忽略的风险"
""")


async def main():
    parser = argparse.ArgumentParser(description="L3 辩论增量验证")
    parser.add_argument("--ticker", required=True, help="股票代码，如 600519.SH")
    parser.add_argument("--force", action="store_true", help="强制重跑（跳过缓存）")
    parser.add_argument("--gate", choices=["mechanism", "quality", "cost", "all"],
                       default="all", help="验证哪个质量门")
    args = parser.parse_args()

    print(f"L3 辩论增量验证: {args.ticker}")
    print(f"强制重跑: {args.force}")

    results = {}

    if args.gate in ("mechanism", "all"):
        results["mechanism"] = await verify_mechanism_gate(args.ticker, args.force)

    if args.gate in ("quality", "all"):
        results["quality"] = await verify_quality_gate(args.ticker, args.force)

    if args.gate in ("cost", "all"):
        results["cost"] = await verify_cost(args.ticker, args.force)

    if args.gate == "all":
        print_fallback_path()

    # 汇总
    print(f"\n{'='*60}")
    print("验证汇总")
    print(f"{'='*60}")
    for gate, passed in results.items():
        status = "PASSED" if passed else "FAILED"
        print(f"[{status}] {gate}")

    all_passed = all(results.values())
    if all_passed:
        print("\n[ALL PASSED] 质量门验证通过")
        return 0
    else:
        print("\n[SOME FAILED] 质量门验证未完全通过")
        print("请参考 7.4 回退路径进行调优")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
