"""diff 引擎 — watchlist 增量检测 + 历史轨迹查询."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def compute_diff(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    """计算两个 watchlist 快照之间的 diff.

    Args:
        current: 当前 watchlist JSON 结构
        previous: 上一快照 watchlist JSON 结构（可为 None，表示首次运行）

    Returns:
        diff 报告 JSON 结构，包含：
        - first_run: bool（是否首次运行）
        - added: list[str]（新增 ticker）
        - removed: list[str]（移除 ticker）
        - l1_score_changed: list[dict]（l1_score 变化 >10）
        - stage_upgraded: list[dict]（stage 升级）
        - stage_downgraded: list[dict]（stage 降级）
        - verdict_changed: list[dict]（l3_verdict 变化）
        - valuation_low: list[dict]（pe_percentile_5y 触及低位阈值）
        - l2_triggers: list[str]（需重跑 L2 的 ticker）
        - l3_triggers: list[str]（需重跑 L3 的 ticker）
    """
    if previous is None:
        return {
            "first_run": True,
            "message": "首次运行，无历史对比",
            "added": [],
            "removed": [],
            "l1_score_changed": [],
            "stage_upgraded": [],
            "stage_downgraded": [],
            "verdict_changed": [],
            "valuation_low": [],
            "l2_triggers": [],
            "l3_triggers": [],
        }

    # 构建 ticker → candidate 映射
    curr_map = {c["ticker"]: c for c in current.get("candidates", [])}
    prev_map = {c["ticker"]: c for c in previous.get("candidates", [])}

    curr_tickers = set(curr_map.keys())
    prev_tickers = set(prev_map.keys())

    # 1. 新增/移除
    added = sorted(curr_tickers - prev_tickers)
    removed = sorted(prev_tickers - curr_tickers)

    # 2. 逐项对比
    l1_score_changed = []
    stage_upgraded = []
    stage_downgraded = []
    verdict_changed = []
    valuation_low = []

    for ticker in sorted(curr_tickers & prev_tickers):
        curr = curr_map[ticker]
        prev = prev_map[ticker]

        # l1_score 变化
        curr_score = curr.get("l1_score")
        prev_score = prev.get("l1_score")
        if curr_score is not None and prev_score is not None:
            delta = abs(curr_score - prev_score)
            if delta > 10:
                l1_score_changed.append({
                    "ticker": ticker,
                    "previous": prev_score,
                    "current": curr_score,
                    "delta": curr_score - prev_score,
                })

        # stage 变化
        curr_stage = curr.get("stage", "l1")
        prev_stage = prev.get("stage", "l1")
        stage_order = {"l1": 1, "l2": 2, "l3": 3}

        if stage_order.get(curr_stage, 1) > stage_order.get(prev_stage, 1):
            stage_upgraded.append({
                "ticker": ticker,
                "previous": prev_stage,
                "current": curr_stage,
            })
        elif stage_order.get(curr_stage, 1) < stage_order.get(prev_stage, 1):
            stage_downgraded.append({
                "ticker": ticker,
                "previous": prev_stage,
                "current": curr_stage,
            })

        # l3_verdict 变化
        curr_verdict = curr.get("l3_verdict")
        prev_verdict = prev.get("l3_verdict")
        if (curr_verdict and prev_verdict and
            curr_verdict != "unknown" and prev_verdict != "unknown" and
            curr_verdict != prev_verdict):
            verdict_changed.append({
                "ticker": ticker,
                "previous": prev_verdict,
                "current": curr_verdict,
            })

        # pe_percentile_5y 触及低位阈值
        curr_pe = curr.get("pe_percentile_5y")
        prev_pe = prev.get("pe_percentile_5y")
        if (curr_pe is not None and prev_pe is not None and
            prev_pe >= 20.0 and curr_pe < 20.0):
            valuation_low.append({
                "ticker": ticker,
                "previous": prev_pe,
                "current": curr_pe,
            })

    # 3. 计算触发条件
    l2_triggers = []
    l3_triggers = []

    # L2 触发：新增 candidate 或 l1_score 变化 >15
    l2_triggers.extend(added)
    for item in l1_score_changed:
        if abs(item["delta"]) > 15:
            l2_triggers.append(item["ticker"])

    # L3 触发：l2_verdict 翻转为 deep_dive
    for ticker in sorted(curr_tickers & prev_tickers):
        curr = curr_map[ticker]
        prev = prev_map[ticker]
        curr_verdict = curr.get("l2_verdict")
        prev_verdict = prev.get("l2_verdict")
        if (curr_verdict == "deep_dive" and
            prev_verdict in (None, "pass", "reject", "watch")):
            l3_triggers.append(ticker)

    return {
        "first_run": False,
        "added": added,
        "removed": removed,
        "l1_score_changed": l1_score_changed,
        "stage_upgraded": stage_upgraded,
        "stage_downgraded": stage_downgraded,
        "verdict_changed": verdict_changed,
        "valuation_low": valuation_low,
        "l2_triggers": sorted(set(l2_triggers)),
        "l3_triggers": sorted(set(l3_triggers)),
    }


def get_latest_watchlist(watchlist_dir: str | Path = "watchlist") -> tuple[str, dict[str, Any]] | None:
    """获取最新的 watchlist 快照.

    Returns:
        (date_str, watchlist_data) 或 None（无快照）
    """
    watchlist_dir = Path(watchlist_dir)
    if not watchlist_dir.exists():
        return None

    files = sorted(watchlist_dir.glob("*.json"), reverse=True)
    for f in files:
        # 跳过 per-ticker 和 report 文件（含 _ 的都不是纯日期 watchlist）
        if "_" in f.stem:
            continue
        try:
            with f.open(encoding="utf-8") as fp:
                data = json.load(fp)
            return (f.stem, data)
        except (json.JSONDecodeError, OSError):
            continue

    return None


def get_previous_watchlist(
    current_date: str,
    watchlist_dir: str | Path = "watchlist",
) -> dict[str, Any] | None:
    """获取 current_date 之前的最新快照.

    Args:
        current_date: 当前日期（YYYY-MM-DD）
        watchlist_dir: watchlist 目录

    Returns:
        上一快照 watchlist JSON 结构，或 None（无历史快照）
    """
    watchlist_dir = Path(watchlist_dir)
    if not watchlist_dir.exists():
        return None

    current_dt = datetime.strptime(current_date, "%Y-%m-%d").date()

    # 收集所有日期文件
    date_files = []
    for f in watchlist_dir.glob("*.json"):
        # 跳过 per-ticker 和 report 文件（含 _ 的都不是纯日期 watchlist）
        if "_" in f.stem:
            continue
        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d").date()
            if file_date < current_dt:
                date_files.append((file_date, f))
        except ValueError:
            continue

    if not date_files:
        return None

    # 取最新的一个
    date_files.sort(reverse=True)
    _, latest_file = date_files[0]

    try:
        with latest_file.open(encoding="utf-8") as fp:
            return json.load(fp)
    except (json.JSONDecodeError, OSError):
        return None


def history(
    ticker: str,
    date_from: str | None = None,
    date_to: str | None = None,
    watchlist_dir: str | Path = "watchlist",
) -> list[dict[str, Any]]:
    """查询单只股票的历史轨迹.

    Args:
        ticker: 股票代码
        date_from: 起始日期（YYYY-MM-DD，可选）
        date_to: 截止日期（YYYY-MM-DD，可选）
        watchlist_dir: watchlist 目录

    Returns:
        历史记录列表，每项包含：
        - date: 日期
        - l1_score: L1 综合得分
        - stage: 当前阶段
        - l3_verdict: L3 verdict
        - pe_percentile_5y: PE 5年分位
    """
    watchlist_dir = Path(watchlist_dir)
    if not watchlist_dir.exists():
        return []

    # 解析日期范围
    from_dt = datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None
    to_dt = datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None

    records = []
    for f in sorted(watchlist_dir.glob("*.json")):
        # 跳过 per-ticker 文件（格式：{date}_{ticker}.json）
        if f.stem.count("_") > 0:
            continue

        try:
            file_date = datetime.strptime(f.stem, "%Y-%m-%d").date()
        except ValueError:
            continue

        # 日期范围过滤
        if from_dt and file_date < from_dt:
            continue
        if to_dt and file_date > to_dt:
            continue

        try:
            with f.open(encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            continue

        # 查找该 ticker
        for c in data.get("candidates", []):
            if c["ticker"] == ticker:
                records.append({
                    "date": f.stem,
                    "l1_score": c.get("l1_score"),
                    "stage": c.get("stage", "l1"),
                    "l3_verdict": c.get("l3_verdict"),
                    "pe_percentile_5y": c.get("pe_percentile_5y"),
                })
                break

    # P3 修复：tasks 3.5 要求快照数 > 50 时提示缩小范围
    if len(records) > 50:
        print(f"⚠️  找到 {len(records)} 条历史记录，建议使用 --from/--to 缩小范围")

    return records
