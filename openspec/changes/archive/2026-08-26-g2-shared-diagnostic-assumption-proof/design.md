## Context

G2 umbrella 的 3.1–3.3 已冻结并接入 `growth_expectation_diagnostic`：contract 负责 canonical serialization、`input_digest`/`diagnostic_digest` 与 `assumption_snapshot`，engine 负责一次确定性计算，dossier integration 负责不重算地暴露 artifact。下一步 3.4 需要在正式 A/B 之前证明输入公平性和 Council 增量口径。

当前 strong-single-agent fallback 与 Council 编排分别持有自己的运行上下文，已有 ticker/run/dossier 审计字段，但没有一个跨路径、只读的 proof boundary 来验证 diagnostic artifact 和 assumption snapshot 的内容级一致。若在 proof 中再次调用 engine，或允许路径传入后改写 artifact，就会把“共享计算”与“路径洞察”混在一起。

## Goals / Non-Goals

**Goals:**

- 新增一个确定性、无副作用的 proof/harness，消费已验证的 diagnostic artifact 和两条路径的 audit envelope。
- 以 canonical digest 验证两条路径使用同一 diagnostic artifact、同一 assumption snapshot，并校验 ticker、run、dossier、diagnostic identity 全链一致。
- 对 Council finding 做可审计分类：共享 diagnostic 事实不计 Council 增量；仅 baseline 未出现且属于反证、风险、关键变量或有效假设质疑的 finding 才计入。
- artifact 内容或 digest 被替换、路径 envelope 不一致、finding 不合法时 fail closed。

**Non-Goals:**

- 不修改 `growth_expectation_engine.py`、contract 或既有 Council/fallback 编排。
- 不调用 LLM、provider 或真实运行产物；不执行正式多样本 A/B、盲评或 capability Gate。
- 不接入 G2 4.1 主流程质量门，不写 watchlist/debate/cache 成功路径。
- 不将 proof 结果描述为 G2 capability passed。

## Decisions

### 1. Proof boundary 只接受预计算 artifact

新增 `council/shared_diagnostic_proof.py`，公开纯函数接收 artifact mapping、validated input/assumption snapshot 绑定参数，以及 `strong_single_agent`/`council` 两个路径 envelope。函数只做 contract validation、canonical digest 和 identity comparison，不导入或调用 engine。

备选方案是让 proof 自己根据 input 调 engine。该方案会重复计算，无法证明真实路径消费的就是同一个已传递 artifact，因此不采用。

### 2. 以 canonical content digest 而非 Python object identity 判等

artifact 和 assumption snapshot 都通过 contract 的 canonical serializer 计算 digest；两条路径允许拥有独立 mapping 副本，但 canonical 内容必须完全相同。每条 envelope 同时携带 ticker、run_id、dossier_snapshot、diagnostic_digest 和 assumption_snapshot_digest，所有字段必须与 shared identity 相同。

备选方案是只比较 `diagnostic_digest`。这不能防止 envelope 记录错误的 ticker/run/dossier，也不能单独证明 assumption snapshot 内容一致，因此不采用。

### 3. 将 shared diagnostic 和 Council finding 分开计量

新增 `classify_council_increment`：先验证每个 `shared_diagnostic` finding 携带匹配的 diagnostic digest 与支持指标，再按稳定 fingerprint 去除 baseline 已有 finding；通过验证的 `shared_diagnostic` 不计入增量。仅允许四类 `counter_evidence`、`risk`、`key_variable`、`assumption_challenge` 作为有效增量。结果保存 excluded shared findings、duplicate findings 和 accepted findings；不合法 finding 直接 fail closed，便于审计“为什么计入/未计入”。

备选方案是按文本相似度或 token 数估算增量。该方案不确定、易把改写和诊断数字变化误算为洞察，故不采用。

### 4. Fail-closed 且不修改输入

所有输入 mapping 在验证前转为 canonical JSON digest；proof 不回填、不规范化、不覆盖 caller 的 artifact。任何 mutation、unknown field、identity mismatch 或 unsupported finding kind 都抛出专用 `SharedDiagnosticProofError`。

## Risks / Trade-offs

- [Risk] finding fingerprint 依赖调用方提供稳定标识 → 要求 fingerprint 为非空文本，并在 proof result 中保留逐项 audit 分类；正式 rubric 仍由后续 A/B child 冻结。
- [Risk] proof 只能证明输入共享，不能证明 LLM 实际忠实解释 artifact → 将解释质量、反证有效性和盲评留给 G2 6.x/7.x，不扩大 3.4。
- [Risk] 现有 legacy diagnostic fixture 可能没有完整 assumption snapshot → proof 使用现有 contract validator；不完整输入显式失败，不添加默认假设。

## Migration Plan

1. 新增 proof module 与 focused tests，先验证 RED，再实现最小纯函数。
2. 将 proof 作为独立 engineering harness 使用；本 change 不把它接入 Council/fallback 主流程。
3. 运行 focused/full tests、compileall、OpenSpec strict 和 diff check。
4. archive 时保留 spec/task 与测试证据；不迁移 runtime 产物。

回滚只需删除新增 proof module、tests 和本 change artifacts；不涉及数据迁移或生产缓存。

## Open Questions

- 正式 8–10 样本的 finding rubric、匿名评分和统计阈值由 G2 6.2/6.3 child 冻结，本 change 不预注册样本。
- 后续 A/B 是否将 proof result 嵌入 audit chain，由主流程质量门/A-B child 决定；本 change 只定义可独立运行的 proof 输出。
