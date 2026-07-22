"""weekly_monitor 主循环 — 聚合 → diff → 触发 L2/L3 → 催化检测 → 提醒."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from monitor.aggregation import aggregate_watchlist
from monitor.diff import compute_diff, get_previous_watchlist
from monitor.catalyst import detect_catalysts_batch
from monitor.alert import generate_alerts
from scout.quality import ScoutCache


async def run_weekly(
    l1_output_file: str | None = None,
    watchlist_dir: str | Path = "watchlist",
    force_l2: bool = False,
    force_l3: bool = False,
) -> dict[str, Any]:
    """运行 weekly_monitor 主循环.

    流程：
    1. 聚合 watchlist（L1 + L2 cache + L3 历史）
    2. 计算 diff（与上一快照对比）
    3. 条件触发 L2 重评估（新增 candidate 或 l1_score 变化 >15）
    4. L2 重跑后，用新 verdict 重新判断 L3 触发（verdict 翻转为 deep_dive）
    5. 催化检测（MVP 阶段仅风险信号）
    6. 生成提醒（估值提醒 MVP 暂停 + 风险扫描 + key_variable 提醒）

    Args:
        l1_output_file: L1 产出文件路径（可选，缺省从默认位置读取）
        watchlist_dir: watchlist 输出目录（默认 watchlist/）
        force_l2: 强制重跑 L2（忽略 diff 阈值）
        force_l3: 强制重跑 L3（忽略 diff 阈值）

    Returns:
        weekly 报告 JSON 结构，包含：
        - run_date: 运行日期
        - watchlist: 聚合后的 watchlist
        - diff: diff 报告
        - l2_triggered: L2 重评估的 ticker 列表
        - l3_triggered: L3 深研的 ticker 列表
        - catalyst_reports: 催化检测报告列表
        - alerts: 提醒报告
    """
    run_date = date.today().isoformat()
    watchlist_dir = Path(watchlist_dir)

    print(f"🚀 weekly_monitor 开始运行：{run_date}")

    # 1. 聚合 watchlist
    print("📊 步骤 1/6：聚合 watchlist...")
    scout_cache = ScoutCache()
    watchlist = aggregate_watchlist(
        run_date=run_date,
        l1_output_file=l1_output_file,
        scout_cache=scout_cache,
        watchlist_dir=watchlist_dir,
    )

    # 2. 计算 diff
    print("🔍 步骤 2/6：计算 diff...")
    previous = get_previous_watchlist(run_date, watchlist_dir)
    diff_report = compute_diff(watchlist, previous)

    if diff_report.get("first_run"):
        print("  ℹ️  首次运行，无历史对比")
    else:
        print(f"  - 新增：{len(diff_report['added'])}")
        print(f"  - 移除：{len(diff_report['removed'])}")
        print(f"  - l1_score 变化：{len(diff_report['l1_score_changed'])}")
        print(f"  - stage 升级：{len(diff_report['stage_upgraded'])}")
        print(f"  - stage 降级：{len(diff_report['stage_downgraded'])}")

    # 记录 L2 重跑前的旧 verdict（用于后续判断翻转）
    old_l2_verdict_map: dict[str, str | None] = {}
    for c in watchlist["candidates"]:
        old_l2_verdict_map[c["ticker"]] = c.get("l2_verdict")

    # 3. 条件触发 L2 重评估
    print("🤖 步骤 3/6：L2 重评估...")
    l2_triggers = diff_report.get("l2_triggers", [])
    if force_l2:
        # 强制重跑：所有 candidate
        l2_triggers = [c["ticker"] for c in watchlist["candidates"]]
        print(f"  ⚠️  强制重跑模式：{len(l2_triggers)} 只")
    elif l2_triggers:
        print(f"  - 触发 L2 重评估：{len(l2_triggers)} 只")
    else:
        print("  - 无需重跑 L2")

    l2_triggered = []
    l2_failed = []
    l2_new_verdicts: dict[str, str] = {}  # ticker -> new verdict from L2 rerun
    if l2_triggers:
        print(f"  - 开始 L2 重评估：{len(l2_triggers)} 只")
        from scout.batch import scout_batch

        # 构造 L2 输入（从 watchlist candidates 中提取）
        candidates_to_rerun = [c for c in watchlist["candidates"] if c["ticker"] in l2_triggers]

        try:
            # 调用 scout_batch，force=True 绕过 24h 缓存
            # g1-l2-full-result-contract：返回三元组 (full_results, usage_summary, failure_summary)
            l2_results, _usage, l2_failures = await scout_batch(candidates_to_rerun, force=True)

            # g1-l2-full-result-contract：l2_failed 从 failure_summary["errors"] 取
            # （修复潜伏 bug：旧逻辑从 deep_dive 列表反推 error，但 error 票已被返回点过滤 → l2_failed 永远空）
            l2_failed = [e["ticker"] for e in l2_failures.get("errors", [])]

            # l2_new_verdicts 从 full_results 全量遍历（含 watch/skip/error，非只 deep_dive）
            for result in l2_results:
                ticker = result.get("ticker")
                if ticker in l2_failed:
                    print(f"  ⚠️  {ticker}: L2 评估失败 - {result.get('error', 'unknown')}")
                else:
                    l2_triggered.append(ticker)
                    l2_new_verdicts[ticker] = result.get("verdict", "deep_dive")

            print(f"  ✓ L2 完成：成功 {len(l2_triggered)} 只，失败 {len(l2_failed)} 只")
        except (ConnectionError, TimeoutError, OSError) as e:
            print(f"  ❌ L2 重评估异常：{e}")
            l2_failed.extend(l2_triggers)

    # 4. 条件触发 L3 深研
    # P0 修复：L3 触发基于 L2 重跑后的新 verdict，而非聚合时的旧 verdict
    print("🎓 步骤 4/6：L3 深研...")

    if force_l3:
        # 强制重跑：所有 stage=l2 的 candidate
        l3_triggers = [c["ticker"] for c in watchlist["candidates"] if c.get("stage") == "l2"]
        print(f"  ⚠️  强制重跑模式：{len(l3_triggers)} 只")
    else:
        # 从 L2 重跑结果中判断 verdict 翻转：
        # 旧 verdict 为 None/pass/reject/watch，新 verdict 为 deep_dive → 触发 L3
        l3_triggers = []
        for ticker, new_verdict in l2_new_verdicts.items():
            old_verdict = old_l2_verdict_map.get(ticker)
            if new_verdict == "deep_dive" and old_verdict in (None, "pass", "reject", "watch"):
                l3_triggers.append(ticker)
                print(f"  - {ticker}: L2 verdict 翻转 {old_verdict} → deep_dive，触发 L3")

        if l3_triggers:
            print(f"  - 触发 L3 深研：{len(l3_triggers)} 只（基于 L2 重跑后新 verdict）")
        else:
            print("  - 无需重跑 L3")

    l3_triggered = []
    l3_failed = []
    if l3_triggers:
        print(f"  - 开始 L3 深研：{len(l3_triggers)} 只")
        from council.debate import run_debate

        for ticker in l3_triggers:
            try:
                print(f"    - {ticker}: 运行 L3 深研...")
                await run_debate(ticker, force=True)
                l3_triggered.append(ticker)
                print(f"    ✓ {ticker}: L3 完成")
            except (ConnectionError, TimeoutError, OSError) as e:
                print(f"    ❌ {ticker}: L3 深研失败 - {e}")
                l3_failed.append(ticker)

        print(f"  ✓ L3 完成：成功 {len(l3_triggered)} 只，失败 {len(l3_failed)} 只")

    # 5. 催化检测
    print("🔬 步骤 5/6：催化检测...")
    catalyst_reports = detect_catalysts_batch(watchlist["candidates"], previous)
    risk_signals_count = sum(len(r.get("risk_signals", [])) for r in catalyst_reports)
    print(f"  - 风险信号：{risk_signals_count} 个")

    # 6. 生成提醒
    print("🔔 步骤 6/6：生成提醒...")
    alerts = generate_alerts(watchlist["candidates"], diff_report, catalyst_reports)

    valuation_status = alerts["valuation_alerts"]["status"]
    risk_count = len(alerts["risk_alerts"]["alerts"])
    key_var_count = len(alerts["key_variable_alerts"]["alerts"])

    print(f"  - 估值提醒：{valuation_status}")
    print(f"  - 风险扫描：{risk_count} 个")
    print(f"  - key_variable 提醒：{key_var_count} 个")

    # 构造 weekly 报告
    # g1-canonical-run-identity D2+D6: 周报顶层带 run_id（从 watchlist/L1 继承）
    report = {
        "run_date": run_date,
        "run_id": watchlist.get("run_id"),  # 从 L1 经 aggregate_watchlist 继承
        "profile_version": watchlist.get("profile_version"),
        "input_ticker_set_hash": watchlist.get("input_ticker_set_hash"),
        "watchlist": watchlist,
        "diff": diff_report,
        "l2_triggered": l2_triggered,
        "l2_failed": l2_failed,
        "l3_triggered": l3_triggered,
        "l3_failed": l3_failed,
        "catalyst_reports": catalyst_reports,
        "alerts": alerts,
    }

    # 成本日志（P2 修复：L3 单价 ¥40，design.md AD-03 范围 ¥20-60）
    cost_log = {
        "l2_calls": len(l2_triggered),
        "l2_failed": len(l2_failed),
        "l3_calls": len(l3_triggered),
        "l3_failed": len(l3_failed),
        "estimated_cost_yuan": len(l2_triggered) * 0.01 + len(l3_triggered) * 40.0,
    }
    report["cost_log"] = cost_log

    print(f"\n💰 成本日志：")
    print(f"  - L2 调用：{cost_log['l2_calls']} 次（失败 {cost_log['l2_failed']} 次）")
    print(f"  - L3 调用：{cost_log['l3_calls']} 次（失败 {cost_log['l3_failed']} 次）")
    print(f"  - 预估成本：¥{cost_log['estimated_cost_yuan']:.2f}")

    # 写入报告文件
    report_file = watchlist_dir / f"{run_date}_weekly_report.json"
    with report_file.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n✅ weekly_monitor 完成：{report_file}")
    print(f"  - L1 candidates: {watchlist['l1_candidates']}")
    print(f"  - L2 shortlist: {watchlist['l2_shortlist']}")
    print(f"  - L2 重评估：{len(l2_triggered)} 只")
    print(f"  - L3 深研：{len(l3_triggered)} 只")

    return report
