"""催化事件检测 — MVP 阶段基本面催化维度为空，仅检测风险信号."""
from __future__ import annotations

from typing import Any


def detect_catalysts(
    ticker: str,
    current_features: dict[str, Any],
    previous_features: dict[str, Any] | None,
) -> dict[str, Any]:
    """检测催化事件和风险信号.

    MVP 阶段规则：
    - 基本面催化维度为空（数据源全部缺失）
    - 仅检测风险信号：pledge_ratio 周环比上升 >5ppt
    - pe_percentile_5y 边际变化归 diff.py 的 valuation_low 类型，不是催化事件

    Args:
        ticker: 股票代码
        current_features: 当前特征数据（包含 pledge_ratio 等）
        previous_features: 上一周期特征数据（可选）

    Returns:
        催化检测报告 JSON 结构，包含：
        - fundamental_catalysts: list（MVP 阶段为空）
        - risk_signals: list[dict]（风险信号列表）
        - placeholder: str（MVP 阶段提示）
    """
    report = {
        "ticker": ticker,
        "fundamental_catalysts": [],
        "risk_signals": [],
        "placeholder": "⏸️ 基本面催化事件数据源待补齐（event-fetcher TODO）",
    }

    # MVP 阶段：基本面催化维度为空
    # TODO: event-fetcher - 财报超预期（业绩预告/快报）
    # TODO: event-fetcher - 分红提升（分红公告）
    # TODO: event-fetcher + LLM - 行业政策（新闻/公告 + LLM 判断）
    # TODO: event-fetcher + LLM - 管理层变动（高管变动 + LLM 判断）
    # TODO: event-fetcher - 减持（减持公告）
    # TODO: event-fetcher - 业绩预告差（业绩预告）
    # TODO: audit-opinion - 审计意见变更（数据源不可靠，待后续验证）

    # 风险信号检测：pledge_ratio 急升
    if previous_features is not None:
        curr_pledge = current_features.get("pledge_ratio")
        prev_pledge = previous_features.get("pledge_ratio")

        if curr_pledge is not None and prev_pledge is not None:
            delta = curr_pledge - prev_pledge
            if delta > 5.0:
                report["risk_signals"].append({
                    "type": "pledge_ratio_spike",
                    "severity": "high",
                    "message": f"质押率急升 {prev_pledge:.1f}% → {curr_pledge:.1f}%（+{delta:.1f}ppt）",
                    "previous": prev_pledge,
                    "current": curr_pledge,
                    "delta": delta,
                })

    return report


def detect_catalysts_batch(
    candidates: list[dict[str, Any]],
    previous_watchlist: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """批量检测所有 candidate 的催化事件.

    Args:
        candidates: watchlist 中的 candidates 列表
        previous_watchlist: 上一快照 watchlist JSON 结构（可选）

    Returns:
        催化检测报告列表
    """
    # 构建上一快照的 ticker → features 映射
    prev_map = {}
    if previous_watchlist:
        for c in previous_watchlist.get("candidates", []):
            prev_map[c["ticker"]] = c

    reports = []
    for c in candidates:
        ticker = c["ticker"]
        prev_features = prev_map.get(ticker)
        report = detect_catalysts(ticker, c, prev_features)
        reports.append(report)

    return reports


def _llm_catalyst_check(ticker: str, features: dict[str, Any]) -> list[str]:
    """LLM 催化判断预留接口（MVP 阶段未启用）.

    TODO: activate when event-fetcher available

    后续启用时：
    - 调用 council.llm.call_llm(reasoning_level="moderate")
    - 判断催化事件是否影响基本面
    - 返回催化事件列表

    Args:
        ticker: 股票代码
        features: 特征数据

    Returns:
        催化事件列表（MVP 阶段返回空列表）
    """
    # MVP 阶段：不调用 LLM，直接返回空列表
    return []
