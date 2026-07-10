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


# ── f2 §5 新增校验函数 ─────────────────────────────────────────


def verify_r2_new_evidence(output: AgentOutput, features: dict) -> tuple[bool, list[str]]:
    """R2 新证据校验（f2 §5.1/5.2，soft warning 语义，D2 scope 调整 2026-07-10）.

    soft 语义：所有不合规情况都返回 pass=True + warnings（不拦截），f3 落地后升 hard gate。
    - new_evidence 非空 → 通过（数字反向校验，编造记 soft warning）
    - evidence_exhausted=true → 通过
    - 两者皆无 → soft warning（r2_no_new_evidence）
    - new_evidence 含凭空数字 → soft warning（suspected_fabricated_evidence）

    数字反向校验复用 verify_r1_feature_grounding 的逻辑（提取数字查 features），
    但降级为 warning 而非 hard fail。
    """
    warnings: list[str] = []

    new_evidence = getattr(output, "new_evidence", []) or []
    evidence_exhausted = getattr(output, "evidence_exhausted", False)

    if evidence_exhausted:
        return True, []
    if not new_evidence:
        return True, ["soft: r2_no_new_evidence"]

    # 数字反向校验（复用 verify_r1_feature_grounding 的数字提取逻辑）
    feature_numbers: list[float] = []
    for v in features.values():
        if isinstance(v, (int, float)):
            feature_numbers.append(abs(float(v)))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, (int, float)):
                    feature_numbers.append(abs(float(item)))

    def _found_in_features(n: float) -> bool:
        target = abs(n)
        return any(abs(fv - target) <= 0.5 for fv in feature_numbers)

    for metric in new_evidence:
        for m in re.finditer(r"(\d+\.?\d*)", metric):
            n = m.group(1)
            end = m.end()
            next_char = metric[end:end + 1]
            if next_char in ("日", "年", "季", "倍", "期"):
                continue
            n_val = float(n)
            if not _found_in_features(n_val):
                warnings.append(
                    f"soft: suspected_fabricated_evidence — new_evidence '{metric}' "
                    f"含数字 {n}，但 features 中无对应字段值"
                )

    return True, warnings


def verify_divergence_report(syn_output) -> tuple[bool, list[str]]:
    """R4 分歧报告完整性校验（f2 §5.3/5.4，hard gate）.

    - divergence_level 非空 → 必填
    - divergence_level 为 high/extreme 时 key_disagreements 必须非空
    - calibration_status 必须为 "uncalibrated"
    """
    issues: list[str] = []

    level = getattr(syn_output, "divergence_level", None)
    if not level:
        issues.append("divergence_level 缺失（R4 必须输出分歧等级）")

    key_disagreements = getattr(syn_output, "key_disagreements", []) or []
    if level in ("high", "extreme") and not key_disagreements:
        issues.append(
            f"divergence_level={level} 时 key_disagreements 必须非空"
            f"（需列出结构化分歧点）"
        )

    calibration = getattr(syn_output, "calibration_status", "uncalibrated")
    if calibration != "uncalibrated":
        issues.append(
            f"calibration_status 必须为 'uncalibrated'，实际 {calibration!r}"
            f"（conviction 未校准，诚实声明）"
        )

    return (len(issues) == 0), issues


