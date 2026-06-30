## ADDED Requirements

### Requirement: AgentOutput extra 字段透传
`AgentOutput` SHALL 支持 `extra: dict` 字段，用于透传 agent 特有字段（冯柳 5 字段、DA 盲点清单）。

- 基础 8 字段（signal / conviction / core_thesis / key_metrics / risks / what_would_change_my_mind / out_of_circle / historical_parallel）SHALL 严格校验（类型 + 枚举 + 非空）
- `extra` 中的字段 SHALL NOT 做类型/值校验（LLM 输出格式不稳定，强校验会误杀）
- `from_dict` SHALL 将未定义字段收集进 `extra`（不再丢弃）
- `to_dict` / `to_json` SHALL 自动包含 `extra` 中的字段

#### Scenario: 冯柳特有字段透传
- **WHEN** 冯柳 agent 输出 JSON 包含 `market_consensus` / `consensus_flaw` / `odds_assessment` / `is_reversible` / `catalyst`
- **THEN** `AgentOutput.from_dict` SHALL 将这些字段存入 `extra`，`to_dict` 返回的字典 SHALL 包含这些字段

#### Scenario: 基础字段校验不变
- **WHEN** agent 输出 JSON 的 `signal` 不在枚举内
- **THEN** SHALL 抛出 ValidationError，与 `extra` 字段无关

#### Scenario: extra 字段不做校验
- **WHEN** agent 输出 JSON 的 `extra` 中包含任意类型/值的字段
- **THEN** `from_dict` SHALL 接受，不抛出 ValidationError

### Requirement: extra 字段进入辩论记录
辩论记录 markdown 中的 JSON 块 SHALL 完整呈现 `extra` 字段，人类复盘时可看到 agent 特有字段。

#### Scenario: 冯柳特有字段出现在辩论记录
- **WHEN** 冯柳 agent 在 R1 输出包含 `market_consensus` 等特有字段
- **THEN** `debate/{ticker}/{date}.md` 中冯柳的 JSON 块 SHALL 包含这些字段

### Requirement: extra 字段 A2A 透传
Round 2 每个 agent 收到的 `other_opinions` SHALL 包含他人 R1 的完整 AgentOutput（含 `extra` 字段），其他 agent 可消费特有字段。

#### Scenario: R2 可见他人 extra 字段
- **WHEN** R2 分发 `other_opinions` 给巴菲特 agent
- **THEN** 巴菲特 agent 可见冯柳 R1 的 `market_consensus` / `consensus_flaw` 等字段，可针对性质疑
