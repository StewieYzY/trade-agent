## Why

G2 已冻结成长预期资本化诊断的输入、输出和失败语义，但当前没有实际计算引擎，无法把市值拆解为现有经营能力价值与隐含增长价值，也无法反推价格要求的增长率或持续年限。现在实现一个独立、确定性、无 LLM/API 的 V0 engine，才能在接入 dossier/InvestmentThesis 前验证数值口径、边界和可复现性。

## What Changes

- 新增基于冻结 contract 的纯函数计算引擎，计算 EPV proxy 与成熟期 PE 交叉锚。
- 支持互斥的 fixed-growth-rate 与 fixed-duration reverse 求解，并输出 conservative/base/optimistic 三情景。
- 计算 priced growth value/share、expectation gap、value pulled forward years 和 assumption-bound sensitivity。
- 生成带 input/assumption snapshot、provenance、calculation status、warnings/reasons 与 digest 的不可变 diagnostic artifact。
- 对缺失/非法/不适用/不可解输入 fail closed；不调用 LLM、外部 API，不接入 dossier 或上层 G2 流程。

## Capabilities

### New Capabilities

- `growth-expectation-v0-engine`: 基于已归档 growth-expectation contract 实现确定性 V0 诊断计算和 artifact 生成。

### Modified Capabilities

- 无

## Impact

- 新增 `value-screener/data/lib/growth_expectation_engine.py`。
- 新增 engine focused tests；复用并绑定 `growth_expectation_contract.py`，不修改其冻结语义。
- 新增本 change 的 OpenSpec proposal/design/spec/tasks；不修改根目录既有 WIP、G1、dossier、InvestmentThesis、Council 或 prompt。
