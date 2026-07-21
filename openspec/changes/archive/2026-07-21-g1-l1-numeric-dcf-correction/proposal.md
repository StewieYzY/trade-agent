## Why

当前 L1 排序存在数值口径与量纲风险，直接威胁 G1「快」的核心能力——排序正确性。具体问题：

1. **DCF 量纲错误**：`compute_simple_dcf()` 用公司级 FCF 序列折现得到 `intrinsic_value`（企业价值量纲），随后直接与每股 `current_price` 比较计算 `safety_margin_pct`。函数签名中没有总股本、净债务或企业价值到每股价值的转换输入。
2. **安全边际权重放大错误**：DCF 安全边际占安全边际子项 60%，安全边际又占综合分 20%。量纲错误的 DCF 值以 12% 权重直接污染排序。
3. **异常静默吞没**：DCF 计算被 `except Exception` 静默跳过，无法区分「数据不足合理跳过」与「计算异常被掩盖」。
4. **测试覆盖不足**：现有测试只验证资本开支全缺失时跳过 DCF，未验证企业价值/每股价值量纲、净债务、总股本或现实数量级。

这些问题导致 `l1_full.json` 中多只股票 `safety_margin=100`，排序结果不可信。G1 Capability Gate 的「数值正确性」指标无法通过。

## What Changes

- 将不可靠的简化 DCF 从 G1 L1 排序中移除，使其成为 non-decision 展示字段。
- 在 `factor_scores.py` 的 `_compute_safety_margin_score()` 中，当 DCF 不参与排序时，安全边际子项权重重新分配给质押率（100%）。
- 在 `compute_factor_scores()` 返回结构中新增 `dcf_note` 字段，解释 DCF 未参与排序的原因。
- 收窄 `_compute_safety_margin_score()` 中的 `except Exception` 为具体异常类型，并将 DCF 计算失败记录为 degraded 状态。
- 扫描 ROE、F-Score、PE/PB 等排序关键指标的单位与分母，只修复有证据的实际错误。
- 新增正反向行为测试：证明 DCF 量纲错误在旧实现上会产生错误安全边际，在新实现上不影响排序。

## Capabilities

### New Capabilities

- `l1-numeric-correctness`: 确保 L1 排序中所有影响综合分的指标使用正确的单位、分母和量纲。DCF 在每股口径、净债务和总股本未可靠验证前不得参与排序。

### Modified Capabilities

- `quantitative-screener`: 安全边际子项中 DCF 权重从 60% 降为 0%（non-decision），质押率权重从 40% 升为 100%；`compute_factor_scores` 返回结构新增 `dcf_note` 字段；DCF 异常处理从 `except Exception` 收窄为具体异常类型并记录 degraded 状态。

## Impact

**受影响代码**：
- `value-screener/screener/factor_scores.py` — `_compute_safety_margin_score()` 权重调整、异常收窄、`dcf_note` 生成
- `value-screener/tests/test_screener.py` — 新增量纲正确性正反向测试

**不受影响**：
- `value-screener/data/lib/fin_models.py` — `compute_simple_dcf()` 函数本身不修改，保留供未来 G2 深研使用
- 其他 screener 模块（hard_gates、anti_trap、heat_filter）不修改
- 不引入新依赖

**AD 引用**：
- **AD-10**（串行 Gate）：本 change 推进 G1 数值正确性 Gate，是 G1 通过的前置条件
- **G1 umbrella D4**：简化 DCF 在可靠前不得影响 G1 排序

**风险**：
- 移除 DCF 后安全边际维度变窄（只剩质押率），可能降低排序区分度。但错误的量纲比缺失更危险；完整估值保留给 G2。
- 现有 `l1_full.json` 缓存中的排序结果会变化，需要重新运行才能反映修正后的排序。
