## Context

M1 的 MVP 目标是对 5–20 只股票或一个小型多行业样本完成一次可重复筛选，输出质量、估值、反陷阱、热度、数据质量以及进入/排除原因。当前 `value-screener/screener/staged_runtime.py` 已提供 Stage A/B/C 的显式维度边界和 `run_staged_screening()`，但调用方仍需自行构造 fetcher、理解内部阶段结构并拼装用户可读结果。

根目录存在受保护的未跟踪 `value-screener/scripts/build_validation_sample.py`，本 change 不修改、不复制为实现来源，也不将其 provider 行为接入本 child。M1.1 的 selector contract 只提供样本 identity/strata/provenance 约束；本 child 以显式 fixture 输入承载实际五维 L1 数据，避免把 selector 元数据误当成完整行情与财务数据。

## Goals / Non-Goals

**Goals:**

- 提供一个显式输入、无隐式 provider/cache side effect 的小样本运行入口。
- 复用现有 Stage A/B/C、hard gates、factor scores、anti-trap 和 heat filter，不重写筛选规则。
- 为每个输入 ticker 输出 canonical identity、每阶段状态、首个失败原因、最终候选/排除状态、质量状态和可用分数信息。
- 输出稳定排序的 JSON/Markdown，并绑定 `run_id`、`profile_version`、`input_ticker_set_hash`、`as_of` 和 fixture provenance。
- 在输入不足、字段缺失、单票失败时保持 fail-closed 且不阻断其他 ticker。

**Non-Goals:**

- 不调用 AkShare、东财、LongPort/Longbridge、其他 provider、LLM、Scout 或 Council。
- 不读取或写入全局缓存、生产 watchlist、debate、live evidence 或 provider qualification 路径。
- 不运行真实全市场或 300+ 样本，不产生 G1 Capability Gate 证据，不修改 G1 umbrella Gate 状态。
- 不修改 `hard_gates.py`、`factor_scores.py`、`anti_trap.py`、`heat_filter.py` 的规则阈值。
- 不实现 M1.3 用户人工复核、L2 shortlist、Top-20 review、前端或 G3 runtime。

## Decisions

### D1：以显式 fixture fetcher 接入既有 staged runtime

新增小样本 adapter 接收一个 JSON 输入 envelope，包含 canonical ticker 集合、运行 identity、fixture provenance 以及按 ticker/dimension 组织的五维结果。adapter 在内存中提供 `fetch_all(tickers, dimensions, telemetry=...)`，再调用现有 `run_staged_screening()`。

选择注入 fetcher 而不是修改 `BatchFetcher` 或现有脚本，是为了让 M1.2 验证用户可见筛选结果，不引入 provider 连接、缓存写入或新的全局框架。

### D2：输入和输出都显式绑定 identity

输入必须包含非空 `run_id`、`profile_version`、`as_of`、`input_ticker_set_hash` 和 fixture provenance。adapter 重新计算 canonical ticker set hash 并校验一致性；输入来源必须明确为 fixture/reference 或 simulated/development，任何 live/provider/production 标记均拒绝。

输出沿用输入 `run_id`，并保存 profile、as-of、hash 和 provenance，确保同一输入不会因为内部随机 run id 或输入顺序产生不可诊断的结果漂移。

### D3：逐票结果从 staged evidence 派生

不改变 `StagedScreeningResult` 的既有结构。新增汇总层按 canonical ticker 稳定排序，从 Stage A/B/C 的 input/output/failures 和最终 candidates 派生：

- `stage_statuses`：每个阶段为 `passed`、`failed` 或 `not_reached`；
- `exclusion`：首个可定位的阶段、dimension、status 和 reason；
- `quality_status`：`complete`、`degraded`、`failed` 或 `not_evaluable`；
- `scores`：仅在计算成功时保留 factor、anti-trap、heat filter 和 adjusted composite；
- `candidate`：是否进入最终候选列表。

缺失数据不能通过零值、均值或伪造分数进入候选；一票失败只影响该票，其他票继续运行。

### D4：CLI 只负责安全读写和确定性渲染

新增 `small-sample-run --input <fixture.json> --output-dir <dir>`。CLI 读取一个输入文件，在内存执行 adapter，并写入 `<run_id>.json` 与 `<run_id>.md`。输出目录必须由调用方显式传入；实现不得自行选择生产路径，也不得覆盖不同 `run_id` 的既有文件。

Markdown 只呈现用户需要的摘要和逐票表格；JSON 保留完整证据结构。两种渲染均使用稳定 key/order 和 canonical ticker 排序。

### Alternatives considered

- 直接改 `screen_a_shares()`：会重新引入隐式 `BatchFetcher`、生产缓存和全市场语义，不适合离线 M1.2。
- 修改受保护的 `build_validation_sample.py`：会扩大本 child 到 provider reader 和生产脚本，且破坏根目录 WIP 边界。
- 接入 L2 Scout：会把 M1.2 与成本闸门、LLM 调用和 M1.3 用户复核混在一起，违反 MVP 分层。

## Risks / Trade-offs

- **[Risk] fixture 与未来真实 reader 形状漂移** → 固定输入 schema/version、维度白名单和 identity/provenance 校验，真实 reader 留给后续独立 child。
- **[Risk] 用户把 fixture 结果误认为真实 G1 证据** → 输出固定 `artifact_type=fixture/reference`、`mode=simulated/development` 和 `capability_status=not_evidence`。
- **[Risk] staged runtime 内部结果结构变化导致汇总层脆弱** → 只读取公开 result/evidence 字段，并用行为测试锁定逐票输出契约。
- **[Risk] 不同输入顺序造成结果不一致** → adapter 在运行前 canonicalize、去重并稳定排序 ticker，使用显式 run id。

## Migration Plan

1. 在独立 worktree 中先增加输入/输出 contract 的 RED 测试。
2. 实现最小 fixture fetcher、adapter、逐票汇总和 JSON/Markdown renderer。
3. 增加 CLI，并验证输出目录隔离与不同 run id 不覆盖。
4. 运行 focused、相关回归、全量 pytest、compileall、`git diff --check` 和 OpenSpec strict。
5. 完成后保持 `capability_status=not_evidence`；M1.3 由用户人工复核决定是否进入下一步。

## Open Questions

- 真实 provider reader 如何映射到该 fixture fetcher 的输入 contract，留给后续 provider/runtime child。
- 小样本的实际股票集合与用户风格判断，留给 M1.3 人工复核，不在本 child 内自动推断。
