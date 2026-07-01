## ADDED Requirements

### Requirement: R1 features 充分性门
Round 1 调用 LLM 前，编排器 SHALL 校验 `features` 数据充分性。当 features 为空、关键字段缺失或 `assemble_council_features` 返回 `{"error": "insufficient_data"}` 时，SHALL fail-fast 抛出错误并提示缺失字段，SHALL NOT 拿空/缺数据喂给 LLM 产出幻觉输出。

> 背景：deviation-analysis §1.2/1.3 实证发现，600519/600900 在 features 缺失时，模型靠 system prompt 案例锚定（茅台/可口可乐）编造同质化输出 + 环形引用他人 core_thesis，污染了 AD-09 gate。本 requirement 把"数据不足→喂空数据→幻觉"这条链路在 R1 入口截断。

#### Scenario: features 为空字典时 R1 fail-fast
- **WHEN** `assemble_council_features(ticker)` 返回空 dict 或仅含占位字段
- **THEN** R1 SHALL 抛出 `ValueError("insufficient_data")` 并列出缺失字段，不调用任何 LLM

#### Scenario: features 返回 insufficient_data 错误时 R1 fail-fast
- **WHEN** `assemble_council_features(ticker)` 返回 `{"error": "insufficient_data", "missing_fields": [...]}`
- **THEN** R1 SHALL 抛出 `ValueError`，提示用户先跑 `batch` 采集，不调用 LLM

#### Scenario: features 充分时 R1 正常调用
- **WHEN** `assemble_council_features(ticker)` 返回包含 name/industry/pe_ttm/roe 等关键字段的非空 dict
- **THEN** R1 SHALL 将 features JSON 注入 user message 并调用 LLM，产出引用真实数据点的 AgentOutput

#### Scenario: 600009 真实产出 vs 600519 幻觉产出的区分
- **WHEN** 对比 600009（features 充分，core_thesis 引用"PE_TTM 26.42、ROE 趋势上升"）与 600519（features 缺失，core_thesis 编"ROE 32%、可口可乐"）的 R1 输出
- **THEN** features 充分性门 SHALL 让前者通过、后者在 R1 入口即 fail-fast，杜绝幻觉产出进入后续轮次
