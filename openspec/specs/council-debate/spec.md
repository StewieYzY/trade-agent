# council-debate Specification

## Purpose
L3 天团辩论框架 —— 多投资哲学视角深度研判单只股票，通过 4 轮结构化辩论产出 CouncilResult。

## Requirements
### Requirement: AgentOutput JSON Schema
每个 agent 的输出 SHALL 是符合以下 schema 的 JSON 对象：

- `signal`: 枚举值 `"bullish"` | `"bearish"` | `"neutral"` | `"skip"`（必填）
- `conviction`: 整数 0-100，表示确信度（必填）
- `core_thesis`: 一句话核心理由（必填，非空字符串）
- `key_metrics`: 引用的具体数据点列表（必填，可为空数组）
- `risks`: 最大风险列表（必填，可为空数组）
- `what_would_change_my_mind`: 什么情况下会改变看法（必填，非空字符串）
- `out_of_circle`: 布尔值，是否在能力圈外（必填）
- `historical_parallel`: 类似历史案例（选填，可为 null）

LLM 输出 SHALL 通过 `response_format: {"type": "json_object"}` 强制 JSON 格式，解析后用 schema 校验。

#### Scenario: 巴菲特看多茅台
- **WHEN** agent 对贵州茅台（600519.SH）产出 AgentOutput
- **THEN** signal == "bullish"，core_thesis 非空，conviction 在 0-100 范围内

#### Scenario: 巴菲特看空长江电力
- **WHEN** agent 对长江电力（600900.SH）产出 AgentOutput
- **THEN** signal != "bullish"（允许 bearish/neutral/skip）

#### Scenario: LLM 输出非法 JSON
- **WHEN** LLM 返回的内容无法解析为合法 AgentOutput JSON
- **THEN** 系统 SHALL 抛出 ValidationError，不静默接受

#### Scenario: AgentOutput 必填字段缺失
- **WHEN** LLM 返回的 JSON 缺少 core_thesis 或 what_would_change_my_mind 等必填字段
- **THEN** 系统 SHALL 抛出 ValidationError，不静默填充默认值

#### Scenario: AgentOutput signal 枚举非法
- **WHEN** LLM 返回 signal = "strong_buy"（不在 bullish/bearish/neutral/skip 枚举内）
- **THEN** 系统 SHALL 抛出 ValidationError

---

### Requirement: CouncilResult 结构
辩论编排器的最终输出 SHALL 是 CouncilResult 对象，包含：

- `rounds`: 列表，按轮次顺序存放每轮结果（R1/R2/R3/R4）
- `final_verdict`: 最终信号（来自 R4 或 R1 的 fallback）
- `key_variables`: 从所有 AgentOutput 的 `what_would_change_my_mind` 提取的关键变量列表

3a 单 agent 场景下：`rounds[0]` 含 1 个 AgentOutput，`rounds[1]`/`rounds[2]`/`rounds[3]` 可为 None 或空列表。

#### Scenario: 单 agent 完整流程
- **WHEN** 只注册巴菲特 1 个 agent 运行辩论
- **THEN** CouncilResult.rounds[0] 含 1 个 AgentOutput，rounds[1-3] 为 None 或空列表，final_verdict 取 rounds[0][0].signal

#### Scenario: 全天团完整流程（3b）
- **WHEN** 注册 5+1 个 agent 运行辩论
- **THEN** CouncilResult.rounds[0] 含 5 个 AgentOutput，rounds[1] 含 5 个，rounds[2] 含 1 个 DA 输出，rounds[3] 含 1 个 synthesizer 输出

---

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

#### Scenario: DA skipped 时 CouncilResult 记录 da_skipped_reason（spec review #3 连带）
- **WHEN** DA 被跳过（low/extreme 分流、R2 evidence_exhausted≥3、运行时降级任一）
- **THEN** `CouncilResult` SHALL 在新增选填字段 `da_skipped_reason: str | None`（默认 None）填入对应取值（`"low_divergence"` / `"extreme_divergence"` / `"evidence_exhausted"` / `"runtime_degraded"`）；DA ran 时该字段为 None。`_call_synthesizer` 从该字段读 reason 传入 synthesizer prompt。**f1 N1 豁免说明**：`CouncilResult` 是编排器内部状态结构（非 L3 对外 JSON 输出 schema——f1 N1 保护的是 `AgentOutput`/`SynthesizerOutput` 的输出语义），加选填字段不触碰 N1；老代码构造 CouncilResult 不传该字段走默认 None，向后兼容。

