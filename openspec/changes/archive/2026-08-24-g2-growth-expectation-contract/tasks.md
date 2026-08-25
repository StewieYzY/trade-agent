## 1. 契约与测试骨架

- [x] 1.1 新增 `value-screener/data/lib/growth_expectation_contract.py`，定义常量、冻结 dataclass 与 `ContractError`
- [x] 1.2 新增 `value-screener/tests/test_g2_growth_expectation_contract.py`，按 RED 先写输入/输出/假设/适用性/失败语义测试

## 2. 输入契约

- [x] 2.1 冻结必需字段、货币与缩放单位、报告期、来源和时间基准
- [x] 2.2 实现缺失、未知单位、非法数值、来源不匹配的 fail-closed 校验

## 3. 输出契约

- [x] 3.1 冻结输出字段与 `clean`/`degraded`/`not_evaluable`/`failed` 状态
- [x] 3.2 实现半成品拒绝规则

## 4. 用户 assumption snapshot

- [x] 4.1 冻结显式假设记录、必需键和版本化方式
- [x] 4.2 实现缺失或冲突假设禁止静默默认值

## 5. 模型适用性与失败语义

- [x] 5.1 冻结模型适用边界与 `data_insufficient`/`model_not_applicable`/`computation_failed`
- [x] 5.2 实现 `evaluate_applicability` 与失败状态映射，不伪装成功

## 6. Golden cases 与验证

- [x] 6.1 建立正反 golden cases，覆盖可计算、不可评估、失败和降级路径
- [x] 6.2 运行 focused tests、全量 tests、compileall、`openspec validate --all --strict` 和 `git diff --check`
