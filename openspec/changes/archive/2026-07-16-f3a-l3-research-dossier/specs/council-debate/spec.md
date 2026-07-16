## MODIFIED Requirements

### Requirement: 辩论编排 4 轮串行
debate.py SHALL 实现 4 轮串行辩论编排：

- **Round 1（各自表态）**：所有 agent 并行调用 LLM，彼此隔离（不传他人论点），使用重度推理模型；user message SHALL 按 agent_id 从 dossier 取角色侧重子集（`core_snapshot` 全员共享 + 定性维度按角色分发，见下方「角色分发按 agent_id 构造 user message」requirement）
- **分歧度分流**：R1 完成后计算分歧度，按 level 决定是否跳过 R2/R3
- **Round 2（交叉质疑）**：所有 agent 并行调用 LLM，每个 agent 可见其他 agent 的 R1 AgentOutput JSON，使用重度推理模型；单 agent 场景下跳过 LLM 调用；R2 prompt SHALL **encourage** 引用 R1 未充分覆盖的数据维度，如无则 **may** 声明 `evidence_exhausted`（**soft signal，非硬约束**，f3a 保持 soft 不升 hard，见 [[design]] D8）；user message SHALL 按 agent_id 角色分发（同 R1）
- **Round 3（DA 仲裁）**：Devil's Advocate 单独调用，可见 R1+R2 全部讨论 + 原始 dossier（做事实回查，含定性维度数字），使用重度推理模型；DA SHALL 走全量路径（不分发，见下方「角色分发按 agent_id 构造 user message」requirement）；**DA skipped 条件**：① 分流 `level == "low"` 或 `"extreme"` 跳 R2/R3；② R2 中 ≥3 agent 标 `evidence_exhausted` 跳 R3；③ 运行时降级（error rate ≥0.4）跳 R3。被跳时 `CouncilResult.round3 == None` + `CouncilResult.da_skipped_reason` 取四值之一。注：`da_skipped_reason` 存 `CouncilResult`（编排器内部状态，非 L3 输出 schema，不违反 f1 N1）
- **Round 4（收敛共识）**：Synthesizer 单独调用，可见 R1（+R2 if ran）+（DA 仲裁报告 if ran，否则 `da_skipped_reason`）+ 原始 dossier，使用中度推理模型，产出含分歧报告的 SynthesizerOutput；Synthesizer SHALL 走全量路径（不分发）

信息可见性 SHALL 由编排器控制（R1 彼此隔离但按角色分发 dossier 子集 / R2 可见他人 + 按角色分发 / R3 全知含 dossier / R4 全知含 dossier + DA 仲裁报告 if ran，否则含 `da_skipped_reason`），不由 agent 自行决定。

> **f3a 修订（2026-07-13）**：`run_debate` 的 L3 入口从 `assemble_council_features(ticker)` 改为 `build_research_dossier(ticker)`（见下方「run_debate 入口改调 build_research_dossier」requirement），`call_agent`/`_call_da`/`_call_synthesizer` 的 `features` 形参语义从「扁平 21 字段」变为「分层 dossier」（形参名保持 `features` 不变，避免 cascade 改名）。R1/R2 的 user message 按 agent_id 角色分发 dossier 子集，R3/R4 走全量。[[design]] D3/D4。

#### Scenario: R1 信息隔离但按角色分发
- **WHEN** 执行 Round 1 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 为空列表，且 user message SHALL 按 agent_id 从 dossier 取角色侧重子集（`core_snapshot` 全员共享 + 定性维度按角色分发）

#### Scenario: R2 可见他人 R1 论点且按角色分发
- **WHEN** 执行 Round 2 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 包含 R1 中其他 agent 的 AgentOutput JSON（排除自己），且 user message SHALL 按 agent_id 角色分发 dossier 子集（同 R1）

#### Scenario: R3 DA 走全量路径
- **WHEN** 执行 Round 3（DA 未被跳过）
- **THEN** DA 的 user message SHALL 含 dossier 全部维度（不分发，`research_dossier` 全量），区别于 agent 的角色分发路径

#### Scenario: R4 Synthesizer 走全量路径
- **WHEN** 执行 Round 4
- **THEN** Synthesizer 的 user message SHALL 含 dossier 全部维度（不分发）

#### Scenario: R1 低分歧跳过 R2/R3
- **WHEN** R1 计算得 `level == "low"`
- **THEN** `run_debate` SHALL 跳过 R2 和 R3，直接进入 R4，CouncilResult.round2/round3 为 None

#### Scenario: 单 agent 下 R2 跳过 LLM 调用
- **WHEN** 只有 1 个 agent 执行 Round 2
- **THEN** 系统 SHALL 跳过 LLM 调用，CouncilResult.round2 为 None，不调用 LLM 浪费 token

#### Scenario: 单 agent 下 R3/R4 跳过
- **WHEN** 只有 1 个 agent 且无 DA/synthesizer 注册
- **THEN** R3/R4 SHALL 返回 None，不报错，CouncilResult 中对应轮次为 None