---

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

---

### Requirement: A2A 传结构化 JSON
Agent 间传递的消息 SHALL 是 §AgentOutput JSON Schema 定义的结构化对象，SHALL NOT 传自由文本散文。

Round 2 每个 agent 收到的 other_opinions 是 AgentOutput JSON 列表（非文本摘要），Round 3 DA 收到的 full_discussion 是累积 JSON 列表。

#### Scenario: R2 接收结构化 JSON
- **WHEN** R2 分发 other_opinions 给 agent
- **THEN** 每个 AgentOutput SHALL 是完整的 JSON 对象（含 signal/conviction/core_thesis 等全部字段），不是文本摘要

#### Scenario: Token 预算
- **WHEN** R2 传入 4 个 AgentOutput JSON
- **THEN** 总 token 数 SHALL 显著低于传入 4 段 500 字散文（结构化 JSON 比自由文本紧凑 5-10 倍）

---

### Requirement: 辩论记录 append-only 持久化
辩论记录 SHALL 写入 `debate/{ticker}/{YYYY-MM-DD}.md`，按轮次顺序 append-only。

- 每轮结束后 SHALL 立即写入（不等 4 轮全完成），确保中途崩溃或超时时已有部分记录可复盘
- 文件格式：markdown，按 §6.4.1 结构（`## Round 1 · 各自表态` / `## Round 2 · 交叉质疑` / `## Round 3 · Devil's Advocate` / `## Round 4 · 收敛共识`）
- 每个 agent 的输出包含完整 AgentOutput JSON + 推理链

#### Scenario: 每轮立即写入
- **WHEN** Round 1 完成
- **THEN** `debate/{ticker}/{date}.md` 文件 SHALL 已存在且包含 `## Round 1 · 各自表态` 节，Round 2-4 节尚不存在

#### Scenario: 中途崩溃恢复
- **WHEN** Round 2 LLM 调用超时导致辩论中断
- **THEN** `debate/{ticker}/{date}.md` 文件 SHALL 已包含 Round 1 完整记录，可人工复盘

#### Scenario: 单 agent 占位
- **WHEN** 单 agent 模式下 R3/R4 跳过
- **THEN** markdown 文件中 R3/R4 节 SHALL 写入"（单 agent 模式，跳过）"占位文本

---

### Requirement: debate.py 是唯一状态持有者
debate.py SHALL 是唯一的状态持有者和消息路由。Agent SHALL 是纯函数（system_prompt + context → AgentOutput），agent 之间 SHALL NOT 直接通信。

- Agent 函数签名：`call_agent(name, system_prompt, context) -> AgentOutput`
- Agent SHALL NOT 持有跨轮状态
- Agent SHALL NOT 直接读写文件系统
- 所有消息收集、过滤、分发由 debate.py 编排器完成

#### Scenario: Agent 纯函数
- **WHEN** 对同一 agent 传入相同 system_prompt 和 context
- **THEN** 系统 SHALL 以 temperature=0 调用 LLM 以最大化输出一致性

#### Scenario: Agent 无副作用
- **WHEN** agent 函数执行完毕
- **THEN** SHALL 不修改任何全局状态、不写入文件系统、不修改辩论记录文件

---

### Requirement: Agent 注册表
debate.py SHALL 从 `council/agents.py` 的 `AGENT_REGISTRY` 读取 agent 列表，不硬编码 agent 名称。

- `AGENT_REGISTRY` 是字典结构：`{"agent_id": {"name": "显示名", "prompt_builder": "模块路径"}}`
- 3a 仅注册巴菲特（`"buffett"`）
- 3b 在此字典追加芒格/段永平/冯柳/张坤/DA/synthesizer，无需改编排逻辑

#### Scenario: 3a 单 agent 注册
- **WHEN** debate.py 启动辩论
- **THEN** SHALL 从 AGENT_REGISTRY 读取，仅发现巴菲特 1 个 agent，执行单 agent 流程

#### Scenario: 3b 全天团注册
- **WHEN** AGENT_REGISTRY 注册 5+1 个 agent
- **THEN** debate.py SHALL 自动按 agent 列表执行全天团辩论（R1×5 + R2×5 + R3×1 + R4×1），无需改编排代码

