## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: 辩论编排 4 轮串行
debate.py SHALL 实现 4 轮串行辩论编排：

- **Round 1（各自表态）**：所有 agent 并行调用 LLM，彼此隔离（不传他人论点），使用重度推理模型
- **分歧度分流（新增）**：R1 完成后计算分歧度，按 level 决定是否跳过 R2/R3
- **Round 2（交叉质疑）**：所有 agent 并行调用 LLM，每个 agent 可见其他 agent 的 R1 AgentOutput JSON，使用重度推理模型；单 agent 场景下跳过 LLM 调用；R2 prompt SHALL **encourage** 引用 R1 未充分覆盖的数据维度，如无则 **may** 声明 `evidence_exhausted`（**soft signal，非硬约束**，见上方「AgentOutput 新证据字段」requirement 的 scope 调整；spec review #3 修订：原「SHALL 要求」与 D2 降级不一致）
- **Round 3（DA 仲裁）**：Devil's Advocate 单独调用，可见 R1+R2 全部讨论 + 原始 features（做事实回查），使用重度推理模型；**DA skipped 条件**（spec review #2）：① 分流 `level == "low"` 或 `"extreme"` 跳 R2/R3；② R2 中 ≥3 agent 标 `evidence_exhausted` 跳 R3；③ 运行时降级（error rate ≥0.4）跳 R3。被跳时 `CouncilResult.round3 == None` + `CouncilResult.da_skipped_reason` 取四值之一（`"low_divergence"` / `"extreme_divergence"` / `"evidence_exhausted"` / `"runtime_degraded"`，spec review #3 补 extreme_divergence）。注：`da_skipped_reason` 存 `CouncilResult`（编排器内部状态，非 L3 输出 schema，不违反 f1 N1）
- **Round 4（收敛共识）**：Synthesizer 单独调用，可见 R1（+R2 if ran）+（DA 仲裁报告 if ran，否则 `da_skipped_reason`），使用中度推理模型，产出含分歧报告的 SynthesizerOutput（spec review #2：DA skipped 时 synthesizer 基于 R1(+R2) 自行加权收敛，`consensus_summary` 标注 `da_skipped_reason`，conviction 受 `confidence_cap` 约束）

信息可见性 SHALL 由编排器控制（R1 彼此隔离 / R2 可见他人 / R3 全知含 features / R4 全知——含 DA 仲裁报告 if ran，否则含 `da_skipped_reason`），不由 agent 自行决定。

#### Scenario: R1 信息隔离
- **WHEN** 执行 Round 1 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 为空列表

#### Scenario: R2 可见他人 R1 论点
- **WHEN** 执行 Round 2 时
- **THEN** 每个 agent 的 context 中 other_opinions SHALL 包含 R1 中其他 agent 的 AgentOutput JSON（排除自己）

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
