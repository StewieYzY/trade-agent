"""Hard Gates — 硬门槛过滤（一票否决）.

S1 规格：~5000 → ~800

硬门槛条件：
- H1: ST/*ST/退市风险
- H2: 上市 < 3 年（用 financials.years 近似）
- H3: 市值 < 50 亿
- H4: 金融/券商
- H5: 周期股（可选，默认关闭）
- H6: 实控人质押 > 70%
- H7: 非标审计意见
- H8: PE 为负（亏损）

容错策略：数据缺失时跳过该条件（宁可漏过不误杀）
"""

from __future__ import annotations


def check_hard_gates(ticker_data: dict, exclude_cyclicals: bool = False) -> dict:
    """检查单只股票是否通过所有硬门槛.

    Args:
        ticker_data: {
            "basic": {"name", "market_cap", "industry", "pe", ...},
            "risk": {"pledge_ratio", "audit_opinion", ...}
        }
        exclude_cyclicals: 是否排除周期股（默认 False）

    Returns:
        {"pass": bool, "failed_gates": [str]}
    """
    basic = ticker_data.get("basic", {})
    risk = ticker_data.get("risk", {})
    financials = ticker_data.get("financials", {})
    failed_gates = []

    # H1: ST/*ST/退市风险
    name = basic.get("name")
    if name is not None:
        if "ST" in name.upper():
            failed_gates.append("H1")

    # H2: 上市 < 3 年（用 financials.years 近似：期数不足即财务历史不够）
    years = financials.get("years", [])
    if len(years) < 3:
        failed_gates.append("H2")

    # H3: 市值 < 50 亿 (50e8 = 50亿)
    market_cap = basic.get("market_cap")
    if market_cap is not None:
        if market_cap < 5e9:
            failed_gates.append("H3")

    # H4: 金融/券商
    industry = basic.get("industry")
    if industry is not None:
        if industry in ["银行", "证券", "保险", "多元金融"]:
            failed_gates.append("H4")

    # H5: 周期股（可选）
    if exclude_cyclicals and industry is not None:
        if industry in ["钢铁", "煤炭", "航运", "化工", "水泥", "养殖"]:
            failed_gates.append("H5")

    # H6: 实控人质押 > 70%
    pledge_ratio = risk.get("pledge_ratio")
    if pledge_ratio is not None:
        if pledge_ratio > 70:
            failed_gates.append("H6")

    # H7: 非标审计意见
    audit_opinion = risk.get("audit_opinion")
    if audit_opinion is not None:
        if audit_opinion in ["保留意见", "无法表示意见", "否定意见"]:
            failed_gates.append("H7")

    # H8: PE 为负（亏损）
    pe = basic.get("pe")
    if pe is not None:
        if pe < 0:
            failed_gates.append("H8")

    return {"pass": len(failed_gates) == 0, "failed_gates": failed_gates}