---

### Requirement: 校准测试
校准测试 SHALL 验证巴菲特 agent 对已知股票的判断是否符合设计预期：

- 巴菲特看多案例：`600519.SH`（贵州茅台）→ `signal == "bullish"`
- 巴菲特看空案例：`600900.SH`（长江电力）→ `signal != "bullish"`

校准测试 SHALL 调用 `assemble_snapshot` 取真实特征数据，不 mock。

#### Scenario: 校准全部通过
- **WHEN** 运行 `council --calibrate` 且所有用例立场一致
- **THEN** 输出 "Calibration PASSED" + 每个用例的 signal/conviction

#### Scenario: 校准失败
- **WHEN** 运行 `council --calibrate` 且某用例立场不一致（如茅台 signal != "bullish"）
- **THEN** 输出 "Calibration FAILED" + 失败用例详情（expected/actual signal），退出码非零

---

### Requirement: 辩论缓存命中
同股同日内重跑 SHALL 命中 `debate/{ticker}/{date}.md` 记录文件，不重跑 LLM。

- 命中条件：`debate/{ticker}/{date}.md` 文件存在且内容完整（至少含 Round 1 节）
- `--force` flag SHALL 跳过缓存，强制重跑 LLM
- 跨日（date 不同）自然重跑

#### Scenario: 同股同日重跑命中缓存
- **WHEN** `council --ticker 600519` 在同一天内第二次运行
- **THEN** 系统 SHALL 检测到 `debate/600519/{today}.md` 已存在，直接读取并返回 CouncilResult，不调用 LLM

#### Scenario: --force 跳过缓存
- **WHEN** `council --ticker 600519 --force` 运行
- **THEN** 系统 SHALL 忽略已有辩论记录文件，重新调用 LLM 并覆盖写入

#### Scenario: 跨日重跑
- **WHEN** `council --ticker 600519` 在不同日期运行
- **THEN** 系统 SHALL 创建新的 `debate/600519/{new_date}.md` 文件，完整重跑 LLM

---

### Requirement: LLM 调用按推理等级映射模型
LLM 调用层 SHALL 按推理等级（`heavy` / `moderate` / `light`）映射到不同模型环境变量，并 SHALL 采集每次调用的 token usage 返回给调用方，支撑 AD-03 成本实测。

- `heavy`（R1-R3）→ `LLM_MODEL_HEAVY` 环境变量
- `moderate`（R4）→ `LLM_MODEL_MODERATE` 环境变量
- `light`（L2 scout 等轻量调用）→ `LLM_MODEL` 环境变量（第三 tier，与 L2 共享轻量模型）
- 复用 `LLM_API_KEY` / `LLM_API_BASE`（与 L2 共享）
- **新增**：`call_llm` SHALL 返回 `(content: str, usage: dict)` 或等价结构，`usage` 含 `prompt_tokens` / `completion_tokens` / `total_tokens`，从 API 响应的 `usage` 字段提取（当前实现丢弃该字段，只返回 JSON 字符串）

不写死模型种类（AD-04），只标推理等级。

#### Scenario: 重度推理调用
- **WHEN** 辩论 Round 1 调用 LLM
- **THEN** SHALL 使用 `LLM_MODEL_HEAVY` 环境变量指定的模型

#### Scenario: 中度推理调用
- **WHEN** 辩论 Round 4 调用 LLM
- **THEN** SHALL 使用 `LLM_MODEL_MODERATE` 环境变量指定的模型

#### Scenario: 轻量推理调用
- **WHEN** L2 scout 等轻量调用使用 `light` 推理等级
- **THEN** SHALL 使用 `LLM_MODEL` 环境变量指定的模型

#### Scenario: 环境变量缺失
- **WHEN** `LLM_MODEL_HEAVY` 或 `LLM_MODEL_MODERATE` 未设置
- **THEN** SHALL 抛出 ValueError，fail-fast 不静默降级

#### Scenario: token usage 采集
- **WHEN** `call_llm` 完成一次 LLM 调用
- **THEN** SHALL 返回 content 与 usage（含 prompt_tokens/completion_tokens/total_tokens），L2 scout 与 L3 council 的调用方 SHALL 累加 usage 以实测 AD-03 成本（≈¥0.01/只），不再仅记录调用次数

