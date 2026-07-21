# l1-numeric-correctness Specification

## Purpose

确保 L1 排序中的 DCF、ROE、F-Score、PE、PB 等关键指标使用可验证的单位、分母和量纲；未经可靠每股口径验证的 DCF 不得污染 G1 排序。

## Requirements

### Requirement: DCF 量纲验证
系统 SHALL 在将 DCF 结果纳入排序前验证其量纲一致性。当 DCF 输出的 `intrinsic_value` 与企业价值到每股价值的换算口径未经验证时，该值 MUST NOT 参与排序或 hard gate。

#### Scenario: DCF 企业价值与每股价格量纲不一致
- **WHEN** `compute_simple_dcf()` 返回的 `intrinsic_value` 是公司级企业价值（无总股本换算）
- **THEN** 该值 MUST NOT 进入 `_compute_safety_margin_score()` 的加权计算，并 SHALL 标记 `dcf_note` 为 `"dcf_dimension_mismatch"`

#### Scenario: DCF 每股口径已验证
- **WHEN** 未来 `compute_simple_dcf()` 被修改为输出每股内在价值，且总股本、净债务和报告期已验证
- **THEN** 该值 SHALL 可重新参与安全边际排序，并 MUST 通过独立的每股口径验证测试

### Requirement: 排序指标单位与分母正确性
所有影响 L1 综合分的指标 SHALL 使用明确的单位和分母。系统 MUST 在测试中验证关键指标的数量级合理性。

#### Scenario: ROE 分母不为零
- **WHEN** 计算 ROE 时权益（TOTAL_ASSETS - TOTAL_CURRENT_LIAB - TOTAL_NONCURRENT_LIAB）为零或负
- **THEN** 该期 ROE SHALL 被跳过，MUST NOT 产生无穷大或负值参与均值计算

#### Scenario: PE/PB 为正值
- **WHEN** PE 或 PB 为负值或零
- **THEN** 相关估值子项 SHALL 被跳过或降级处理，MUST NOT 产生误导性的低分或高分

### Requirement: DCF 状态可解释
系统 SHALL 在排序结果中提供 DCF 未参与排序的原因说明，使用户能够理解排序依据。

#### Scenario: DCF 因量纲问题被排除
- **WHEN** DCF 因量纲不一致被移出排序
- **THEN** `compute_factor_scores()` 返回的 `dcf_note` SHALL 包含 `"dcf_dimension_mismatch"` 说明

#### Scenario: DCF 因数据不足被跳过
- **WHEN** FCF 序列不足 2 期或营收序列为空
- **THEN** `dcf_note` SHALL 包含 `"insufficient_data"` 说明

#### Scenario: DCF 计算异常
- **WHEN** DCF 计算过程中抛出 ValueError、ZeroDivisionError 或 TypeError
- **THEN** `dcf_note` SHALL 包含 `"calculation_error"` 说明，并 MUST NOT 静默吞没异常

### Requirement: 异常处理收窄
系统 SHALL 将 DCF 计算的异常处理从宽泛的 `except Exception` 收窄为具体异常类型，使编程错误能够暴露。

#### Scenario: 已知异常类型被捕获
- **WHEN** DCF 计算抛出 ValueError、ZeroDivisionError 或 TypeError
- **THEN** 异常 SHALL 被捕获，`dcf_note` 标记为 `"calculation_error"`，排序继续

#### Scenario: 未知异常类型暴露
- **WHEN** DCF 计算抛出 AttributeError、KeyError 或其他非预期异常
- **THEN** 异常 SHALL 向上传播，MUST NOT 被静默捕获
