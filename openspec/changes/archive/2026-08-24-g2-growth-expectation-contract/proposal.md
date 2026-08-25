## Why

G2 umbrella 3.1 要求先冻结成长预期资本化诊断的契约，再实现 V0 engine 和 dossier/InvestmentThesis 集成。当前没有任何模块定义该 artifact 的输入、输出、用户假设快照、模型适用性、失败语义和 golden cases，直接进入引擎会带来口径不一致、无法审计和 A/B 输入不公平。

## What Changes

- 新增版本化契约模块 `value-screener/data/lib/growth_expectation_contract.py`，冻结 `growth_expectation_diagnostic` 的 schema 和校验规则。
- 冻结输入契约：必需字段、货币与缩放单位、报告期、来源和时间基准，以及缺失/未知单位/非法数值/来源不匹配的 fail-closed 语义。
- 冻结输出契约：`clean`、`degraded`、`not_evaluable`、`failed` 四种 `calculation_status`，并禁止返回半成品。
- 冻结用户 assumption snapshot 的显式假设记录、必需键、版本化和缺失/冲突时禁止静默默认值。
- 冻结模型适用边界与失败语义，区分 `data_insufficient`、`model_not_applicable`、`computation_failed`。
- 新增正反 golden cases 测试，覆盖可计算、不可评估、失败和降级路径。

明确不包含：EPV proxy / reverse 求解等计算引擎，dossier 与 `InvestmentThesis` 集成，G2 capability passed 宣告，G3 runtime。

## Capabilities

### New Capabilities
- `growth-expectation-diagnostic`: 成长预期资本化诊断 artifact 的输入、输出、假设快照、模型适用性、失败语义与 golden cases 契约。

### Modified Capabilities

（无）

## Impact

- `value-screener/data/lib/growth_expectation_contract.py`：新增契约模块。
- `value-screener/tests/test_g2_growth_expectation_contract.py`：新增契约测试与 golden cases。
- `openspec/specs/growth-expectation-diagnostic/spec.md`：新增能力 spec。
- 不新增依赖，不修改 L0-L4 runtime，不修改 dossier/Thesis 集成。