#### Scenario: 调用点适配
- **WHEN** `call_llm` 签名从返回 `str` 改为返回 `(str, usage)`
- **THEN** L3 `debate.py::call_agent` / `_call_da` / `_call_synthesizer` 与 L2 `scout/batch.py` 的所有调用点 SHALL 适配新签名（解构 content 与 usage），不破坏现有 `AgentOutput.from_json` 解析逻辑

---

### Requirement: CLI council 子命令
CLI SHALL 提供 `council` 子命令：

- `council --ticker <TICKER>`：对指定股票跑单股深研，输出 AgentOutput JSON + 辩论记录 markdown
- `council --calibrate`：跑校准测试
- `--force`：跳过缓存强制重跑
- TICKER 格式：6 位数字（如 `600519`），自动补后缀（`.SH` / `.SZ`）

#### Scenario: 单股深研
- **WHEN** 运行 `council --ticker 600519`
- **THEN** 系统 SHALL 调用 assemble_snapshot 取特征 → 跑巴菲特 agent → 输出 AgentOutput JSON 到 stdout → 写入 debate/600519/{date}.md

#### Scenario: 数据不足
- **WHEN** 运行 `council --ticker 999999`（不存在或数据不足的股票）
- **THEN** 系统 SHALL 输出错误信息 "insufficient_data" + 缺失字段列表，退出码非零

#### Scenario: 校准测试
- **WHEN** 运行 `council --calibrate`
- **THEN** 系统 SHALL 跑巴菲特校准用例（茅台/长江电力），输出通过/失败结果

---

### Requirement: R1 features 充分性门
Round 1 调用 LLM 前，编排器 SHALL 校验 `features` 数据充分性。除现有 `critical_fields=["name","market_cap"]` 和整体缺失率 >50% 阈值外，SHALL 新增**财务字段最低组合**校验——L3 深研的命脉是财务维度，不是 name/market_cap。当财务字段组合不满足时，SHALL fail-fast，SHALL NOT 拿"有名字有市值但无财务数据"的 dict 喂给 LLM。

> 背景：deviation-analysis §1.2/1.3 实证发现 600519/600900 在 features 缺失时模型靠 system prompt 案例锚定编造。代码核查（`scout/input_assembly.py:338-354`）发现现有 guard 的实际漏洞：`critical_fields` 只有 name/market_cap，整体缺失率 >50% 才拦——**当 basic 维缓存命中（name/market_cap 有值）但 financials 维度过期/缺失时，缺失率可能才 ~40%，guard 放行**，模型拿到无财务数据的 dict 靠"可口可乐→茅台""ROE 32%"案例编造。本 requirement 在 guard 层补财务字段硬门槛，精确捕获这条幻觉触发路径。

**校验规则**（在 `assemble_council_features` / `assemble_snapshot` guard 层落地）：
- `critical_fields = ["name", "market_cap"]`（保留，basic 维硬门槛）
- `financials_floor = ["pe_ttm", "roe_3y", "net_margin"]`（新增，财务维硬门槛——L3 深研最低三件套，任一缺失则 features 不足以支撑质性判断）
- 触发 `insufficient_data` 的条件（满足任一即 fail-fast）：
  1. `missing_critical` 非空（name 或 market_cap 缺失）
  2. `financials_floor` 中**任一**字段为 None（财务三件套不齐）
  3. 整体 `missing_ratio > 0.5`（保留原阈值作为兜底）

#### Scenario: features 为空字典时 R1 fail-fast
- **WHEN** `assemble_council_features(ticker)` 返回空 dict 或仅含占位字段
- **THEN** R1 SHALL 抛出 `ValueError("insufficient_data")` 并列出缺失字段，不调用任何 LLM

#### Scenario: basic 命中但 financials 全空时 R1 fail-fast（核心漏洞修复）
- **WHEN** `assemble_council_features(ticker)` 返回 `{"name": "贵州茅台", "market_cap": 1.8e12, "pe_ttm": None, "roe_3y": None, "net_margin": None, ...}`（basic 维命中、financials 维过期/缺失）
- **THEN** R1 SHALL 抛出 `ValueError("insufficient_data")` 并列出 `missing_fields=["pe_ttm","roe_3y","net_margin"]`，不调用 LLM——这是 600519 幻觉的真正触发路径，原 guard 因缺失率 <50% 放行，新 guard 因 financials_floor 不齐而拦截

