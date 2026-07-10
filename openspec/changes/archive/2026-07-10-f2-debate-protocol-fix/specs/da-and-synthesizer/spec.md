## MODIFIED Requirements

### Requirement: DA prompt 职责导向
`build_da_prompt()` SHALL 返回 DA（Devil's Advocate）的 system prompt，职责导向（非 Level 2 四层结构）。DA 职责从「找盲点」升级为「仲裁」：

- 职责一：综合 R1+R2 找盲点和共识漏洞（原有）
- 职责二（新增）：**评估各 agent 引用数据点的真实性**——对每个 agent 的 key_metrics，回查 user message 中注入的 features 实际值，标注证据质量
- 工作守则：必须找**具体**漏洞（指向具体数据或事件），不允许泛泛之谈；证据质量评估必须基于 features 实际值比对，不允许纯主观
- 输出格式：`AgentOutput` + `extra.blind_spots`（列表，每项含 `title` / `detail` / `which_agents_missed_it`）+ `extra.evidence_quality_assessment`（新增，dict，key 为 agent_id，value 为 `"accurate"`/`"moderate"`/`"weak"`/`"inaccurate"`）+ `extra.recommendation`（新增，`"defer_to_<agent_id>_consensus"` 或 `"no_clear_winner"`）
- `signal` 固定 `"neutral"`，`conviction` 固定 0

> 背景：Kimi 辩论要点 4（第三方仲裁）。DA 已在 user message 注入 features（`_call_da` 现有实现）。改造要求 DA 对 agent 引用的数据点做事实回查，避免 LLM 评 LLM 文字游戏（[[design]] D3）。

#### Scenario: DA prompt 强调具体漏洞
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 包含"必须找具体漏洞"、"不允许泛泛之谈"相关内容

#### Scenario: DA prompt 定义 blind_spots 结构
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 列出 `extra.blind_spots` 的结构（`title` / `detail` / `which_agents_missed_it`）

#### Scenario: DA prompt 要求事实回查
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 包含要求「对每个 agent 的 key_metrics 回查 features 实际值，标注证据质量」的相关内容

#### Scenario: DA prompt 定义 evidence_quality_assessment 结构
- **WHEN** `build_da_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 列出 `extra.evidence_quality_assessment`（agent_id → accurate/moderate/weak/inaccurate）和 `extra.recommendation` 的结构

### Requirement: Synthesizer prompt 职责导向
`build_synthesizer_prompt()` SHALL 返回 synthesizer 的 system prompt，职责导向（非 Level 2 四层结构）：

- 职责：综合 R1+R2+DA 产出结构化结论，**条件依赖 DA 仲裁报告**（spec review #2 修订：DA 可能被跳过）——**DA ran 时**基于 DA 的 `evidence_quality_assessment` 和 `recommendation` 做最终判断，而非自行重新综合所有观点；**DA skipped 时**基于 R1（+R2 if ran）收敛，`consensus_summary` SHALL 标注 `da_skipped_reason`（取值：`"low_divergence"` / `"extreme_divergence"` / `"evidence_exhausted"` / `"runtime_degraded"`，spec review #3 补 extreme_divergence；reason 存 `CouncilResult` 由 `_call_synthesizer` 读取传入 prompt），此时 synthesizer 自行加权多数收敛但 conviction SHALL 受 `confidence_cap` 约束（降级时=40）
- 工作守则：收敛结论反映加权多数，保留真实分歧点（不抹平），列出待验证事项，structural 高分歧时标注「不可解决」
- 输出格式：`SynthesizerOutput`（独立 dataclass，非 `AgentOutput`）
  - `final_signal`: "bullish" | "bearish" | "neutral" | "skip"
  - `conviction`: 0-100（加权平均，应用 `confidence_adjustment`）
  - `consensus_summary`: 一句话结论
  - `dissent_points`: 保留的分歧点列表 `[{topic, who_disagrees, their_reason}]`
  - `pending_verification`: 待验证事项列表
  - `divergence_level` / `divergence_score` / `key_disagreements` / `confidence_adjustment` / `divergence_source` / `calibration_status`（新增分歧报告字段，见 council-debate spec）

#### Scenario: Synthesizer prompt 定义输出结构
- **WHEN** `build_synthesizer_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 列出 `SynthesizerOutput` 的字段（含新增分歧报告字段）

