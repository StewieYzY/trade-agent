## Why

“找到好股票”和“找到后拿得住”是两个不同问题。当前系统只能生成候选、标的研判与人工提醒，尚未维护真实持仓、持有 Thesis、仓位纪律或交易前复核；本 change 需要把“拿得住”正式确认为独立产品能力，并定义其在不自动交易前提下的验收边界。

## What Changes

- 将“拿得住”定义为持仓纪律副驾驶：把可信 Investment Thesis 转译为用户确认的 HoldingContract。
- 明确候选池与真实持仓池分离，持仓不会因退出本期 L1 候选而停止监控。
- 定义认知锚、仓位锚、反证锚、节奏锚，以及 Green/Yellow/Red/Blue/Rebalance Review 状态机。
- 定义 `pre_trade_check`、状态变化证据链、合同版本、人工确认和 shadow mode 验收标准。
- 明确不接券商、不自动下单、不做精确 Kelly 或完整组合优化。
- 规定本 umbrella change 在 G2 通过前只允许继续设计，不允许实现运行时代码；后续按“领域模型 → 合同生命周期 → 监控信号 → 状态机 → 交易前检查 → shadow mode”拆成 child changes。

## Capabilities

### New Capabilities

- `holding-discipline`: 定义从 Investment Thesis 到 HoldingContract、持仓状态和交易前纪律审查的能力边界、验收门与里程碑拆分规则。

### Modified Capabilities

无。本 umbrella change 不直接修改现有 monitoring specs；具体 L4 接口和行为变化由后续 child changes 提交 delta specs。

## Impact

- 未来新增领域：`value-screener/holding/`、持仓真值源、合同和状态历史。
- 未来受影响模块：L3 输出接口、`value-screener/monitor/`、CLI，以及后续前端持仓状态展示。
- 未来受影响现有 specs：`council-output-interface`、`monitoring-alerts`、`watchlist-aggregation`、`watchlist-diff`。
- 不接触券商或真实交易执行。
- 依赖关系：只有 G2 的 Investment Thesis Gate 通过后，才进入本 Goal 的代码实现。