#### Scenario: features 返回 insufficient_data 错误时 R1 fail-fast
- **WHEN** `assemble_council_features(ticker)` 返回 `{"error": "insufficient_data", "missing_fields": [...]}`
- **THEN** `debate.py::run_debate` 已有的 `if "error" in features: raise ValueError` SHALL 消费新校验返回的 error，错误信息含缺失字段列表，提示用户先跑 `batch` 采集

#### Scenario: features 充分时 R1 正常调用
- **WHEN** `assemble_council_features(ticker)` 返回包含 name/market_cap 且 financials_floor（pe_ttm/roe_3y/net_margin）全非空的 dict
- **THEN** R1 SHALL 将 features JSON 注入 user message 并调用 LLM，产出引用真实数据点的 AgentOutput

#### Scenario: 600009 真实产出 vs 600519 幻觉产出的区分
- **WHEN** 对比 600009（features 充分，core_thesis 引用"PE_TTM 26.42、ROE 趋势上升"）与 600519（features 缺失，core_thesis 编"ROE 32%、可口可乐"）的 R1 输出
- **THEN** features 充分性门 SHALL 让前者通过、后者在 R1 入口即 fail-fast，杜绝幻觉产出进入后续轮次

---

### Requirement: 分歧度量化与分流
`debate.py` SHALL 在 Round 1 完成后、Round 2 开始前，对 R1 的 AgentOutput 列表计算分歧度，并基于分歧度决定后续轮次路径。分歧度量化函数 SHALL 返回 `{signal_consensus, conviction_std, level}`：

- `signal_consensus`：多数 signal 占比（如 4 个 bullish + 1 个 neutral → 0.8），作为**主信号**
- `conviction_std`：所有 agent conviction 的标准差，作为**辅助信号**（仅当 signal 一致时区分「都看多但确信度差异大」）
- `level`：`low` / `medium` / `high` / `extreme`，映射分流路径

分流路径 SHALL 按 `level` 决定：
- `low`（signal_consensus ≥ 0.8 且 conviction_std < 10）：跳 R2/R3，直接 R4 收敛
- `medium`（signal_consensus ≥ 0.6 或 conviction_std 10-20）：正常跑 R2/R3
- `high`（signal 无多数派，如 2:2 或 2:1:1）：正常跑 R2/R3，R4 输出 `divergence_level: "high"`
- `extreme`（signal 完全分散，如 1:1:1:1:1）：跳 R2/R3，直接 R4 输出 `final_signal: "neutral"`（无法收敛到多数派）+ `divergence_level: "extreme"` + 非空 `key_disagreements`——**不引入 `conflict` 枚举值**（spec review #1 调整：守 f1 N1「不改 L3 schema 语义」，`VALID_SIGNALS` 仍为 bullish/bearish/neutral/skip，分歧状态靠 `divergence_level`/`key_disagreements` 表达而非污染 `final_signal`）

> 背景：Kimi 辩论要点 1（分歧度作为元信号）+ 要点 2（分级响应）。当前 `run_debate` 固定跑完 4 轮，低分歧也跑 R2/R3 浪费 heavy-model token。以 signal 一致性为主、conviction std 为辅，因 conviction 是主观 0-100 分从未校准（[[design]] D1）。
>
> 阈值为保守默认值，**待 MVP 实测校准**，标注 `# TODO: calibrate divergence thresholds`。

#### Scenario: R1 全员一致跳过 R2/R3
- **WHEN** R1 的 4 个 agent signal 全为 "bullish"，且 conviction_std < 10
- **THEN** `level == "low"`，`run_debate` SHALL 跳过 R2 和 R3，直接调用 synthesizer 做 R4，CouncilResult.round2/round3 为 None

#### Scenario: R1 中度分歧正常跑全轮
- **WHEN** R1 的 4 个 agent signal 为 3 bullish + 1 neutral，conviction_std = 15
- **THEN** `level == "medium"`，`run_debate` SHALL 正常跑 R2/R3/R4

#### Scenario: R1 signal 无多数派标 high
- **WHEN** R1 的 4 个 agent signal 为 2 bullish + 2 bearish
- **THEN** `level == "high"`，`run_debate` SHALL 正常跑 R2/R3，R4 的 `divergence_level` SHALL 为 "high"