## ADDED Requirements

### Requirement: 角色分发按 agent_id 构造 user message
`_build_user_message` SHALL 增加 `agent_id` 形参，按 agent_id 从 dossier 的 `research_dossier` 取角色侧重子集：

- `core_snapshot`（21 量化字段）SHALL 全员共享，不按角色裁剪
- 定性维度 SHALL 按角色分发（见 research-dossier spec「角色分发映射」requirement 的角色表）
- `call_agent` SHALL 透传 `agent_id` 给 `_build_user_message`
- DA / Synthesizer SHALL 走全量路径（`_call_da`/`_call_synthesizer` 不按 agent_id 分发，传 dossier 全量），与 agent 分发路径区分
- system prompt（`build_*_prompt`）SHALL NOT 改动——角色哲学已在静态 prompt 里，分发的是数据不是哲学

> 背景：[[design]] D3。当前 `_build_user_message(ticker, features, other_opinions)`（debate.py:69-116）对所有 agent 生成完全相同的 user message（同一份 features JSON），无 `agent_id` 入参——「角色分发」若只停在 prompt 层无法落地也无法验证。改 user message 层（不改 prompt 层），因 system prompt 是按 agent_id 分无参函数、调用处 `builder()` 也无参，改 prompt 层改动面大。

#### Scenario: _build_user_message 接受 agent_id
- **WHEN** `_build_user_message(ticker, features, other_opinions, agent_id)` 被调用
- **THEN** SHALL 按 `agent_id` 从 `features`（分层 dossier）的 `research_dossier` 取角色侧重子集拼进 user message

#### Scenario: core_snapshot 全员共享不被裁剪
- **WHEN** 构造任意 agent 的 user message
- **THEN** SHALL 含完整 `core_snapshot`（21 量化字段），不按 agent_id 裁剪

#### Scenario: call_agent 透传 agent_id
- **WHEN** `call_agent(agent_id, ticker, features, ...)` 调用 `_build_user_message`
- **THEN** SHALL 透传 `agent_id`，使 user message 按角色分发

#### Scenario: DA / Synthesizer 不按 agent_id 分发
- **WHEN** `_call_da` / `_call_synthesizer` 构造 user message
- **THEN** SHALL 传 dossier 全量（不分发），SHALL NOT 调按 agent_id 分发的 `_build_user_message` 路径（或以特殊 agent_id 标识全量）

#### Scenario: system prompt 不改动
- **WHEN** f3a 实现角色分发
- **THEN** `build_buffett_prompt` / `build_munger_prompt` / `build_duan_prompt` / `build_feng_liu_prompt` SHALL 保持无参签名不变，角色分发只在 user message 层

---

### Requirement: run_debate 入口改调 build_research_dossier
`run_debate` SHALL 把 L3 入口从 `assemble_council_features(ticker)` 改为 `build_research_dossier(ticker)`：

- `run_debate` SHALL 调 `build_research_dossier(ticker)` 取代 `assemble_council_features` 作为 L3 数据入口
- `assemble_council_features` SHALL 退居为 dossier 内部 `core_snapshot` 的来源（`build_research_dossier` 内部 `core_snapshot = core_snapshot or assemble_council_features(symbol)`）
- `call_agent`/`_call_da`/`_call_synthesizer` 的 `features` 形参语义 SHALL 从「扁平 21 字段」变为「分层 dossier」，形参名保持 `features` 不变（避免 cascade 改名）
- dossier 含 `core_snapshot` 的 `"error"`（insufficient_data）时 SHALL fail-fast（与现有 `debate.py:502-508` guard 同模式）

> 背景：[[design]] D4。明确 dossier 传入路径，避免「设计口号」。`assemble_council_features` 退居 dossier 内部来源，不删除（向后兼容）。

#### Scenario: run_debate 调 build_research_dossier
- **WHEN** `run_debate(ticker)` 被调用且 `features=None`
- **THEN** SHALL 调 `build_research_dossier(ticker)` 取分层 dossier，SHALL NOT 直接调 `assemble_council_features`

#### Scenario: assemble_council_features 退居 dossier 内部来源
- **WHEN** `build_research_dossier(symbol)` 内部需 core_snapshot
- **THEN** SHALL 调 `assemble_council_features(symbol)` 采集 core_snapshot（复用，不重复采）

#### Scenario: features 形参语义变为分层 dossier
- **WHEN** `call_agent` / `_call_da` / `_call_synthesizer` 接收 `features` 形参
- **THEN** 该形参 SHALL 是分层 dossier（含 `core_snapshot` + `research_dossier`），不再是扁平 21 字段；形参名保持 `features` 不变

#### Scenario: dossier 不足时 fail-fast
- **WHEN** `build_research_dossier` 返回的 `core_snapshot` 含 `"error"`
- **THEN** `run_debate` SHALL 抛 `ValueError`（insufficient_data），与现有 guard 同模式
