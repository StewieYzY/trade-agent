## Why

M1 需要回答“对少量股票运行 G1 快筛后，用户能否看懂每只股票为何通过或被排除”。现有 `staged_runtime` 已有分阶段筛选逻辑，但缺少一个显式、离线、可重复的小样本输入与用户可读产物边界；因此需要先补齐 M1 MVP 的最小运行封装。

## What Changes

- 新增 `g1-mvp-small-sample-run` 能力，接收显式注入的小样本 fixture 输入并运行现有 G1 staged screening。
- 输出确定性的 JSON 与 Markdown 产物，逐票保留阶段状态、分数、通过/排除原因、质量状态和候选信息。
- 复用 canonical ticker、`run_id`、`profile_version`、`input_ticker_set_hash`、`as_of` 和 fixture provenance，拒绝不一致或 live 证据输入。
- 新增离线 CLI，输出只能写入调用方指定的目录，不写生产 cache、watchlist、debate 或 live evidence。
- 为成功、降级、失败、缺失和不可评估输入定义可观察的结果状态，不用默认值掩盖数据不足。

## Capabilities

### New Capabilities

- `g1-mvp-small-sample-run`: 对 5–20 只股票或小型多行业 fixture 执行可重复 G1 快筛并生成逐票可读结果。

### Modified Capabilities

无。现有 `g1-fast-personal-value-screening`、`staged-fetch-boundary`、`quantitative-screener` 和 `run-identity` 只作为约束引用，不修改其 requirements。

## Impact

- 新增小样本输入适配、结果汇总/渲染和 CLI 接线。
- 新增行为测试，覆盖阶段边界、逐票失败可见性、身份校验、确定性输出和目录隔离。
- 不新增依赖，不调用 provider、LLM 或 Council，不改变现有 L1 规则与 `staged_runtime` 的阶段语义。