#### Scenario: R1 signal 完全分散跳轮输出极端分歧报告
- **WHEN** R1 的 4 个 agent signal 全不同（如 1 bullish + 1 bearish + 1 neutral + 1 skip）
- **THEN** `level == "extreme"`，`run_debate` SHALL 跳 R2/R3，R4 输出 `final_signal: "neutral"`（signal 完全分散无法收敛到多数派，最诚实的投资动作信号是「无法形成方向判断」）+ `divergence_level: "extreme"` + 非空 `key_disagreements`。**SHALL NOT** 输出 `final_signal: "conflict"`（该值不在 `VALID_SIGNALS`，会触发 `SynthesizerOutput.__post_init__` ValidationError）

#### Scenario: 单 agent 不触发分流
- **WHEN** 只有 1 个 agent 运行（单 agent 模式）
- **THEN** SHALL 跳过分流逻辑（沿用现有单 agent 跳过 R2/R3/R4 逻辑），不计算分歧度

### Requirement: AgentOutput 新证据字段（soft signal，f3 落地后升 hard）
`AgentOutput` schema SHALL 新增两个选填字段（向后兼容，老输出缺失不报错）：

- `new_evidence: list[str]`：本轮引用的数据点列表（R1 时可为空或全部，R2 时**鼓励**引用 R1 未充分覆盖的维度）
- `evidence_exhausted: bool`：是否已穷尽所有可用数据，默认 `false`

> 背景：Kimi 辩论要点 3（新数据证据防辩论退化复读）。**scope 调整（2026-07-10）**：原设计为「每轮强制新数据证据」，但实证显示 L3 输入仅 21 个纯量化字段，R2 无新维度可引（R1 已引用信息量最高的 PE/ROE/F-score/涨跌幅），硬约束触发「编造-校验-拦截」死循环或 evidence_exhausted 全员命中。根因属信息基底不足（f3-l3-research-dossier 范畴）。本 requirement 降为 soft：字段保留作 f3 的 enabling carrier（f3 补定性维度后，R2 确有新东西可引，质量门升回 hard gate），R2 prompt 改鼓励性引导而非「必须」。

#### Scenario: R2 输出含 new_evidence
- **WHEN** agent 在 R2 引用了 R1 未充分覆盖的数据维度
- **THEN** `new_evidence` SHALL 非空，列出该数据点

#### Scenario: R2 声明证据穷尽
- **WHEN** R2 所有相关数据已在 R1 被引用，agent 无法引用新维度
- **THEN** agent SHALL 输出 `evidence_exhausted: true`，`new_evidence` 可为空

#### Scenario: 老输出缺新字段不报错
- **WHEN** LLM 返回的 JSON 不含 `new_evidence` 或 `evidence_exhausted` 字段
- **THEN** `AgentOutput.from_json` SHALL 接受并填充默认值（`new_evidence=[]`, `evidence_exhausted=false`），不抛 ValidationError

### Requirement: R2 证据穷尽跳 R3
`run_debate` SHALL 在 R2 完成后聚合 `evidence_exhausted` 标记：当 ≥3 个 agent 标 `evidence_exhausted: true` 时，跳过 R3（DA 无新信息可仲裁），直接进入 R4。

#### Scenario: 多数 agent 证据穷尽跳 R3
- **WHEN** R2 中 ≥3 个 agent 标 `evidence_exhausted: true`
- **THEN** `run_debate` SHALL 跳过 R3 DA 调用，CouncilResult.round3 为 None，直接调用 synthesizer 做 R4

#### Scenario: 少数 agent 证据穷尽不跳
- **WHEN** R2 中 <3 个 agent 标 `evidence_exhausted: true`
- **THEN** `run_debate` SHALL 正常执行 R3 DA 调用

### Requirement: SynthesizerOutput 分歧报告增量字段
`SynthesizerOutput` SHALL 新增 6 个选填字段（向后兼容，缺失走默认值，不进 `__post_init__` 必填校验）：

