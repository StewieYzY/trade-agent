## ADDED Requirements

### Requirement: R1 输出引用真实特征校验
质量门 SHALL 新增"R1 输出必须引用 features 中的具体数据点"校验维度，区分真实产出与空输入幻觉。

> 背景：deviation-analysis §1.3 铁证——600900（水电股）R1 输出"ROE 32%、毛利率 90%+、可口可乐"与 600519（茅台）逐字相同，证明 features 未注入时模型靠 system prompt 案例锚定编造。AD-09 的"辩论增量"gate 之前被这种空壳产出污染（6/7 watchlist 全 null）。本 requirement 在质量门层补一道"引用真实性"校验。

#### Scenario: R1 key_metrics 引用 features 中的真实数据
- **WHEN** 4 个 agent 的 R1 AgentOutput 的 `key_metrics` 字段
- **THEN** SHALL 至少有 1 个数据点能在传入的 features JSON 中找到对应来源（如 features.pe_ttm=26.42 → key_metrics 含 "PE_TTM 26.42"）

#### Scenario: 幻觉产出被质量门拦截
- **WHEN** R1 的 `key_metrics` 全部无法在 features 中找到来源（如 features 无 "ROE 32%" 但输出却引），且 `core_thesis` 出现引用其他 agent 名字的元叙述（如 "munger 看好长期价值"）
- **THEN** 质量门 SHALL 标记该轮 R1 为"幻觉产出/数据未注入"，不通过 AD-09 gate，触发根因排查而非继续加 agent

#### Scenario: 环形引用检测
- **WHEN** R1（other_opinions=None，本该隔离）的 `core_thesis` 中出现其他 agent_id 的名字（如 buffett 写 "munger 看好..."）
- **THEN** 质量门 SHALL 标记为"R1 信息隔离被破坏/幻觉引用"，因为 R1 无 other_opinions 输入，引用他人只能是模型编造
