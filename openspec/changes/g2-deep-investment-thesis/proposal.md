## Why

当前 L3 已形成 research dossier、角色分发、辩论协议、DA 与 Synthesizer 等工程骨架，但尚未证明多 Agent 相比强单 Agent 能稳定产生更多正确、可溯源、可用于投资决策的信息增量。本 change 需要把“深”从结构化辩论机制重新锚定为可验证的 Investment Thesis 生成能力。

## What Changes

- 将“深”正式定义为生成可溯源、可证伪、可持续跟踪的 Investment Thesis，而不是完成多轮角色扮演。
- 建立“强单 Agent baseline vs Multi-Agent Council”的同输入盲评 Gate。
- 定义事实接地、来源追溯、审计链、串台、R2 修订、DA 增量、用户盲评和负增量比例等验收标准。
- 明确 Council 未通过信息增量 Gate 时，产品应降级为“强单 Agent + 独立 DA/事实检查器”，不强留全天团。
- 定义结构化 `InvestmentThesis` 作为未来 L3→L3.5/L4 的稳定接口。
- 规定本 umbrella change 不直接实现 prompt、数据源或编排修复；后续按“审计链 → dossier 数据质量 → prompt 蒸馏 → 主流程质量门 → A/B 验证”拆成 child changes。

## Capabilities

### New Capabilities

- `investment-thesis`: 定义对指定股票生成可信 Investment Thesis 的能力边界、质量 Gate、输出契约与里程碑拆分规则。

### Modified Capabilities

无。本 umbrella change 不直接修改现有 `research-dossier`、`council-debate`、`debate-quality-gate` 或 `council-output-interface` requirement；具体行为变更由后续 child changes 提交 delta specs。

## Impact

- 未来受影响模块：`value-screener/council/`、L3 research dossier fetchers、debate/watchlist 持久化与质量验证工具。
- 未来受影响现有 specs：`research-dossier`、`council-debate`、`debate-orchestration`、`debate-quality-gate`、`council-output-interface`、`da-and-synthesizer`。
- 与当前 `f3c-r1-crosstalk-root-cause` 的关系：f3c 是 G2 下的前置诊断 child change，不被本 change 替代。
- 依赖关系：G1 通过后正式验收；G2 通过后才允许实现 G3 HoldingContract。