- `divergence_level: str | None`：分歧等级（low/medium/high/extreme，来自分流）
- `divergence_score: float | None`：分歧度综合分
- `key_disagreements: list[dict]`：结构化分歧点列表，每项含 `{topic, bull_case, bear_case, strength}`
- `confidence_adjustment: float`：conviction 调整幅度（如 -0.2 表示下调 20%），默认 0.0
- `divergence_source: dict | None`：不确定性来源粗标 `{parameter, model, structural}`
- `calibration_status: str`：固定 `"uncalibrated"`（诚实声明 conviction 未校准）

> 背景：Kimi 辩论要点 5（产出是分歧报告不是共识）+ 校准要点 3（三层不确定性）+ 校准要点 1（校准>准确率）。与 deviation-analysis §2.5「schema 不改」调和——这些是**增量叠加**字段，`final_verdict`/`consensus_summary`/`dissent_points` 保留不变（[[design]] D4/D7/D8）。

#### Scenario: 高分歧输出分歧报告
- **WHEN** R1 `level == "high"` 且 synthesizer 执行 R4
- **THEN** `SynthesizerOutput` SHALL 含 `divergence_level: "high"`、`key_disagreements` 非空、`confidence_adjustment` 为负值

#### Scenario: 低分歧跳轮后分歧报告
- **WHEN** R1 `level == "low"` 跳 R2/R3 直接 R4
- **THEN** `SynthesizerOutput.divergence_level` SHALL 为 "low"，`key_disagreements` 可为空（无分歧）

#### Scenario: 老输出缺分歧字段不报错
- **WHEN** synthesizer 返回的 JSON 不含 `divergence_level` 等字段
- **THEN** `SynthesizerOutput.from_json` SHALL 接受并填充默认值（None / 0.0 / "uncalibrated"），不抛 ValidationError

### Requirement: structural 不确定性标注终止辩论
当分歧报告的 `divergence_source.structural == "high"`（存在不可预测外部因素：政策/黑天鹅/管理层个人行为）时，R4 SHALL 标注「不可解决」，SHALL NOT 强求收敛到单一结论。

#### Scenario: structural 高分歧标不可解决
- **WHEN** `divergence_source.structural == "high"`
- **THEN** `consensus_summary` SHALL 含「不可解决」标注，`final_signal` SHALL 倾向 `"neutral"`（不强行 bullish/bearish），`divergence_level` SHALL 为 `"high"` 或 `"extreme"` + 非空 `key_disagreements`。**SHALL NOT** 用 `final_signal: "conflict"`（spec review #1 调整：`conflict` 不在 `VALID_SIGNALS`，分歧状态靠 `divergence_level`/`key_disagreements` 表达）

### Requirement: L3 运行时降级（agent error rate）
`run_debate` SHALL 用 `asyncio.gather(*, return_exceptions=True)` 收集 R1 结果并统计 error rate = `failed_count / active_agent_count`（spec review #4 修订：**动态比**，不硬编码 agent 数——当前 4 位投资大师，未来张坤加入变 5 agent 时逻辑不变）。当 error rate ≥ 0.4 时触发运行时降级：跳 R2/R3，用幸存 R1 做 R4，`confidence_cap=40`，watchlist 标注 `council_degraded: true`。

> 区别于入口 fail-fast（f1 的 `financials_floor`，数据根本进不来）vs 运行时降级（数据进来了但 agent 跑崩了）。L3 单只深研入口保持 fail-fast 不变（[[design]] D5/D6）。

#### Scenario: agent error rate 高触发运行时降级
- **WHEN** R1 的 4 个 agent 中 ≥2 个抛异常（timeout/HTTP error），即 error rate = `2/4 = 0.5 ≥ 0.4`
- **THEN** `run_debate` SHALL 跳过 R2/R3，用幸存的 R1 做 R4，watchlist 输出 `council_degraded: true` + `degraded_reason: "high_agent_error_rate"`，conviction 上限 40

#### Scenario: 个别 agent 失败容忍继续
- **WHEN** R1 的 4 个 agent 中仅 1 个失败，即 error rate = `1/4 = 0.25 < 0.4`
- **THEN** `run_debate` SHALL 正常继续 R2/R3，R2 的 other_opinions 跳过失败 agent

> 注（spec review #4）：scenario 按当前 4 位投资大师写以符合 TDD「测试覆盖当前实现」；张坤（第 5 agent）加入后补 5-agent scenario，动态比逻辑不变（5 agent 阈值 = ≥2 失败）。
