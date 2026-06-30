## ADDED Requirements

### Requirement: DA prompt 职责导向
`build_da_prompt()` SHALL 返回 DA（Devil's Advocate）的 system prompt，职责导向（非 Level 2 四层结构）：

- 职责：综合 R1+R2 找盲点和共识漏洞
- 工作守则：必须找**具体**漏洞（指向具体数据或事件），不允许泛泛之谈
- 输出格式：`AgentOutput` + `extra.blind_spots`（列表，每项含 `title` / `detail` / `which_agents_missed_it`）
- `signal` 固定 `"neutral"`，`conviction` 固定 0

#### Scenario: DA prompt 强调具体漏洞
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 包含"必须找具体漏洞"、"不允许泛泛之谈"相关内容

#### Scenario: DA prompt 定义 blind_spots 结构
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 列出 `extra.blind_spots` 的结构（`title` / `detail` / `which_agents_missed_it`）

### Requirement: Synthesizer prompt 职责导向
`build_synthesizer_prompt()` SHALL 返回 synthesizer 的 system prompt，职责导向（非 Level 2 四层结构）：

- 职责：综合 R1+R2+DA 产出结构化结论
- 工作守则：收敛结论反映加权多数，保留真实分歧点，列出待验证事项
- 输出格式：`SynthesizerOutput`（独立 dataclass，非 `AgentOutput`）
  - `final_signal`: "bullish" | "bearish" | "neutral" | "skip"
  - `conviction`: 0-100（加权平均）
  - `consensus_summary`: 一句话结论
  - `dissent_points`: 保留的分歧点列表 `[{topic, who_disagrees, their_reason}]`
  - `pending_verification`: 待验证事项列表

#### Scenario: Synthesizer prompt 定义输出结构
- **WHEN** `build_synthesizer_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 列出 `SynthesizerOutput` 的字段（`final_signal` / `conviction` / `consensus_summary` / `dissent_points` / `pending_verification`）

#### Scenario: Synthesizer prompt 强调保留分歧
- **WHEN** `build_synthesizer_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 包含"保留真实分歧点（不抹平）"相关内容

### Requirement: SynthesizerOutput dataclass
`schema.py` SHALL 新增 `SynthesizerOutput` dataclass，与 `AgentOutput` 平级：

- `final_signal`: str（枚举校验）
- `conviction`: int（0-100 范围校验）
- `consensus_summary`: str（非空校验）
- `dissent_points`: list[dict]（可为空）
- `pending_verification`: list[str]（可为空）

`SynthesizerOutput` SHALL 提供 `from_json` / `to_json` / `to_dict` 方法，校验逻辑与 `AgentOutput` 类似。

#### Scenario: SynthesizerOutput 校验 final_signal 枚举
- **WHEN** LLM 返回 `final_signal = "strong_buy"`
- **THEN** SHALL 抛出 ValidationError

#### Scenario: SynthesizerOutput 校验 consensus_summary 非空
- **WHEN** LLM 返回空字符串的 `consensus_summary`
- **THEN** SHALL 抛出 ValidationError

### Requirement: DA/synthesizer 不进 AGENT_REGISTRY
DA 和 synthesizer SHALL NOT 注册到 `AGENT_REGISTRY`（设计决策 3），`debate.py` 内独立调用。

#### Scenario: AGENT_REGISTRY 不含 DA/synthesizer
- **WHEN** `council/agents.py` 被加载
- **THEN** `AGENT_REGISTRY` SHALL 只包含 4 位投资大师，不含 `da` / `synthesizer`

### Requirement: debate.py 独立调用 DA/synthesizer
`debate.py` SHALL 新增私有函数 `_call_da(round1, round2, ticker, features)` 和 `_call_synthesizer(round1, round2, da_result, ticker, features)`，内部调用 `call_llm`（不走 `call_agent`，因为 prompt 构建和输出解析逻辑不同）。

#### Scenario: R3 调用 DA
- **WHEN** 全天团执行 Round 3
- **THEN** `debate.py` SHALL 调用 `_call_da`，传入 R1+R2 的 AgentOutput 列表，返回 DA 的 AgentOutput（含 `extra.blind_spots`）

#### Scenario: R4 调用 synthesizer
- **WHEN** 全天团执行 Round 4
- **THEN** `debate.py` SHALL 调用 `_call_synthesizer`，传入 R1+R2+R3 的输出，返回 `SynthesizerOutput`

#### Scenario: DA/synthesizer 使用正确的推理等级
- **WHEN** R3/R4 调用 LLM
- **THEN** R3 SHALL 使用 `reasoning_level="heavy"`，R4 SHALL 使用 `reasoning_level="moderate"`（AD-04）
