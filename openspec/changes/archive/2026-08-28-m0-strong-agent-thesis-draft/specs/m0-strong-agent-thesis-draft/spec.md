# m0-strong-agent-thesis-draft Specification

## Purpose

为 M0.2 提供从已校验 M0.1 growth diagnostic artifact 和可信 dossier 到单股 strong single-agent Thesis 草稿的最小可运行链路。产物是 `mvp_evidence`，必须保留人工复核和 `gate_status=not_passed` 边界。

## ADDED Requirements

### Requirement: Draft input is explicit and identity-bound

系统 SHALL 接受版本为 `m0-strong-agent-thesis-draft-input-v1` 的显式 JSON envelope，包含 canonical ticker、run_id、dossier_snapshot、profile_version、完整 M0.1 diagnostic artifact 和 dossier。系统 SHALL 校验 artifact digest、diagnostic digest、ticker、run、snapshot、profile 以及 dossier raw payload 的 ticker 一致性；未知字段、缺字段、digest 错误或身份错配 MUST fail closed。

#### Scenario: Valid diagnostic and dossier are accepted

- **WHEN** 输入 envelope 的 identity 与 M0.1 artifact、diagnostic 和 dossier 一致，且高严重度事实可追溯
- **THEN** 系统 SHALL 构造已验证的 draft input 并进入单 Agent 调用

#### Scenario: Invalid input has no LLM or file side effect

- **WHEN** 输入缺字段、ticker/run/snapshot/profile 不一致、artifact digest 错误或 dossier 事实契约阻断
- **THEN** 系统 SHALL 在 LLM 调用前抛出验证错误，且输出目录 SHALL 不产生 JSON/Markdown 草稿

### Requirement: Strong single-agent boundary is exactly one call

系统 SHALL 使用现有 strong LLM client 的 no-retry 路径对同一份已验证输入进行一次 provider request，调用等级 SHALL 为 `heavy`，并 SHALL 记录模型、prompt/input digest 和调用 usage。系统 MUST NOT 调用 Council、DA、Synthesizer 或第二次 LLM/provider request。

#### Scenario: One strong call produces a draft

- **WHEN** Agent 返回合法 `AgentOutput` 及 Thesis 扩展字段
- **THEN** 系统 SHALL 生成一份带完整 identity、diagnostic digest、AgentOutput 和 Thesis 字段的 draft envelope

#### Scenario: Transport or schema failure is visible

- **WHEN** LLM transport 失败或返回 JSON/字段校验失败
- **THEN** 系统 SHALL 生成 `quality_status=failed`、`agent_output.signal=skip`、`agent_output.conviction=0` 的非方向性草稿，并保留失败类型/原因；系统 SHALL 不重试第二次 Thesis/provider 调用

### Requirement: Draft preserves the single-agent research judgment

成功草稿 SHALL 至少包含 artifact identity、diagnostic 摘要、完整通过校验的 `AgentOutput`、quality status、quality reasons、risks、pending verification、`capability_status` 和 `gate_status`。AgentOutput 的未知稳定接口字段 SHALL 被拒绝，`key_metrics` SHALL 是 `list[str]`，其中无法在已验证 dossier/diagnostic 找到的数字 SHALL 触发 grounding failure。本 child SHALL 保留 `AgentOutput.signal` 作为单 Agent 观点，但 MUST NOT 把它升级为稳定版 `InvestmentThesis`、完整 `view_signal` 或 `investment_eligibility` 语义。

#### Scenario: Agent judgment is preserved

- **WHEN** Agent 返回合法的 `signal`、`conviction`、`core_thesis`、`key_metrics`、`risks` 和改变条件
- **THEN** draft SHALL 原样保留通过 `AgentOutput` 校验的字段，并明确这是 Thesis 草稿而非稳定投资资格结论

#### Scenario: Model rejects or is out of circle

- **WHEN** Agent 返回 `signal=skip` 或 `out_of_circle=true`
- **THEN** draft SHALL 使用 `agent_output.signal=skip`、`agent_output.conviction=0` 的安全草稿，并保留 pending verification/quality reason

#### Scenario: Grounding or forbidden-field failure is visible

- **WHEN** AgentOutput 包含未定义的稳定接口字段，或 `key_metrics` 包含无法在已验证输入中找到的数字
- **THEN** draft SHALL 标记 `quality_status=failed`，使用 `signal=skip`、`conviction=0` 的安全 AgentOutput，并 SHALL 不发布未验证字段

### Requirement: Diagnostic status is preserved and cannot be upgraded

系统 SHALL 原样保留 M0.1 diagnostic、assumption snapshot、provenance、source metadata、warnings/reasons、calculation status 和 digests。对于 diagnostic `not_evaluable` 或 `failed`，draft MUST NOT 发布 numeric valuation conclusion、clean quality 或 investable eligibility；系统 SHALL 产生非方向性草稿。

#### Scenario: Diagnostic warning remains visible

- **WHEN** diagnostic 为 `degraded` 或带 warning
- **THEN** draft SHALL 保留其 warning/reasons，并将 draft quality 标记为不高于 `warning`

#### Scenario: Failed dossier is blocked before model call

- **WHEN** raw dossier fact contract 的质量状态为 `failed`
- **THEN** 系统 SHALL 在创建输出目录和 LLM 调用前 fail closed，且不得写入草稿文件

#### Scenario: Diagnostic cannot be numerically upgraded

- **WHEN** diagnostic 为 `not_evaluable` 或 `failed`
- **THEN** draft SHALL 保留失败 metadata、不得含新的数值估值结论，且 `agent_output.signal=skip`、`agent_output.conviction=0`

### Requirement: Draft artifacts are deterministic and reviewable

系统 SHALL 将 draft envelope 写入显式 output directory 下的固定 JSON 和 Markdown 文件。JSON SHALL 使用严格 JSON、固定 schema、稳定键序和无运行时间戳；Markdown SHALL 展示 identity、事实来源、diagnostic status、核心 Thesis、证据/反证、风险、关键变量、改变条件、待验证项、质量状态和人工复核提示，并 SHALL 标记 `capability_status=mvp_evidence`、`gate_status=not_passed`。

#### Scenario: Same input and response render identically

- **WHEN** 使用相同输入和相同模型响应运行两次
- **THEN** JSON 内容、Markdown 内容、input/prompt/response digests SHALL 相同

#### Scenario: CLI uses explicit paths

- **WHEN** 用户运行 `strong-agent-thesis-draft --input <file> --output-dir <dir>`
- **THEN** CLI SHALL 只读取该 input、只在该目录写入两个产物并打印路径，且不初始化 provider/fetcher

## Out of Scope

本 capability SHALL NOT 实现 Council、多轮辩论、DA、Synthesizer、稳定版 `InvestmentThesis`、M2 baseline、A/B harness、G3 runtime、前端、自动交易、目标价或正式 Capability Gate evidence。
