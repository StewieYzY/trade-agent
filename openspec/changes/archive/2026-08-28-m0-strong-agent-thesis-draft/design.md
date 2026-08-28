## Context

M0.1 已在 `data.lib.frozen_growth_diagnostic` 提供版本化 diagnostic artifact、输入身份绑定、digest 校验和确定性产物。现有 `council.fallback` 已证明可以执行一次 strong agent 调用，但其结果是 fallback 质量 envelope，不能直接冒充 M0.2 Thesis 草稿。M0.2 需要把两者接成一个单股、可人工复核的最小链路。

## Goals / Non-Goals

**Goals:**

- 只接受带 canonical ticker、run identity、dossier snapshot、profile version 和完整 M0.1 diagnostic artifact 的显式输入。
- 在 LLM 调用前从 raw payload 校验 diagnostic 绑定和 dossier 事实质量。
- 对同一输入执行一次 `call_llm_once(..., "heavy", model=...)`，确保只有一次 provider request；禁止 Council 多轮、DA 或第二次 synthesis LLM 调用。
- 校验 AgentOutput 及 Thesis 草稿语义，生成稳定 JSON/Markdown；模型失败或拒答时保留可审计的非方向性草稿。
- 保留 AgentOutput 的观点字段，但不在本 child 固化完整 `view_signal`/`investment_eligibility` 语义。

**Non-Goals:**

- 不实现稳定版 `InvestmentThesis` interface，不修改 `openspec/specs/investment-thesis` 的要求。
- 不运行 provider，不重新计算 growth diagnostic，不修改 diagnostic 数值或隐藏 warning。
- 不调用 Council、DA、Synthesizer，不建立 A/B harness，不证明 Council 增量。
- 不输出目标价、仓位、自动买卖指令，不实现 G3 HoldingContract。
- 不更新根目录 handoff、roadmap 或其他用户 WIP。

## Decisions

### 1. 新增独立 draft adapter，不改 Council 主编排

新增 `council/thesis_draft.py`，输入为显式 draft envelope，输出为 `ThesisDraftArtifacts`。它复用 `frozen_growth_diagnostic.validate_frozen_growth_diagnostic_artifact`、`council.debate._validate_council_input`、`council.fact_grounding` 和 `council.llm.call_llm_once`，但不把 M0.2 接入 `run_debate` 或 fallback 成功缓存。

备选方案是扩展 `run_fallback` 直接改变其 result schema；这会把既有 fallback 合同和 M0.2 草稿语义耦合，增加回归风险，因此不采用。

### 2. 输入绑定与失败边界

输入 envelope 使用 `m0-strong-agent-thesis-draft-input-v1`，字段为 `canonical_ticker`、`run_id`、`dossier_snapshot`、`profile_version`、`diagnostic_artifact` 和 `dossier`。adapter 从 diagnostic artifact 的 `diagnostic.input_snapshot` 与 `diagnostic.assumption_snapshot` 重建 M0.1 验证所需 bundle view，并校验 artifact digest、diagnostic digest、ticker/run/snapshot/profile。dossier 的 core ticker 和所有声明 ticker 必须与 canonical ticker 一致，raw fact contract 的高严重度不可追溯事实 fail closed；dossier 派生质量为 `failed` 时也在 output directory 和 LLM 之前阻断。

结构错误、身份错配、事实质量阻断发生在 LLM 之前并抛出错误，不写任何草稿文件。LLM transport/schema 错误则写入 `quality_status=failed` 的非方向性草稿；Agent 明确 `signal=skip`、`out_of_circle=true` 或 diagnostic 为 `not_evaluable/failed` 时，草稿归一为 `agent_output.signal=skip` 且 `conviction=0`，不得发布方向性结论。

### 3. Agent 输出与确定性 Thesis 草稿

强 Agent 使用现有 `buffett` prompt builder 的投资框架，并追加 M0.2 输出要求。模型返回按现有 `AgentOutput.from_json` 校验；不允许未知稳定接口字段，且 `key_metrics` 的数字必须通过既有 deterministic grounding。草稿 envelope 保留完整 `AgentOutput`、diagnostic 摘要、质量状态、失败原因、风险和待验证项。M0.2 不扩展或固化稳定版 `InvestmentThesis`、`view_signal` 或 `investment_eligibility` 的完整语义；这些属于后续 M2 child。

Thesis envelope 只复制已校验的 agent 字段和输入 diagnostic/dossier quality metadata；不让模型改写 diagnostic。JSON 使用排序键、固定 schema version 和无时间戳序列化；Markdown 由同一 JSON envelope 确定性渲染，明确“草稿、人工复核、非 Gate evidence”。

### 4. 文件与 CLI

CLI 命令为 `strong-agent-thesis-draft --input <input.json> --output-dir <dir> [--model <model>]`。输入文件由 CLI 读取，adapter 负责全部校验和产物写入；文件名固定为 `<canonical_ticker>-<run_id>.json/.md`，目录由调用方显式传入并隔离。CLI 不初始化 fetcher；真实 LLM 仅在用户显式运行命令且环境变量/模型可用时调用。

## Risks / Trade-offs

- [Risk] 单次模型输出可能遗漏某个 AgentOutput 字段 → 对 AgentOutput 严格 schema 校验，失败时输出 failed/skip 语义而非静默补齐。
- [Risk] 现有 LLM helper 默认会在 HTTP 错误时重试 → M0.2 使用 `call_llm_once` 关闭 retry，避免一次 Agent 调用产生第二次 provider request。
- [Risk] dossier sidecar 伪造 clean 状态 → 每次从 raw payload 重建 fact contract，禁止信任质量 sidecar。
- [Risk] diagnostic 为 warning/failed 仍被模型写成 bullish → adapter 在最终 envelope 做 deterministic downgrade，保留模型原始结构但不发布投资资格。
- [Risk] M0.2 被误解为稳定 G2 接口 → schema、Markdown 和 OpenSpec 明确 `mvp_evidence`/`not_passed` 与人工复核边界。

## Migration Plan

新增模块和 CLI 命令，不迁移既有 fallback/council 产物。用户使用 M0.1 JSON artifact 与同一 run 的 dossier 组装 input envelope 后运行；若输入或模型失败，保留失败草稿用于 M0.3 复核。未来 M2 或稳定接口 child 可复用字段，但不得把本实验 schema 直接升级为正式 `InvestmentThesis`。

## Open Questions

- M0.3 决定人工复核记录的最终文件格式；本 change 只在 Markdown 中提示复核，不写用户反馈。
- 真实模型、样本股票、预算和 baseline 比较由后续 M2/A-B child 冻结。
