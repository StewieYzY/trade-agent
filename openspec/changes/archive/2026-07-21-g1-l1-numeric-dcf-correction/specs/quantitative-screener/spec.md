# quantitative-screener Specification

## Purpose

定义 L1 量化筛选的安全边际评分与结果契约，确保未经验证的 DCF 不参与排序，并向调用方返回可解释的 DCF 状态。

## Requirements

### Requirement: 安全边际因子权重分配
安全边际子项（占综合分 20%）的内部权重 SHALL 调整为：DCF 安全边际 0%（non-decision），质押率反向 100%。当 DCF 量纲未通过验证时，安全边际子项 MUST 仅由质押率构成。

#### Scenario: DCF 不参与排序时安全边际仅由质押率构成
- **WHEN** DCF 因量纲不一致或数据不足被移出排序
- **THEN** 安全边际子项 SHALL 100% 由质押率反向构成，MUST NOT 将 DCF 分数以任何权重混入

#### Scenario: 质押率缺失时安全边际为零
- **WHEN** `risk.pledge_ratio` 为 None 且 DCF 不参与排序
- **THEN** 安全边际子项 SHALL 返回 0.0，MUST NOT 用 DCF 填充

### Requirement: 综合分返回结构扩展
`compute_factor_scores()` 返回结构 SHALL 新增 `dcf_note: str | None` 字段，说明 DCF 未参与排序的原因。

#### Scenario: DCF 被移出排序
- **WHEN** DCF 因量纲问题、数据不足或计算异常未参与排序
- **THEN** 返回结构 SHALL 包含 `dcf_note` 字段，值为具体原因字符串（如 `"dcf_dimension_mismatch"`、`"insufficient_data"`、`"calculation_error"`）

#### Scenario: DCF 正常参与排序（未来）
- **WHEN** DCF 通过每股口径验证并重新参与排序
- **THEN** `dcf_note` SHALL 为 None

### Requirement: DCF 异常处理收窄
`_compute_safety_margin_score()` 中的 DCF 计算异常处理 SHALL 从 `except Exception` 收窄为 `except (ValueError, ZeroDivisionError, TypeError)`。

#### Scenario: 具体异常类型被捕获
- **WHEN** DCF 计算抛出 ValueError、ZeroDivisionError 或 TypeError
- **THEN** 异常 SHALL 被捕获，`dcf_note` 标记为 `"calculation_error"`，排序继续

#### Scenario: 非预期异常向上传播
- **WHEN** DCF 计算抛出 AttributeError、KeyError 或其他非预期异常
- **THEN** 异常 SHALL 向上传播，MUST NOT 被静默捕获
