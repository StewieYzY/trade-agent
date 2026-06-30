"""提醒系统 — 估值提醒（MVP 暂停）+ 风险扫描 + key_variable 提醒."""
from __future__ import annotations

from typing import Any


def generate_valuation_alerts(
    candidates: list[dict[str, Any]],
    catalyst_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成估值提醒（AD-02 双条件）.

    MVP 阶段规则：
    - 基本面催化数据源缺失，暂停输出
    - 输出 placeholder 提示
    - 完整态：pe_percentile_5y < 20% AND 催化事件 → 触发提醒

    Args:
        candidates: watchlist candidates 列表
        catalyst_reports: 催化检测报告列表

    Returns:
        估值提醒报告 JSON 结构
    """
    # MVP 阶段：暂停输出
    return {
        "type": "valuation_alerts",
        "status": "paused",
        "placeholder": "⏸️ 估值提醒暂不可用——基本面催化事件数据源待补齐（event-fetcher TODO）",
        "alerts": [],
    }

    # TODO: 完整态实现（待 event-fetcher 补齐后启用）
    # alerts = []
    # for c in candidates:
    #     pe = c.get("pe_percentile_5y")
    #     if pe is None or pe >= 20.0:
    #         continue
    #
    #     # 查找对应催化报告
    #     catalyst_report = next(
    #         (r for r in catalyst_reports if r["ticker"] == c["ticker"]),
    #         None
    #     )
    #     if not catalyst_report or not catalyst_report.get("fundamental_catalysts"):
    #         continue
    #
    #     # AD-02 双条件满足
    #     alerts.append({
    #         "ticker": c["ticker"],
    #         "name": c.get("name", ""),
    #         "pe_percentile_5y": pe,
    #         "catalysts": catalyst_report["fundamental_catalysts"],
    #         "message": f"🟢 {c['ticker']} {c.get('name', '')} 估值低位 + 催化出现！建议关注",
    #     })
    #
    # return {
    #     "type": "valuation_alerts",
    #     "status": "active",
    #     "alerts": alerts,
    # }


def generate_risk_alerts(
    catalyst_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成风险扫描提醒.

    规则：
    - 从催化检测报告中提取风险信号
    - 质押率急升 >5ppt → 触发提醒

    Args:
        catalyst_reports: 催化检测报告列表

    Returns:
        风险扫描报告 JSON 结构
    """
    alerts = []

    for report in catalyst_reports:
        for signal in report.get("risk_signals", []):
            alerts.append({
                "ticker": report["ticker"],
                "type": signal["type"],
                "severity": signal["severity"],
                "message": f"🔴 {report['ticker']} {signal['message']}，建议重新审视",
            })

    # TODO: event-fetcher - 减持风险（减持公告）
    # TODO: event-fetcher - 业绩预告差风险（业绩预告）
    # TODO: audit-opinion - 审计意见变更风险（数据源不可靠，待后续验证）

    return {
        "type": "risk_alerts",
        "alerts": alerts,
    }


def generate_key_variable_alerts(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成 key_variable 提醒（MVP 人工核对）.

    规则：
    - 对 stage=l3 的 candidate，列出 key_variables 供人工核对
    - 不做自动检测（MVP 阶段）

    Args:
        candidates: watchlist candidates 列表

    Returns:
        key_variable 提醒报告 JSON 结构
    """
    alerts = []

    for c in candidates:
        if c.get("stage") != "l3":
            continue

        key_vars = c.get("key_variables")
        if not key_vars or not isinstance(key_vars, list) or len(key_vars) == 0:
            continue

        alerts.append({
            "ticker": c["ticker"],
            "name": c.get("name", ""),
            "key_variables": key_vars,
            "message": f"⚠️ {c['ticker']} {c.get('name', '')} 关键变量：{', '.join(key_vars)}",
            "hint": "💡 结合近期动态核对是否发生变化",
        })

    # TODO: key_variable auto-detection - LLM 判断或规则映射

    return {
        "type": "key_variable_alerts",
        "alerts": alerts,
    }


def generate_alerts(
    candidates: list[dict[str, Any]],
    diff_report: dict[str, Any],
    catalyst_reports: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成所有类型的提醒.

    Args:
        candidates: watchlist candidates 列表
        diff_report: diff 报告
        catalyst_reports: 催化检测报告列表

    Returns:
        完整提醒报告 JSON 结构，包含：
        - valuation_alerts: 估值提醒（MVP 暂停）
        - risk_alerts: 风险扫描
        - key_variable_alerts: key_variable 提醒
    """
    return {
        "valuation_alerts": generate_valuation_alerts(candidates, catalyst_reports),
        "risk_alerts": generate_risk_alerts(catalyst_reports),
        "key_variable_alerts": generate_key_variable_alerts(candidates),
    }
