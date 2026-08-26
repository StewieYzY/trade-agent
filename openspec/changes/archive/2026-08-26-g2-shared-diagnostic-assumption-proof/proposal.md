## Why

G2 M4.5 已经产出不可变的 growth-expectation diagnostic，但在进入强单 Agent/Council 对照前，尚缺确定性证据证明两条路径消费的是同一个 artifact 和同一个用户 assumption snapshot。若没有这层 proof，共享计算结果可能被错误统计为 Council 独有信息增量，或在 ticker/run/dossier/diagnostic identity 不一致时继续运行。

## What Changes

- 新增只读、确定性的 shared diagnostic/assumption proof harness，验证强单 Agent 与 Council 的输入身份、内容 digest 和审计链。
- 新增 fail-closed 校验：artifact 被替换、digest 被篡改、ticker/run/dossier/diagnostic identity 不一致时拒绝形成 proof。
- 新增 Council 增量分类：共享 deterministic diagnostic 数值不计增量，只有新增反证、风险、关键变量或有效假设质疑才计入。
- 新增确定性测试和审计证据格式，覆盖双路径输入一致、artifact identity/digest、assumption snapshot、增量分类和替换失败。
- 不修改 growth expectation engine 计算逻辑，不启动真实 LLM，不改变 G2 4.1 主流程质量门。

## Capabilities

### New Capabilities

- `g2-shared-diagnostic-assumption-proof`: 为强单 Agent 与 Council 的共享 diagnostic artifact、assumption snapshot、审计 identity 和 Council 增量分类提供确定性 proof。

### Modified Capabilities

- 无。现有 growth-expectation contract 与 InvestmentThesis integration 的 requirements 不变。

## Impact

- 影响 `value-screener/` 内新增的 proof/harness 模块及其 focused tests。
- 复用现有 `growth_expectation_contract` 的 canonical serialization/digest 和已集成的 dossier diagnostic artifact；不引入新依赖。
- 产出 run-scoped、可审计的 proof mapping；不写入真实 Council/watchlist 成功路径，不进入 G1 ranking/hard gate。
