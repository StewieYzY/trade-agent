## Why

G1 umbrella 的 M3 工程 Gate（§5）要求一次对完整可交易 A 股集合执行的真实 L1+L2 运行证据：关键字段可用率至少 95%、未处理异常为 0，并真实记录总耗时与 L2 成本作为观测指标。耗时 15 分钟与 L2 成本 ¥2 是参考阈值，不作为本 child 的硬性 Gate 否决条件。`g1-300-sample-validation` 只建立了离线 fixture/contract foundation，不构成全市场 Gate 证据。本 child 负责建立证据采集能力，先用真实已缓存子集验证 pipeline 与证据口径，再保留完整可交易集合运行作为最终 Gate 证据任务。

## What Changes

- 新增 `g1-full-market-performance-cost` 能力，编排真实 L1+L2 运行，采集耗时、可用率、成本、漏斗分布和异常证据，并明确 `partial_market` 与 `full_market` coverage。
- 新增 performance/cost evidence module：包裹现有 `screen_a_shares` + `scout_batch`，记录分阶段耗时、关键字段可用率、L2 实测/等效推算成本、未处理异常计数和运行配置。
- 新增缓存可用性与新鲜度分离的预检：`cache_warm` 只检查文件存在、JSON 可读和维度最低结构合同；`data_freshness` 单独记录 fresh/stale/missing/invalid 与年龄分布。
- 支持受控 `allow_stale` 本地验证：只读已落盘且结构有效的数据，不触发 provider；生产默认 `require_fresh` 仍按 freshness policy 刷新 stale 数据。
- Evidence bundle 明确区分 `hard_gate_passed`、`observed_metrics`、兼容字段 `metrics_gate_passed` 和 `gate_passed`。
- 保持 canonical `pledge_ratio` 输出语义：`record_not_found` 仍输出 `None + pledge_status`（known-zero 的可用性由 evidence 层按 status 判定），`source_failed` 仍输出 `None + pledge_status`，不在 candidate 投影中用 0.0 改写或丢失 provenance。
- 新增 evidence bundle 输出：总耗时、分阶段耗时、候选数量变化、可用率、降级分布、失败分布、成本、缓存状态和运行配置写入可复核的 JSON evidence artifact。
- 不修改 L1 筛选规则（hard_gates/factor_scores/anti_trap/heat_filter 判定逻辑）、L2 scout 逻辑、provider adapter、ScreeningProfile 或已有 canonical spec 合同；candidate 投影只补充 `pledge_status` provenance。
- 不把 `g1-300-sample-validation` 的 fixture 结果当作本 child 的完成证据。
- 不勾选 umbrella tasks 5.1/5.2/5.3 以外的 Gate，不宣称 G1 capability passed。

## Capabilities

### New Capabilities

- `g1-full-market-performance-cost`: 为 G1 工程 Gate 提供真实 L1+L2 运行的 performance/cost/failure 证据采集与可复核 evidence bundle 输出能力。

### Modified Capabilities

无。现有 `g1-fast-personal-value-screening` umbrella、`quantitative-screener`、`scout-agent`、`run-identity`、`data-minimum-contract` 和 `g1-300-sample-validation` 的 spec 只作为约束与引用，不修改其 requirement。

## Impact

- 新增 performance/cost evidence module 及其行为测试，位于 `value-screener/performance/run_evidence.py`。
- 修改 `value-screener/screener/main.py` 的 candidate 输出：保持 `pledge_ratio` 的 `None + pledge_status` canonical 语义，并补充 `pledge_status` provenance 字段。
- 新增 OpenSpec capability spec、design 与 tasks。
- 不新增依赖，不改 L1 筛选规则/L2 scout 逻辑/provider/G2/G3 或 Capability Gate 状态。
- 已缓存子集运行只能作为 pipeline/证据口径验证；只有完整可交易集合运行才能作为 G1 全市场 Gate 证据。运行失败时保留失败证据，不以默认值伪造成功。
