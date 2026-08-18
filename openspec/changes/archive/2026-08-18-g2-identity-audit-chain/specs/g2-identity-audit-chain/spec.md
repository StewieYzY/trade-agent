## ADDED Requirements

### Requirement: Canonical identity context

系统 SHALL 为每次 audited G2 execution 创建一个不可变 identity context，至少包含
canonical ticker、run_id、profile_version、input_hash、dossier snapshot/version、
prompt version 和 model configuration。

#### Scenario: Missing or non-canonical ticker
- **WHEN** audited execution 缺少 ticker、ticker 非 canonical 或无法由统一 SoT 解析
- **THEN** 系统 MUST fail closed，并 MUST NOT 写入 dossier、prompt、debate、quality 或 final success artifact

#### Scenario: One run id only
- **WHEN** 下游阶段接收到已有 identity context
- **THEN** 下游 MUST 使用同一个 run_id，MUST NOT 静默生成或替换 run_id

#### Scenario: Supplied identity is structurally invalid
- **WHEN** 调用方传入 ticker 非 canonical、run_id 含路径成分、缺少版本字段、input hash 非 SHA-256 或 model configuration 非 strict JSON 的 identity
- **THEN** 系统 MUST 在读取 dossier、解析 output root、构造 artifact path、检查 cache 或调用模型前 fail closed

### Requirement: Cross-artifact identity binding

每个 dossier、prompt、debate、quality report 和 final result artifact SHALL 携带完全相同
的 ticker、run_id、profile、input hash、dossier snapshot、prompt version 和 model
configuration。

#### Scenario: Identity mismatch
- **WHEN** 任一 artifact 的 ticker、run_id、profile、snapshot 或 model configuration 与 context 不一致
- **THEN** 系统 MUST fail closed，并 MUST NOT 发布或写入成功结果

#### Scenario: Nested final result identity mismatch
- **WHEN** final result artifact 内嵌的 published output 或 fallback result 的 ticker、run_id、profile、input hash、snapshot、prompt version 或 model configuration 与 context 不一致
- **THEN** writer 和 chain verification MUST fail closed，即使内嵌 payload 的 hash 已被重新计算

#### Scenario: Fallback uses shared identity
- **WHEN** fallback 与 Council 使用同一份 audited dossier
- **THEN** fallback SHALL 复用同一个 identity context，不得产生另一份 identity 语义

### Requirement: Verifiable hash chain

系统 SHALL 按 `dossier → prompt → debate → quality report → final result` 保存 artifact
hash 和 parent hash；manifest SHALL 保存 artifact 顺序、路径、hash 和 identity digest。

#### Scenario: Tampered payload
- **WHEN** artifact payload 被修改而 payload hash 未同步更新
- **THEN** chain verification MUST fail closed

#### Scenario: Broken parent chain
- **WHEN** quality report 或 final result 引用不存在、错误顺序或不同 identity 的 parent hash
- **THEN** chain verification MUST fail closed

#### Scenario: Prompt or fallback evidence is rebound
- **WHEN** prompt binding hash 与完整 identity/prompt records 不一致，或 fallback response 不能重建记录的 agent output
- **THEN** writer 和 chain verification MUST fail closed

### Requirement: Run-scoped persistence

持久化 SHALL 使用包含 run_id 的隔离 root，并 SHALL 采用 exclusive create 防止覆盖。

#### Scenario: Same ticker same day twice
- **WHEN** 同一 canonical ticker 在同一天运行两次
- **THEN** 两次运行 MUST 使用不同 run_id，并保留两套完整可复核 artifacts

#### Scenario: Existing artifact path
- **WHEN** artifact path 已存在
- **THEN** writer MUST 拒绝覆盖并 fail closed

#### Scenario: Audit transaction fails
- **WHEN** 五段 artifact、manifest 或 publish promotion 任一阶段失败
- **THEN** 系统 MUST NOT 在 published audit root 留下 partial chain 或成功 manifest，也 MUST NOT 发布 final runtime result

#### Scenario: Runtime and audit roots conflict
- **WHEN** audited fallback 的 output root 与 audit root resolve 为同一路径
- **THEN** 系统 MUST 在创建 run directory 前 fail closed

### Requirement: Audit evidence and scope boundary

系统 SHALL 保存可复核 identity/provenance evidence；任何 identity failure SHALL 可定位
到 artifact type、字段或 hash。该 child MUST NOT 修改 G2 umbrella final capability
verdict，MUST NOT 实现 G2 1.2/1.3、后续 M4/M4.5/M5 或 G3 runtime。

#### Scenario: Recompute evidence
- **WHEN** reviewer 读取 manifest 和 artifacts
- **THEN** reviewer SHALL 能重算 identity digest、payload hash 和 parent chain，并得到一致结果
