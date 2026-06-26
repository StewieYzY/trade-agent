"""金融模型 · fin_models 模块.

定位（design.md §2.3, tasks 8.4/8.7）：L1/L3 共享纯计算工具库，放 data/lib/，
不继承 BaseFetcher，不触发采集。change 0 只做简化 DCF；完整版 DCF/LBO/Comps 留 L3 change。

输出契约：
  compute_simple_dcf(fcf_series, revenue_series, current_price, assumptions)
      -> {"intrinsic_value": float, "safety_margin_pct": float}

算法：2-Stage FCF + Gordon Terminal（total-design §4.7.1）
  - 从 revenue_series 算增长率 g（CAGR，近两期；不足或非正则 g=0）
  - Stage 1：以最新 FCF 为基，按 g 投影 3 年
  - Terminal：Gordon Growth，TV = FCF_n*(1+terminal_growth)/(discount_rate-terminal_growth)
  - intrinsic_value = Σ FCF_i/(1+r)^i + TV/(1+r)^n
  - safety_margin_pct = (intrinsic_value - current_price)/current_price*100
纯计算，无副作用；跨维度输入由调用方（batch_fetcher / L1）组装。
"""
from __future__ import annotations

import math

_STAGE1_YEARS = 3


def _cagr(series: list[float]) -> float:
    """近两期营收 CAGR。不足两期或非正返回 0."""
    vals = [float(v) for v in series if v is not None and v > 0]
    if len(vals) < 2 or vals[-2] <= 0:
        return 0.0
    n = len(vals) - 1
    return (vals[-1] / vals[-2]) ** (1.0 / n) - 1.0


def compute_simple_dcf(
    fcf_series: list[float],
    revenue_series: list[float],
    current_price: float,
    assumptions: dict,
) -> dict:
    """2-Stage FCF + Gordon Terminal → 内在价值 + 安全边际."""
    r = float(assumptions.get("discount_rate", 0.08))
    g_term = float(assumptions.get("terminal_growth", 0.03))

    # 基期 FCF：最新期，若 <=0 取近系列正值均值，仍无则 0
    fcfs = [float(v) for v in fcf_series if v is not None]
    base_fcf = fcfs[-1] if fcfs and fcfs[-1] > 0 else (
        sum(v for v in fcfs if v > 0) / max(1, sum(1 for v in fcfs if v > 0)) if any(v > 0 for v in fcfs) else 0.0
    )

    g = _cagr(revenue_series)
    # Stage 1 投影
    projected: list[float] = []
    cur = base_fcf
    for i in range(1, _STAGE1_YEARS + 1):
        cur = cur * (1 + g)
        projected.append(cur)

    # Terminal value（Gordon），防止 r<=g_term 退化
    if r > g_term:
        tv = projected[-1] * (1 + g_term) / (r - g_term)
    else:
        tv = projected[-1] if projected else 0.0

    # 折现
    pv_stage = sum(f / ((1 + r) ** i) for i, f in enumerate(projected, start=1))
    pv_tv = tv / ((1 + r) ** _STAGE1_YEARS)
    intrinsic_value = round(pv_stage + pv_tv, 4)

    price = float(current_price) if current_price not in (None, 0) else 0.0
    safety_margin_pct = round(
        (intrinsic_value - price) / price * 100 if price not in (0, None) else 0.0, 4
    )
    return {"intrinsic_value": float(intrinsic_value), "safety_margin_pct": float(safety_margin_pct)}
