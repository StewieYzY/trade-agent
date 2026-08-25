## Why

独立 review 证明已归档的 V0 engine 存在数值正确性和失败语义缺陷：reverse 求解没有满足估值方程，敏感性不是单变量传播，部分合法输入直接抛异常，且输出没有完整完成自身 binding。该 repair 必须在后续 dossier integration 前闭合这些风险。

## What Changes

- 分离 reverse solver 的 earnings basis、终值利润和 current-business anchor，并增加 bracket/residual 校验。
- 移除 fixed-duration 的隐式 5.0 增长率上限，改为有界自适应搜索。
- 将 sensitivity 改为逐一改变 assumption 的真实 scenario，并覆盖 contract 要求的 reverse/gap/overdraft/pulled-forward 输出。
- 对负净利润和其他可识别计算失败返回 contract-compatible failure artifact。
- 失败 artifact 保留 exact input snapshot；facade 内完成 diagnostic binding validation。
- 修复 `above_base_case` 分类并补齐 review regression tests。

## Capabilities

### New Capabilities

- `growth-expectation-v0-engine-correctness`: 修复 G2 V0 deterministic engine 的数值、失败和 provenance 正确性。

### Modified Capabilities

- 无

## Impact

- 修改 `value-screener/data/lib/growth_expectation_engine.py`。
- 扩展 engine focused tests。
- 新增本 repair 的 OpenSpec artifacts；不接入 dossier、InvestmentThesis、Council、G1/G3，不修改根目录 WIP。
