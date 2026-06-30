## MODIFIED Requirements

### Requirement: CouncilResult 结构
辩论编排器的最终输出 SHALL 是 CouncilResult 对象，采用显式命名字段（而非 rounds 列表）：

- `round1: list[AgentOutput]` — R1 各 agent 独立判断
- `round2: list[AgentOutput] | None` — R2 交叉质疑（单 agent=None）
- `round3: AgentOutput | None` — R3 DA 输出（单对象，不是列表）
- `round4: SynthesizerOutput | None` — R4 收敛共识（单对象，不是列表）
- `final_verdict: str` — 全天团取 `round4.final_signal`，单 agent fallback 取 `round1[0].signal`
- `key_variables: list[str]` — 从 R1/R2 所有 AgentOutput 的 `what_would_change_my_mind` 提取（`extract_key_variables` 函数）
- `consensus_summary: str | None` — 来自 round4
- `dissent_points: list[dict] | None` — 来自 round4
- `pending_verification: list[str] | None` — 来自 round4
- `debate_path: str | None` — 辩论记录 md 路径

全天团场景下：`round1` 含 4 个 AgentOutput（巴菲特/芒格/段永平/冯柳），`round2` 含 4 个，`round3` 是 DA 的 AgentOutput（含 `extra.blind_spots`），`round4` 是 SynthesizerOutput。

#### Scenario: 单 agent 完整流程（3a 已实现）
- **WHEN** 只注册巴菲特 1 个 agent 运行辩论
- **THEN** CouncilResult.round1 含 1 个 AgentOutput，round2/round3/round4 为 None，final_verdict 取 round1[0].signal

#### Scenario: 全天团完整流程（3b）
- **WHEN** 注册 4 个投资大师运行辩论
- **THEN** CouncilResult.round1 含 4 个 AgentOutput，round2 含 4 个，round3 是 DA 的 AgentOutput，round4 是 SynthesizerOutput，final_verdict 取 round4.final_signal

### Requirement: 辩论编排 4 轮串行
debate.py SHALL 实现 4 轮串行辩论编排：

- **Round 1（各自表态）**：所有 agent 并行调用 LLM，彼此隔离（不传他人论点），使用重度推理模型
- **Round 2（交叉质疑）**：所有 agent 并行调用 LLM，每个 agent 可见其他 agent 的 R1 AgentOutput JSON，使用重度推理模型；**单 agent 场景下跳过 LLM 调用**
- **Round 3（DA 挑刺）**：Devil's Advocate 单独调用 `_call_da`，可见 R1+R2 全部讨论，使用重度推理模型
- **Round 4（收敛共识）**：Synthesizer 单独调用 `_call_synthesizer`，可见 R1+R2+R3 全部讨论，使用中度推理模型

信息可见性 SHALL 由编排器控制（R1 彼此隔离 / R2 可见他人 / R3 全知 / R4 全知），不由 agent 自行决定。

#### Scenario: R1 信息隔离
- **WHEN** 执行 Round 1 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 为空列表

#### Scenario: R2 可见他人 R1 论点
- **WHEN** 执行 Round 2 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 包含 R1 中其他 agent 的 AgentOutput JSON（排除自己）

#### Scenario: R3 调用 DA
- **WHEN** 全天团执行 Round 3
- **THEN** debate.py SHALL 调用 `_call_da(round1, round2, ticker, features)`，传入 R1+R2 的 AgentOutput 列表，返回 DA 的 AgentOutput

#### Scenario: R4 调用 synthesizer
- **WHEN** 全天团执行 Round 4
- **THEN** debate.py SHALL 调用 `_call_synthesizer(round1, round2, da_result, ticker, features)`，传入 R1+R2+R3 的输出，返回 SynthesizerOutput

#### Scenario: final_verdict 取 R4 synthesizer
- **WHEN** 全天团辩论完成
- **THEN** CouncilResult.final_verdict SHALL 取 round4.final_signal（synthesizer 输出），不取 round1[0].signal

#### Scenario: 单 agent 下 R2 跳过 LLM 调用（3a 已实现）
- **WHEN** 只有 1 个 agent 执行 Round 2
- **THEN** 系统 SHALL 跳过 LLM 调用，CouncilResult.round2 为 None，不调用 LLM 浪费 token

#### Scenario: 单 agent 下 R3/R4 跳过（3a 已实现）
- **WHEN** 只有 1 个 agent 且无 DA/synthesizer
- **THEN** R3/R4 SHALL 返回 None，不报错，CouncilResult.round3 和 round4 为 None

### Requirement: Agent 注册表
debate.py SHALL 从 `council/agents.py` 的 `AGENT_REGISTRY` 读取 agent 列表，不硬编码 agent 名称。

- `AGENT_REGISTRY` 是字典结构：`{"agent_id": {"name": "显示名", "prompt_builder": "模块路径"}}`
- 3a 仅注册巴菲特（`"buffett"`）
- 3b 追加 3 位大师（`munger` / `duan` / `feng_liu`），DA/synthesizer 不注册（设计决策 3）；张坤留给后续迭代

#### Scenario: 3a 单 agent 注册（已实现）
- **WHEN** debate.py 启动辩论
- **THEN** SHALL 从 AGENT_REGISTRY 读取，仅发现巴菲特 1 个 agent，执行单 agent 流程

#### Scenario: 3b 全天团注册（4 位大师）
- **WHEN** AGENT_REGISTRY 注册 4 位投资大师
- **THEN** debate.py SHALL 自动按 agent 列表执行全天团辩论（R1×4 + R2×4），R3/R4 独立调用 DA/synthesizer（不从注册表读）
