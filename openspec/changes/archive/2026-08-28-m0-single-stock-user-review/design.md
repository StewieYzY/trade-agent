## Context

M0.1 已生成带 `artifact_digest`、`diagnostic_digest`、来源、报告期、`as_of`、假设快照和质量状态的 growth diagnostic artifact。M0.2 在相同的 ticker/run/dossier/profile 身份下生成了带 `artifact_digest` 的 strong-agent Thesis draft。M0.3 只需要把这两份已存在的产物交给用户复核，并保存用户填写的反馈；不应重新运行研究链路，也不应让模型替代用户做判断。

本 change 在 `value-screener/council/user_review.py` 建立一个离线、标准库优先的边界模块，并在 `value-screener/cli.py` 增加显式 input/output 路径的命令。输入 envelope 同时携带两份 artifact、它们的原始路径和用于重新校验 M0.2 的 dossier。模块复用 M0.1 的纯诊断 validator；M0.2 的 envelope 校验在本模块内以等价的纯 Python contract 校验实现，避免加载 Council/provider 运行时，不修改上游代码。

## Goals / Non-Goals

**Goals:**

- 在任何输出写入前校验 canonical ticker、run_id、dossier_snapshot、profile_version、M0.1/M0.2 artifact digest、diagnostic digest、路径引用和两份 artifact 的身份一致性。
- 记录事实、假设、成长预期诊断和 Thesis 草稿四个维度的用户结论与原文反馈。
- 强制保留 `accepted`、`question`、`problem`、`not_evaluable` 四种用户结论状态，并要求无法判断时填写原因。
- 记录用户填写的关键问题、认可内容、residual risk 和下一步决策，不由程序生成判断或建议。
- 从同一份结构化 review record 确定性生成 JSON/Markdown，写入显式 output directory。
- 明确区分 `review_status=template` 的 `capability_status=not_evidence` 与真实完成复核后的 `capability_status=mvp_evidence`；两者都保持 `gate_status=not_passed`。

**Non-Goals:**

- 不调用 provider、LLM、Council、DA 或 Synthesizer。
- 不修改 M0.1 diagnostic、M0.2 AgentOutput/Thesis draft 或稳定 `InvestmentThesis`。
- 不自动生成、归纳或判断用户反馈，不自动补全空字段。
- 不新增 `view_signal`、`investment_eligibility`、目标价、仓位、买卖或自动交易语义。
- 不实现数据库、前端、任务队列、M1/M2/M3 或 G2 Capability Gate。

## Decisions

### 1. 使用单一显式 review input envelope

输入版本固定为 `m0-single-stock-user-review-input-v1`，字段包括顶层身份、`dossier`、两份嵌入 artifact、两份 artifact 的用户提供路径以及 `user_review`。两份路径必须指向现存普通文件；这样 CLI 不依赖隐式 `/tmp` 文件，也不需要访问 provider，且记录可以回查用户实际提供的文件。artifact 内容仍由 envelope 明确提供。

替代方案是让 CLI 接受两个独立 artifact 路径并现场拼装。该方案会增加文件发现、路径覆盖和部分读取失败的分支，而且不利于 fixture 的确定性复现，因此不采用。

### 2. 从 raw artifact 重新验证身份和 digest

模块先用 M0.1 validator 验证 diagnostic artifact，再用本模块的纯 Python contract validator 验证 Thesis draft。该 validator 检查 Thesis draft 的 exact envelope、artifact digest、输入身份、dossier-bound `input_digest`、AgentOutput schema、数字 grounding，以及内嵌 diagnostic 与 M0.1 diagnostic 完全一致。两份 artifact 的路径引用必须指向现存普通文件。

任何缺字段、未知结构字段、ticker/run/snapshot/profile 不一致或 digest 错误都在创建 output directory 前失败。模块不信任 artifact 中的 capability/gate sidecar，validator 会强制其为 M0.1/M0.2 的既有 `mvp_evidence` 与 `not_passed` 状态。

### 3. 用户反馈使用固定四态且原样保存

四个维度统一使用：

```text
conclusion_status: accepted | question | problem | not_evaluable
feedback: string
issues_or_corrections: list[string]
not_evaluable_reason: string
```

`not_evaluable` 必须有非空 `not_evaluable_reason`；其他状态也保留该字段但要求为空，避免程序猜测用户为何无法判断。顶层 `key_issues`、`accepted_content`、`residual_risk` 为用户填写的字符串列表，`next_decision` 为用户填写的非空字符串。渲染器只展示这些字段，不增加模型摘要或建议。

### 4. Template 与真实复核分开表达

`review_status=template` 仅用于契约/空白模板或开发 fixture，四维反馈可以为空，但其输出必须是 `capability_status=not_evidence`，并在 Markdown 中显示 `M0 product loop = pending user review`。`review_status=completed` 要求四个维度、关键问题、认可内容、residual risk 和下一步决策均由用户显式填写，输出才标记 `capability_status=mvp_evidence`。无论哪种状态，`gate_status` 固定为 `not_passed`。

### 5. 确定性文件和 CLI 边界

JSON 使用 `sort_keys=True`、严格 JSON、无运行时间戳；Markdown 从已验证 record 生成，固定文件名为 `<canonical_ticker>-<run_id>.json` 与 `.md`。CLI 只读取显式 `--input`，只写显式 `--output-dir`，不初始化任何数据或模型客户端。

## Risks / Trade-offs

- [Risk] 用户填写的自然语言可能提及交易动作 → 结构化 schema 不提供交易字段，Markdown 只作边界提示；不会把自由文本改写成程序化交易语义。
- [Risk] artifact 文件内容可能在复核后被替换 → M0.3 绑定的是 input 中嵌入 artifact 的 digest，路径同时要求指向现存文件；需要把 artifact 文件本身纳入外部归档或后续 content-hash 体系，当前模块不会重新读取路径文件。
- [Risk] `template` 记录被误认为用户已复核 → 输出同时标记 `review_status=template`、`capability_status=not_evidence`，并在 Markdown 明示产品闭环 pending。
- [Risk] 上游 artifact schema 未来变化 → 本模块固定版本和 exact field whitelist，版本或字段不匹配时 fail closed，而不是静默兼容；M0.2 contract 的校验逻辑需随上游 schema 变更同步更新。
- [Risk] 单次用户反馈不足以支撑 G2 → 固定 `gate_status=not_passed`，并在产物和 OpenSpec 中区分 MVP evidence 与正式 Gate evidence。
