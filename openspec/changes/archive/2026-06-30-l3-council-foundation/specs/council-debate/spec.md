## ADDED Requirements

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

- **Round 1（各自表态）**：所有 agent 并行调用 LLM，彼此隔离（不传他人论点），使用重度推理模型
- **Round 2（交叉质疑）**：所有 agent 并行调用 LLM，每个 agent 可见其他 agent 的 R1 AgentOutput JSON，使用重度推理模型；**单 agent 场景下跳过 LLM 调用**
- **Round 3（DA 挑刺）**：Devil's Advocate 单独调用，可见 R1+R2 全部讨论，使用重度推理模型
- **Round 4（收敛共识）**：Synthesizer 单独调用，可见 R1+R2+R3 全部讨论，使用中度推理模型

信息可见性 SHALL 由编排器控制（R1 彼此隔离 / R2 可见他人 / R3 全知 / R4 全知），不由 agent 自行决定。

#### Scenario: R1 信息隔离
- **WHEN** 执行 Round 1 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 为空列表

#### Scenario: R2 可见他人 R1 论点
- **WHEN** 执行 Round 2 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 包含 R1 中其他 agent 的 AgentOutput JSON（排除自己）

#### Scenario: 单 agent 下 R2 跳过 LLM 调用
- **WHEN** 只有 1 个 agent 执行 Round 2
- **THEN** 系统 SHALL 跳过 LLM 调用，CouncilResult.rounds[1] 为 None，不调用 LLM 浪费 token

#### Scenario: 单 agent 下 R2 注入 mock AgentOutput（机制门验证）
- **WHEN** 单 agent 模式下启用 mock 注入验证机制门
- **THEN** debate.py SHALL 支持注入一份硬编码的 mock AgentOutput JSON（如"假想芒格"的 bullish 立场），验证巴菲特 agent 能消费他人结构化输出并产出修订立场（验证"能消费"，不要求输出必与 R1 不同）

#### Scenario: 单 agent 下 R3/R4 跳过
- **WHEN** 只有 1 个 agent 且无 DA/synthesizer 注册
- **THEN** R3/R4 SHALL 返回 None，不报错，CouncilResult 中对应轮次为 None

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
LLM 调用层 SHALL 按推理等级（`heavy` / `moderate`）映射到不同模型环境变量：

- `heavy`（R1-R3）→ `LLM_MODEL_HEAVY` 环境变量
- `moderate`（R4）→ `LLM_MODEL_MODERATE` 环境变量
- 复用 `LLM_API_KEY` / `LLM_API_BASE`（与 L2 共享）

不写死模型种类（AD-04），只标推理等级。

#### Scenario: 重度推理调用
- **WHEN** 辩论 Round 1 调用 LLM
- **THEN** SHALL 使用 `LLM_MODEL_HEAVY` 环境变量指定的模型

#### Scenario: 中度推理调用
- **WHEN** 辩论 Round 4 调用 LLM
- **THEN** SHALL 使用 `LLM_MODEL_MODERATE` 环境变量指定的模型

#### Scenario: 环境变量缺失
- **WHEN** `LLM_MODEL_HEAVY` 或 `LLM_MODEL_MODERATE` 未设置
- **THEN** SHALL 抛出 ValueError，fail-fast 不静默降级

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
