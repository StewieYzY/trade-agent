## Why

G2 1.1 已使 ticker/run 审计链可验证，但当前 Council、fallback、缓存与 watchlist
仍可能各自保存局部状态；R2、DA、Synthesizer 或最终验证中断后，产物可能被旧的
ticker/date 缓存路径当作可复用成功结果。G2 umbrella 1.2 必须将完整性和质量状态
提升为独立、可读取的运行契约，阻止不完整或降级结果伪装为 clean success。

## What Changes

- 新增 run-scoped G2 quality status record，固定支持
  `complete`、`warning`、`failed`、`incomplete`、`runtime_degraded` 与
  `da_skipped` 六种状态。
- 定义只有 `complete` 且质量门通过的结果可以进入并命中成功缓存的判定。
- 将 R2、DA、Synthesizer 与 final validation 的中断记录为可读取的
  `incomplete` 状态，而不是半成品缓存。
- 将 soft warning、DA skipped 与 runtime degraded 独立持久化，并让 Council、
  fallback、缓存和 watchlist 消费者显式看到状态与原因。
- 以 canonical ticker + `run_id` 隔离所有状态记录与诊断产物，禁止同 ticker 的不同
  run 覆盖彼此。

## Capabilities

### New Capabilities

- `g2-run-quality-status`: G2 深研运行的完整性、质量状态、成功缓存资格与
  run-scoped 读取隔离契约。

### Modified Capabilities

- `council-debate`: Council 缓存和发布结果必须遵守 G2 运行质量状态，不能把
  incomplete、warning、DA skipped 或 runtime degraded 结果作为 clean cache hit。
- `council-output-interface`: watchlist 输出必须携带可读取的 G2 运行质量状态和原因，
  不能把降级或中断运行表示为无标记成功。

## Impact

- 影响 `value-screener/council/debate.py`、`value-screener/council/fallback.py`、
  相关 Council/watchlist/cache tests，以及新增的最小 quality-status persistence
  模块。
- 复用既有 `data.lib.identity` 与 `data.lib.audit_chain` 的 canonical ticker/run
  identity，不改变其 hash chain contract。
- 不新增依赖、不调用真实 provider/LLM、不修改根目录用户 WIP。
