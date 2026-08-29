## Context

Track A 当前进入 `g1-300-sample-validation`。Master `MASTER-2026-08-06` 允许在东财全市场 spot 恢复前，以 contract fixture 推进 G1 抽样和 staged runtime 的离线确定性开发，但明确禁止把 fixture 当作真实 G1 evidence。

根工作区的 `value-screener/scripts/build_validation_sample.py` 是用户未跟踪资产，只能作为行为参考。它目前直接读取 `BasicFetcher._lazy_spot` 和 `build_industry_map()`，因此无法在不调用 provider 的情况下测试抽样边界，也没有稳定暴露 unmapped industry、状态、身份和不足 300 的语义。

本 child 只建立可注入的 sample selector 与输出 contract，不修改用户脚本、不改 L1 规则、不接入 provider、不运行 L1/L2、不进入 provider qualification、canonical promotion 或 G1 evidence bundle。

## Goals / Non-Goals

**Goals:**

- 以标准库数据结构接收 spot 形状记录和行业映射，避免 selector 隐式读取 provider 或全局缓存。
- 以固定 seed 和规范化输入顺序实现可复现、去重的行业与风险分层抽样。
- 显式记录 ST、小市值、负 PE、过热、unmapped industry、缺失值和 invalid value 的选择结果与汇总。
- 使用 canonical ticker、run identity、input ticker set hash、`as_of` 和 provenance 约束构造 fixture/reference 输出。
- 明确 `sample_size >= 300` 才能使用 `full_market` 语义；不足时返回可审计的 `insufficient`/`simulated` 状态，禁止伪造成功。
- 用行为测试覆盖 complete、degraded、source_failed、record_not_found、invalid_value 等输入状态，并证明不发生外部调用。

**Non-Goals:**

- 不调用 AkShare、东财、其他 provider 或 LLM。
- 不修改 `build_validation_sample.py`、`g1-fast-personal-value-screening` umbrella、L1 规则、provider fallback、G2/G3 或治理文件。
- 不执行真实样本运行，不计算关键字段 live 可用率，不生成 provider qualification、canonical promotion 或 G1 evidence bundle。
- 不声明或勾选 G1 umbrella 4.1/4.2，不改变 G1 Capability Gate 状态。
- 不增加依赖，不把 fixture 输出写入生产 cache、watchlist、debate 或 live evidence 路径。

## Decisions

### D1：纯函数 selector，输入与 provider 解耦

新增 `value-screener/data/lib/validation_sample.py` 标准库 selector/contract 模块。公共入口接收已经解析为 Python mapping 的 spot records、industry mapping、显式运行元数据、调用方提供的 input ticker set hash 和 fixture provenance，返回 sample records 与 design summary。selector 不 import AkShare、不访问 `BasicFetcher`、不读取全局缓存。

选择纯函数而不是在现有脚本中继续加 mock 分支，是为了让真实 consumer 未来只需替换 reader/adapter，而不重写下游选择逻辑；同时保护用户未跟踪脚本不被覆盖。

### D2：先规范化身份与字段状态，再执行抽样

输入先经过三步：

1. 规范化并校验 canonical ticker，拒绝非法或无法唯一识别的身份。
2. 将字段值、缺失原因和 provenance 归一到显式状态；缺失或非法数值不会被默认值静默替换。
3. 根据状态决定该记录是否可参与对应行业/风险层，并把排除原因写入 summary，而不是把它伪装为未命中风险层。

`record_not_found` 只表示来源成功但没有该记录；`source_failed` 表示来源失败；`invalid_value` 表示返回值存在但无法通过类型/范围校验；`degraded` 表示仍可用于部分选择但必须带标记。

### D3：分层规则保持确定性且不降低样本门槛

默认配置沿用用户资产脚本已表达的意图：固定 seed、行业层配额与上限，以及 ST、小市值、负 PE、过热风险层。具体配置作为显式 immutable mapping 传入，行业和风险标签按稳定顺序写入。

抽样前按 canonical ticker 排序；每个 pool 只使用固定 `random.Random(seed)`；跨 strata 用 ticker 去重并合并标签。unmapped industry 使用显式 `_unmapped` 分组，并在 summary 中标记行业映射不足；它不能被计作真实行业覆盖。

当可用输入不足以满足某个 strata 时，selector 保留实际可选数量和缺口，不通过放宽阈值或重复 ticker 凑数。

### D4：输出是 fixture/reference contract，不是 live evidence

输出 envelope 包含：

- `mode`/`artifact_type`，明确 `fixture/reference` 或 `simulated/development`；
- `schema_version`、`run_id`、`profile_version`、`input_ticker_set_hash`、`as_of`；
- fixture provenance，包括来源声明、输入 hash 和非 live 运行说明；
- `sample`、逐票 `strata`/状态元数据和 `design` summary；
- `sample_size_semantics`，区分 `full_market` 与 `insufficient`/`subset`。

`full_market_qualified_size` 只统计 canonical 去重、行业映射可用且记录状态可用于正式样本的 ticker；`_unmapped`、source failure、record absence、invalid record 不得解锁门槛。`sample_size < 300` 或 qualified size < 300 时 summary 的 `full_market_eligible` 必须为 false。该输出不得被命名或写入 live evidence bundle。

### D5：不改现有 provider/status canonical 实现

本 child 复用 canonical `data-minimum-contract` 与 `run-identity` 的字段语义，但不修改它们的 canonical spec，也不复制 provider batch adapter 的实现。fixture adapter 只负责把离线记录映射到相同的 status/provenance 形状；未来真实 reader 替换 fixture reader 时，selector API 保持不变。

## Risks / Trade-offs

- **[Risk] fixture schema 与真实 consumer 漂移** → 输出固定 schema/version，并在测试中校验 identity/provenance/status 必填字段；真实 consumer 接入时只允许替换 reader/adapter。
- **[Risk] 行业映射缺失导致样本数量或覆盖虚高** → `_unmapped` 不计真实行业覆盖，summary 保留 unmapped 数量与状态；不足时显式失败。
- **[Risk] 风险层字段缺失造成风险覆盖假象** → 每个风险 strata 记录 eligible/selected/unavailable 数量和原因，不用默认值或重复 ticker 补齐。
- **[Risk] 复用现有脚本时误写生产产物** → 本 child 不修改脚本、不执行其 `main()`，测试只消费内存 fixture，禁止写 `data/validation_sample.*`。
- **[Risk] fixture 被误当作 G1 Gate evidence** → envelope 固定 `fixture/reference`/`simulated/development` 标识，设计、测试和 tasks 均明确不勾选 4.1/4.2。

## Migration Plan

1. 在独立 worktree 中先添加 selector contract 的失败测试。
2. 添加最小标准库实现与内存 fixture builders，逐项使测试转绿。
3. 保持用户抽样脚本不变；未来真实 provider 恢复后，由单独的 reader/integration child 将真实 spot 转成相同输入 contract。
4. 运行 focused pytest、相关回归测试、`git diff --check` 和适用的 OpenSpec strict validation。
5. 本 child 完成不会触发真实样本运行、provider qualification、canonical promotion 或 G1 Gate 放行。

## Open Questions

- 真实 spot reader 接入时的 adapter 归属和 CLI 接入方式留给后续 child，不在本 child 冻结。
- 行业配额是否需要在真实全市场分布上重新校准，留到真实 300+ 预检证据之后决定。