#### Scenario: Synthesizer prompt 强调基于 DA 仲裁
- **WHEN** `build_synthesizer_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 包含「基于 DA 的 evidence_quality_assessment 和 recommendation 做最终判断」相关内容

#### Scenario: Synthesizer prompt 强调保留分歧
- **WHEN** `build_synthesizer_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 包含"保留真实分歧点（不抹平）"相关内容

#### Scenario: Synthesizer prompt 要求分歧报告
- **WHEN** `build_synthesizer_prompt()` 被调用
- **THEN** 返回的 prompt SHALL 要求输出 `divergence_level` / `key_disagreements` / `confidence_adjustment` / `divergence_source` / `calibration_status` 字段

### Requirement: DA/synthesizer 不进 AGENT_REGISTRY
DA 和 synthesizer SHALL NOT 注册到 `AGENT_REGISTRY`（设计决策 3），`debate.py` 内独立调用。

#### Scenario: AGENT_REGISTRY 不含 DA/synthesizer
- **WHEN** `council/agents.py` 被加载
- **THEN** `AGENT_REGISTRY` SHALL 只包含 4 位投资大师，不含 `da` / `synthesizer`

### Requirement: debate.py 独立调用 DA/synthesizer
`debate.py` SHALL 新增私有函数 `_call_da(round1, round2, ticker, features)` 和 `_call_synthesizer(round1, round2, da_result, ticker, features)`，内部调用 `call_llm`（不走 `call_agent`，因为 prompt 构建和输出解析逻辑不同）。**spec review #2**：`_call_synthesizer` 的 `da_result` 参数类型为 `AgentOutput | None`（DA 可能被跳过），`round2` 同样可为 None（低分歧/extreme 跳 R2）。

#### Scenario: R3 调用 DA
- **WHEN** 全天团执行 Round 3（DA 未被跳过：medium/high 分歧且 R2 未全员 evidence_exhausted）
- **THEN** `debate.py` SHALL 调用 `_call_da`，传入 R1+R2 的 AgentOutput 列表 + features，返回 DA 的 AgentOutput（含 `extra.blind_spots` + `extra.evidence_quality_assessment`）

#### Scenario: R4 调用 synthesizer（DA ran）
- **WHEN** 全天团执行 Round 4 且 R3 已执行（DA ran）
- **THEN** `debate.py` SHALL 调用 `_call_synthesizer`，传入 R1+R2+R3 的输出（`da_result` 非空），返回 `SynthesizerOutput`（含分歧报告字段），synthesizer 基于 DA 仲裁报告收敛

#### Scenario: R4 调用 synthesizer（DA skipped，spec review #2）
- **WHEN** 全天团执行 Round 4 但 R3 被跳过（low/extreme 分流跳轮，或 R2 ≥3 agent 标 `evidence_exhausted`，或运行时降级跳轮）
- **THEN** `debate.py` SHALL 调用 `_call_synthesizer`，传入 R1（+R2 if ran，`da_result=None`）+ `da_skipped_reason`（从 `CouncilResult` 读），返回 `SynthesizerOutput`，`consensus_summary` SHALL 标注 `da_skipped_reason`（`"low_divergence"` / `"extreme_divergence"` / `"evidence_exhausted"` / `"runtime_degraded"`），synthesizer 基于 R1(+R2) 自行加权多数收敛，conviction 受 `confidence_cap` 约束

#### Scenario: DA/synthesizer 使用正确的推理等级
- **WHEN** R3/R4 调用 LLM
- **THEN** R3 SHALL 使用 `reasoning_level="heavy"`，R4 SHALL 使用 `reasoning_level="moderate"`（AD-04）