def verify_da_fact_check(
    da_output,
    agent_ids: tuple[str, ...] | None = None,
    da_skipped_reason: str | None = None,
) -> tuple[bool, list[str]]:
    """DA 仲裁事实回查校验（f2 §5.5/5.6，含 DA skipped 分支，spec review #3）.

    DA ran（da_output 非空）：
    - extra.evidence_quality_assessment 非空 → 通过；缺失 → 拦截
    - recommendation 引用 agent_id 必须在 AGENT_REGISTRY 或 "no_clear_winner"
    DA skipped（da_output=None，按 da_skipped_reason 分流）：
    - 情况 A（low/extreme_divergence）→ 跳过（pass=True + 空 warnings）
    - 情况 B（evidence_exhausted/runtime_degraded）→ soft warning
    """
    # DA skipped 分支
    if da_output is None:
        if da_skipped_reason in ("low_divergence", "extreme_divergence"):
            return True, []  # 情况 A：跳过
        if da_skipped_reason in ("evidence_exhausted", "runtime_degraded"):
            return True, [
                f"soft: da_skipped — reason={da_skipped_reason}, "
                f"R1/R2 evidence not fact-checked"
            ]
        # da_output=None 但 reason 未知 → 信息缺口，soft warning
        return True, ["soft: da_skipped — reason unknown, evidence not fact-checked"]

    # DA ran：动态读 AGENT_REGISTRY（复用 f1 P3 修复模式）
    if agent_ids is None:
        from council.agents import AGENT_REGISTRY
        agent_ids = tuple(AGENT_REGISTRY.keys())

    issues: list[str] = []
    extra = getattr(da_output, "extra", {}) or {}

    evidence_quality = extra.get("evidence_quality_assessment")
    if not evidence_quality or not isinstance(evidence_quality, dict):
        issues.append(
            "DA 缺 evidence_quality_assessment（未做事实回查，退化成纯文字评估风险）"
        )
        return (len(issues) == 0), issues

    # recommendation 引用 agent_id 校验
    recommendation = extra.get("recommendation")
    if recommendation and recommendation != "no_clear_winner":
        # 格式 "defer_to_<agent_id>_consensus"
        if recommendation.startswith("defer_to_") and recommendation.endswith("_consensus"):
            cited_agent = recommendation[len("defer_to_"):-len("_consensus")]
            if cited_agent not in agent_ids:
                issues.append(
                    f"recommendation 引用不存在的 agent_id '{cited_agent}'"
                    f"（不在 AGENT_REGISTRY）"
                )
        else:
            issues.append(
                f"recommendation 格式非法：{recommendation!r}"
                f"（应为 'defer_to_<agent_id>_consensus' 或 'no_clear_winner'）"
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

        # 检查 R1（f2 §3.5：降级时 R1 可能 <4，幸存 agent 数）
        if not result.round1:
            print(f"[FAILED] R1 无 agent 输出（全失败）")
            return False
        print(f"[PASSED] R1: {len(result.round1)} 个 agent 完成独立判断"
              + (f"（运行时降级，幸存 {len(result.round1)}/{4}）" if result.council_degraded else ""))

        # 检查 R2: 4 个 agent（f2 §3：low/extreme 分流或降级时 R2=None，属设计行为非失败）
        if result.round2 is None:
            print(f"[INFO] R2 被跳过（da_skipped_reason={result.da_skipped_reason}）— 分流/降级属设计行为")
        else:
            if len(result.round2) != len(result.round1):
                print(f"[FAILED] R2 应有 {len(result.round1)} 个 agent 输出，实际 {len(result.round2)}")
                return False
            print(f"[PASSED] R2: {len(result.round2)} 个 agent 完成交叉质疑")

        # 检查 R3: DA（f2 §3：DA 可被 skip——low/extreme 分流、evidence_exhausted、降级）
        if result.round3 is None:
            print(f"[INFO] R3 DA 被跳过（da_skipped_reason={result.da_skipped_reason}）— 属设计行为")
        else:
            blind_spots = result.round3.extra.get("blind_spots", [])
            if not blind_spots:
                print("[FAILED] R3: DA blind_spots 为空")
                return False

            # 验证 blind_spots 结构
            for i, bs in enumerate(blind_spots):
                for key in ("title", "detail", "which_agents_missed_it"):
                    if key not in bs:
                        print(f"[FAILED] R3: blind_spots[{i}] 缺少 {key}")
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

        # f2 §3：分流/降级时 LLM 调用次数 < 10 属正常（低分歧跳 R2/R3，降级跳 R2/R3）
        if result.council_degraded:
            print(f"\n[机制门 PASSED] 运行时降级模式：R1(幸存) + R4，跳过 R2/R3")
        elif result.round2 is None:
            print(f"\n[机制门 PASSED] 分流模式：R1 + R4，跳过 R2/R3（da_skipped={result.da_skipped_reason}）")
        else:
            print(f"\n[机制门 PASSED] 全 4 轮运行，输出结构完整")
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

        # R2 修订检查（f2 §3：round2 可能为 None——low/extreme 分流或降级跳 R2）
        print("\n[R2 修订检查]")
        if result.round2 is None:
            da_reason = result.da_skipped_reason or "(未跳过)"
            print(f"[INFO] R2 被跳过（da_skipped_reason={da_reason}），跳过 R2 修订检查")
        else:
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
                print(f"\n[WARNING] R2 修订不足: 仅 {revision_count}/{len(result.round2)} 个 agent 修订（需 ≥2）")
            else:
                print(f"\n[INFO] R2 修订: {revision_count}/{len(result.round2)} 个 agent 有实质修订")

        # DA 盲点覆盖检查（f2 §3：round3 可能为 None——DA skipped）
        print("\n[DA 盲点覆盖检查]")
        if result.round3 is None:
            da_reason = result.da_skipped_reason or "unknown"
            print(f"[INFO] DA 被跳过（da_skipped_reason={da_reason}），跳过盲点覆盖检查")
            if result.council_degraded:
                print(f"[INFO] 运行时降级（degraded_reason={result.degraded_reason}）")
        else:
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
            else:
                print(f"\n[INFO] DA 盲点覆盖: {high_coverage_count} 个盲点被 ≥3 个 agent 忽略")

        # f2 §5.7：三个新校验（soft warning / hard fail / pass 三态）
        # f2 CR P1#2：机器 hard gate（divergence/DA fact-check）fail 时 return False，
        # 非无条件 True。人工检查项（R1 同质化/R2 修订/DA 盲点）保持 WARNING 不阻断。
        hard_fail = False
        print("\n[f2 §5 新增校验]")
        # 1. R2 新证据校验（soft warning）
        if result.round2 is not None:
            for agent in result.round2:
                ok_ev, w_ev = verify_r2_new_evidence(agent, features)
                if w_ev:
                    print(f"  [SOFT WARNING] {agent.name} R2 新证据: {w_ev}（不阻断）")
                else:
                    print(f"  [PASS] {agent.name} R2 新证据校验通过")

        # 2. 分歧报告完整性校验（hard gate）
        if result.round4 is not None:
            ok_div, issues_div = verify_divergence_report(result.round4)
            if ok_div:
                print(f"  [PASS] R4 分歧报告完整性校验通过（level={result.round4.divergence_level}）")
            else:
                print(f"  [❌ HARD FAIL] R4 分歧报告: {issues_div}")
                hard_fail = True

        # 3. DA 事实回查校验（含 skipped 分支）
        ok_da, issues_da = verify_da_fact_check(
            result.round3, da_skipped_reason=result.da_skipped_reason
        )
        if result.round3 is None:
            # DA skipped：ok_da=True，issues_da 为空（A）或 soft warning（B）
            if issues_da:
                print(f"  [SOFT WARNING] DA skipped: {issues_da}（不阻断）")
            else:
                print(f"  [PASS] DA skipped（{result.da_skipped_reason}），情况 A 跳过校验")
        else:
            if ok_da:
                print(f"  [PASS] DA 事实回查校验通过")
            else:
                print(f"  [❌ HARD FAIL] DA 事实回查: {issues_da}")
                hard_fail = True

        print(f"\n[质量门 人工检查完成] 请根据上述输出判断是否通过")
        return not hard_fail

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
