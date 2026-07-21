## Context

G1「快」的核心能力是排序正确性。当前 L1 三因子打分中，安全边际子项（占综合分 20%）的 DCF 部分（占安全边际 60%，即综合分 12%）存在量纲错误：`compute_simple_dcf()` 输出的是公司级企业价值（亿元量级），直接与每股价格（元量级）比较，产生的 `safety_margin_pct` 数值无意义。

代码事实（`value-screener/data/lib/fin_models.py`）：
- `compute_simple_dcf(fcf_series, revenue_series, current_price, assumptions)` 用公司级 FCF 投影并折现，得到 `intrinsic_value`（企业价值）。
- `safety_margin_pct = (intrinsic_value - current_price) / current_price * 100`——企业价值与每股价格直接相减，量纲不一致。
- 函数没有 `shares_outstanding`、`net_debt` 或任何企业价值到每股价值的转换输入。

调用方事实（`value-screener/screener/factor_scores.py`）：
- `_compute_safety_margin_score()` 调用 `compute_simple_dcf()`，将 `safety_margin_pct` 作为安全边际子项的 60% 权重。
- DCF 计算被 `except Exception` 静默跳过。
- `compute_factor_scores()` 返回 `{"quality", "value", "safety_margin", "composite", "f_score"}`，无 DCF 状态说明。

测试事实（`value-screener/tests/test_screener.py`）：
- `test_fcf_validity_check` 只验证资本开支全 None 时跳过 DCF，安全边际退化为纯质押率。
- 无测试验证 DCF 输出的量纲、每股换算或现实数量级。

利益相关方：使用 L1 排序结果的用户、消费 G1 shortlist 的 G2 深研流程。

## Goals / Non-Goals

**Goals:**

- 消除 DCF 量纲错误对 L1 排序的污染。
- 确保排序关键指标（ROE、F-Score、PE/PB）无单位或分母错误。
- 提供可解释的 DCF 状态说明，让用户理解 DCF 为何未参与排序。
- 建立正反向行为测试，证明修复前后排序差异可归因。

**Non-Goals:**

- 不修复 `compute_simple_dcf()` 本身的量纲问题（保留供 G2 深研）。
- 不新增总股本、净债务或企业价值到每股价值的换算逻辑。
- 不重构其他 screener 模块（hard_gates、anti_trap、heat_filter）。
- 不引入新依赖。
- 不处理分层采集、L2 全量输出、ticker identity 或全市场实跑。

## Decisions

### D1. 将不可靠 DCF 移出排序，而非临时拼接每股换算

**选择**：将 DCF 从安全边际排序中移除，标记为 non-decision。

**理由**：
- 临时拼接总股本和净债务需要验证数据源的可靠性、报告期对齐和单位一致性，这本身是一个独立的工程里程碑。
- 未经验证的拼接可能引入新的量纲错误，比移除更危险。
- G1 umbrella D4 明确规定：简化 DCF 在可靠前不得影响排序。

**备选方案**：修复 `compute_simple_dcf()` 为每股口径。需要新增 `shares_outstanding` 和 `net_debt` 输入，验证 akshare 数据源的总股本和净债务字段可靠性。这属于独立 child change，不在本 change scope 内。

### D2. 安全边际子项权重重新分配

**选择**：DCF 权重从 60% 降为 0%，质押率权重从 40% 升为 100%。

**理由**：
- 质押率是安全边际中唯一可靠的子项，数据源明确（`risk.pledge_ratio`），单位一致（百分比）。
- 保持安全边际子项存在，但只由可靠信号构成，避免综合分公式大改。

**备选方案**：将安全边际整体权重降为 0%。这会改变综合分公式（quality 50% + value 30% + safety_margin 20% → quality 50% + value 30%），影响面更大，且质押率本身是可靠信号。

### D3. 新增 `dcf_note` 字段解释 DCF 状态

**选择**：在 `compute_factor_scores()` 返回结构中新增 `dcf_note: str | None`。

**理由**：
- 用户需要理解 DCF 为何未参与排序，否则会产生「系统漏算了估值信号」的困惑。
- `dcf_note` 携带具体原因（如 "dcf_dimension_mismatch"、"insufficient_data"、"calculation_error"），支持后续诊断。

**备选方案**：在日志中记录 DCF 状态。日志不持久化，用户无法在排序结果中看到解释。

### D4. 收窄异常处理并记录 degraded 状态

**选择**：将 `except Exception` 收窄为 `except (ValueError, ZeroDivisionError, TypeError)`，并将 DCF 计算失败标记为 degraded。

**理由**：
- 宽泛的 `except Exception` 会掩盖编程错误（如 AttributeError、KeyError）。
- 收窄后，真正的编程错误会暴露为测试失败或运行时异常，而非静默跳过。
- degraded 状态进入 `dcf_note`，用户可区分「数据不足合理跳过」与「计算异常」。

### D5. 扫描其他排序指标但不预防性修复

**选择**：扫描 ROE、F-Score、PE/PB 的单位和分母，只修复有证据的实际错误。

**理由**：
- 预防性修复容易引入回归，且没有证据表明这些指标存在问题。
- 扫描结果记录在 design 中，作为审计证据。

## Risks / Trade-offs

- [Risk] 安全边际维度变窄（只剩质押率），降低排序区分度 → 换取数值可靠性；完整估值保留给 G2。
- [Risk] 现有 `l1_full.json` 缓存中的排序结果会变化 → 需要重新运行才能反映修正后的排序，这是预期行为。
- [Risk] 收窄异常处理后，未预料的异常类型会导致运行时崩溃 → 通过测试覆盖已知的失败路径，未预料异常应暴露而非静默。

## Migration Plan

1. 修改 `_compute_safety_margin_score()` 权重分配。
2. 收窄异常处理。
3. 在 `compute_factor_scores()` 中生成 `dcf_note`。
4. 新增正反向行为测试。
5. 运行全量测试确认无回归。

回退策略：若修复后排序质量明显退化（如 Top 20 中用户复核通过率下降），回退到上一个版本，并通过新的 child change 重新设计安全边际子项。

## Open Questions

- 无。本 change scope 明确，决策已在 G1 umbrella 中确认。

## 排序关键指标审计结论（2026-07-21）

### ROE 计算
- **状态**: ✓ 正确
- **证据**: `factor_scores.py:102` — `if equity <= 0: continue` 正确跳过零/负权益
- **风险**: 无

### F-Score
- **状态**: ✓ 正确
- **证据**: `stock_features.py:40` 返回 0-9 整数；`factor_scores.py:80` 归一化 `f_score / 9.0 * 100.0`
- **风险**: 无

### PE/PB
- **状态**: ✓ 正确
- **证据**:
  - `factor_scores.py:164` — `pe_ttm > 0` 仅使用正 PE
  - `factor_scores.py:166` — `industry_median_pe > 0` 防止零分母
  - `factor_scores.py:175/181/187` — 正确处理 None 值
- **风险**: 负 PB 理论上可能（资不抵债），但极罕见，会被硬门槛或质量检查捕获
