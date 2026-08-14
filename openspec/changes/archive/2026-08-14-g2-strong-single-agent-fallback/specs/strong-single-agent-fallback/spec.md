## ADDED Requirements

### Requirement: Fallback input is preflighted before side effects
fallback SHALL 在任何 LLM 调用、artifact 写入、Council cache 或 watchlist 写入前复用并通过 dossier input preflight；空对象、error/guard 壳、核心事实不足、主营事实缺失或 ticker mismatch SHALL fail closed。

#### Scenario: Invalid dossier has zero side effect
- **WHEN** fallback 收到显式空 features、error shell 或 ticker mismatch
- **THEN** SHALL 抛出可识别错误，不调用 LLM，不创建 fallback artifact，不写 Council/watchlist 文件

#### Scenario: Valid dossier is bound to ticker
- **WHEN** dossier 通过 preflight
- **THEN** fallback SHALL 记录 canonical ticker 和 features hash，并将其用于本次唯一请求

### Requirement: Fallback calls one strong agent only
每次 fallback run SHALL 只调用一个预注册 agent 的 strong reasoning model 一次；默认模型 SHALL 来自 `LLM_MODEL_HEAVY`，显式 model override SHALL 记录在 artifact 中。

#### Scenario: Single call is bounded
- **WHEN** valid dossier enters fallback
- **THEN** SHALL 产生最多一次 agent LLM call，SHALL NOT 调用 R2、DA 或额外 LLM synthesizer

#### Scenario: Model provenance is recorded
- **WHEN** single agent call completes or fails
- **THEN** artifact SHALL 记录 agent id、model id、provider host、usage 和 request hashes

### Requirement: R1 quality breaker blocks contaminated output
fallback SHALL 在 synthesis 前严格校验 AgentOutput，并运行 grounding 与 circular-reference fact checks；schema、transport、grounding 或 circular-reference 任一失败 SHALL 将 run 标为 `blocked`。

#### Scenario: Schema failure blocks release
- **WHEN** agent 返回非法 JSON 或字段类型错误
- **THEN** SHALL 保留首次 raw/error，标记 `blocked`，不得发布 bullish/bearish/neutral final signal

#### Scenario: Fabricated metric blocks release
- **WHEN** agent 的 key metric 数字无法在当前 dossier 找到
- **THEN** fact checker SHALL 记录 issue，quality breaker SHALL 标记 `blocked`

#### Scenario: Circular reference blocks release
- **WHEN** R1 core thesis 引用其他 agent 或当轮观点
- **THEN** quality breaker SHALL 标记 `blocked`，不得进入 clean synthesis

### Requirement: Deterministic synthesizer fallback is non-fabricating
fallback synthesis SHALL 不调用额外 LLM；质量通过时只复制已验证 agent 字段，质量失败时 SHALL 输出 `signal=skip`、`conviction=0` 和 pending verification，不得新增事实。

#### Scenario: Passed output is copied without new facts
- **WHEN** AgentOutput schema-valid 且 fact checks 通过
- **THEN** synthesis SHALL 保留 agent signal/conviction/core thesis/key metrics/risks/what-would-change，且标记 `quality_status=passed`

#### Scenario: Blocked output becomes safe skip
- **WHEN** schema/transport/fact-check 任一失败
- **THEN** synthesis SHALL 使用 `signal=skip`、`conviction=0`，保留 error/issues，且标记 `quality_status=blocked`

### Requirement: Fallback artifacts cannot become Council success
fallback SHALL 只写 run-scoped diagnostic artifact；SHALL NOT 写入 Council success cache、`watchlist/` 或伪装为完整 CouncilResult。

#### Scenario: Artifact is isolated
- **WHEN** fallback run completes or blocks
- **THEN** SHALL 生成 `fallback_runs/<run_id>/manifest.json` 与 `result.json`，且 Council/watchlist 目录无新增成功文件

#### Scenario: Quality state persists
- **WHEN** run 为 passed、blocked 或 transport failure
- **THEN** artifact SHALL 持久化 `quality_status`、fact-check issues、pending verification 和 failure kind

### Requirement: Explicit dossier identity is canonical and shared
显式 dossier SHALL 存在非空 canonical `core_snapshot.ticker`，且 `core_snapshot`、顶层可选
section 与任一 `research_dossier` section 中出现的 `ticker`、`code` 或 `symbol` SHALL 与请求 ticker 一致。该校验 SHALL
在 artifact、cache、watchlist 和 LLM 调用前执行，并 SHALL 与 Council preflight 共享同一语义。

#### Scenario: Missing or mismatched explicit identity fails closed
- **WHEN** `core_snapshot.ticker` 缺失、为空、非法，或 optional section identity 与请求 ticker 不一致
- **THEN** fallback 和 Council SHALL 抛出可识别的 `no_evidence`/ticker 错误，不调用 LLM，不写 artifact、cache 或 watchlist

#### Scenario: Canonical identity is retained on valid input
- **WHEN** explicit dossier identity matches a request expressed in an equivalent non-canonical form
- **THEN** fallback SHALL use and persist the canonical ticker for the request, artifact and synthesis

### Requirement: Fallback diagnostics reuse shared redaction and path boundaries
fallback SHALL 调用 shared `redact_sensitive_text()` 处理错误诊断，并 SHALL 调用 shared
`validate_g1_output_root()` 验证 output root；fallback MUST NOT 复制另一套 secret pattern
或 protected production path 列表。

#### Scenario: Sensitive error content is not persisted
- **WHEN** provider/LLM error or malformed raw response contains API key, token, bearer authorization, URL credentials or nested mapping/list values
- **THEN** `error`、raw、manifest 和 `result.json` SHALL 不包含原始敏感值，同时保留可诊断的错误类型/状态

#### Scenario: Protected production roots fail before side effects
- **WHEN** output root is a protected root, its exact/ancestor/descendant, or a symlink resolving to one
- **THEN** fallback SHALL fail closed before artifact creation or LLM invocation; external run-scoped roots remain governed by the shared validator

### Post-archive CR repair clarification

The closure evidence additionally requires:

- recursive identity validation inside `core_snapshot`, optional top-level sections, and `research_dossier`;
- recursive redaction of schema-valid `agent_output`, `usage`, raw JSON, error strings, and nested secret-bearing values;
- bare credential redaction is limited to a standalone `Bearer|Token <credential>` string so normal diagnostic phrases remain intact;
- identity walking covers `collections.abc.Mapping` as well as plain dictionaries and sequences;
- protected output-root validation before dossier/provider preflight, including `features=None`;
- CURRENT handoff metadata and OpenSpec status table must match the archived state and integrated commit.
