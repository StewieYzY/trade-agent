## ADDED Requirements

### Requirement: Review input is explicit and identity-bound

系统 SHALL 接受版本为 `m0-single-stock-user-review-input-v1` 的显式 JSON envelope，包含 canonical ticker、run_id、dossier_snapshot、profile_version、M0.1 diagnostic artifact、M0.2 Thesis draft artifact、dossier 和两份 artifact 的用户提供路径。两份路径 SHALL 指向现存普通文件。系统 SHALL 从 raw artifact 重新校验两份 artifact 的 digest、diagnostic digest、canonical ticker、run_id、dossier_snapshot、profile_version 以及两份 artifact 的相互绑定。未知字段、缺字段、路径为空/不存在或身份/digest 错配 MUST fail closed，且在 output directory 创建前不得产生文件副作用。

#### Scenario: Valid paired artifacts are accepted

- **WHEN** 两份 artifact、dossier 和顶层身份属于同一 canonical ticker/run/snapshot/profile，且 M0.1/M0.2 digest 与嵌入内容一致
- **THEN** 系统 SHALL 构造已验证的 review input 并继续校验用户复核字段

#### Scenario: Invalid identity or digest is rejected before output

- **WHEN** 输入缺字段、包含未知顶层字段、artifact 路径为空、ticker/run/snapshot/profile 不一致或任一 digest 被篡改
- **THEN** 系统 SHALL 抛出验证错误，不调用 provider/LLM，且 output directory SHALL 不存在

#### Scenario: Missing artifact path is rejected before output

- **WHEN** 任一用户提供的 artifact path 不存在或不是普通文件
- **THEN** 系统 SHALL 抛出路径验证错误，不生成 review record

### Requirement: User review covers four required dimensions

系统 SHALL 记录四个固定维度：`facts`、`assumptions`、`growth_expectation` 和 `thesis_draft`。每个维度 SHALL 包含 `conclusion_status`、`feedback`、`issues_or_corrections` 和 `not_evaluable_reason`。`conclusion_status` SHALL 只能是 `accepted`、`question`、`problem` 或 `not_evaluable`；当状态为 `not_evaluable` 时，原因 SHALL 非空，当状态为其他值时原因 SHALL 为空。系统 MUST 保存用户原始填写内容，不得由模型或程序生成反馈。

#### Scenario: Four dimensions preserve user feedback

- **WHEN** 用户为四个维度分别填写认可、疑问、问题或无法判断状态及对应反馈
- **THEN** review record SHALL 原样保存四个维度的状态、反馈、问题/修正和无法判断原因

#### Scenario: Not evaluable requires an explicit reason

- **WHEN** 任一维度标记为 `not_evaluable` 但未填写原因，或非 `not_evaluable` 状态填写了原因
- **THEN** 系统 SHALL 拒绝该 review input 并返回字段级验证错误

### Requirement: User owns the summary and next-step decision

系统 SHALL 要求 `key_issues`、`accepted_content`、`residual_risk` 和 `next_decision` 由用户在 input envelope 中显式填写。`next_decision` SHALL 为非空字符串；系统不得自动生成、改写、归纳或替用户填写下一步决策，也不得生成买入、卖出、仓位或目标价字段。

#### Scenario: Completed review contains user-owned closure fields

- **WHEN** `review_status=completed` 且用户填写关键问题、认可内容、residual risk 和下一步决策
- **THEN** review record SHALL 保存这些字段，并将其 owner 标记为 `user`

#### Scenario: Missing next decision is rejected

- **WHEN** 完成复核的 input 缺少 `next_decision` 或其内容为空
- **THEN** 系统 SHALL 拒绝生成 review record，不得猜测用户的下一步

### Requirement: Template and completed review have distinct evidence status

系统 SHALL 支持 `review_status=template` 和 `review_status=completed`。template 仅用于契约/开发 fixture，输出 SHALL 标记 `capability_status=not_evidence` 并明确 `M0 product loop = pending user review`；completed 输出 SHALL 标记 `capability_status=mvp_evidence`。两种状态的 `gate_status` MUST 固定为 `not_passed`，且不得被解释为 G2 Capability Gate evidence。

#### Scenario: Template is not reported as user evidence

- **WHEN** 输入为 `review_status=template`
- **THEN** 输出 SHALL 保留空白复核字段，标记 `capability_status=not_evidence`，并在 Markdown 中说明尚未完成真实用户复核

#### Scenario: Completed review is MVP evidence only

- **WHEN** 输入为 `review_status=completed` 且四维及总结字段均通过校验
- **THEN** 输出 SHALL 标记 `capability_status=mvp_evidence`、`gate_status=not_passed`，并明确该记录不是正式 G2 Gate evidence

### Requirement: Review artifacts are deterministic and traceable

系统 SHALL 在显式 output directory 下生成固定 JSON 和 Markdown 文件。JSON SHALL 使用严格 JSON、稳定键序和无运行时间戳；Markdown SHALL 展示两份被复核 artifact 的路径、digest、identity、报告期/来源或质量状态、四维反馈、关键问题、认可内容、residual risk、下一步决策和 evidence status。相同 input SHALL 生成完全相同的 JSON/Markdown 内容。

#### Scenario: Same input renders identically

- **WHEN** 使用相同 input envelope 在两个不同 output directory 生成 review record
- **THEN** 两份 JSON 内容和 Markdown 内容 SHALL 完全一致，且只在各自显式目录产生文件

#### Scenario: Artifact traceability is visible

- **WHEN** review record 生成成功
- **THEN** JSON 和 Markdown SHALL 同时包含 diagnostic/thesis artifact path、artifact digest、canonical ticker、run_id、dossier_snapshot 和 profile_version

### Requirement: CLI is offline and path-confined

系统 SHALL 提供 `single-stock-user-review --input <file> --output-dir <dir>` 命令。CLI SHALL 只读取显式 input 文件、只在显式 output directory 写入 review record JSON/Markdown，并 SHALL 不初始化 provider、LLM、Council、DA 或 Synthesizer。

#### Scenario: Explicit CLI paths produce two files

- **WHEN** 用户使用有效 input 文件和 output directory 运行 `single-stock-user-review`
- **THEN** CLI SHALL 打印两个产物路径，并只在指定目录生成固定 JSON/Markdown 文件

#### Scenario: Missing input is reported clearly

- **WHEN** `--input` 指向不存在文件或文件不是有效 JSON
- **THEN** CLI SHALL 返回明确的参数错误，不创建 output directory
