## ADDED Requirements

### Requirement: R1 输出引用真实特征校验（反向校验）
质量门 SHALL 新增"R1 输出不得含 features 中不存在的凭空数字"反向校验维度，区分真实产出与空输入幻觉。

> 背景：deviation-analysis §1.3 铁证——600900（水电股）R1 输出"ROE 32%、毛利率 90%+、可口可乐"与 600519（茅台）逐字相同，证明 features 未注入时模型靠 system prompt 案例锚定编造。AD-09 的"辩论增量"gate 之前被这种空壳产出污染（6/7 watchlist 全 null）。
>
> **为何反向校验而非正向**：正向"key_metrics 能否在 features 找到来源"是模糊匹配 NLP 问题（`features.pe_ttm=26.42` vs key_metrics `"PE_TTM 26.42"` vs `"pe_ttm ≈ 26"`，需模糊匹配，难落地）。反向校验更可靠——**提取 key_metrics 里的数字，检查该数字是否在 features 任一字段值中出现；若 key_metrics 含具体数字但 features 对应字段为 None 或值不匹配，则判定为凭空编造**。

#### Scenario: R1 key_metrics 数字在 features 中有来源
- **WHEN** R1 AgentOutput 的 `key_metrics` 含 `"PE_TTM 26.42"`，且 `features.pe_ttm == 26.42`（或 `features` 中存在值为 26.42 的字段）
- **THEN** 质量门 SHALL 标记该数据点为"有来源"，通过校验

#### Scenario: R1 key_metrics 含 features 中不存在的凭空数字（幻觉拦截）
- **WHEN** R1 的 `key_metrics` 含 `"ROE 32%"`，但 `features.roe_3y` 为 None 或其值不为 32，且 features 中无任何字段值为 32
- **THEN** 质量门 SHALL 标记该轮 R1 为"幻觉产出/数据未注入"，不通过 AD-09 gate，触发根因排查而非继续加 agent

#### Scenario: 幻觉产出 + 环形引用同时出现
- **WHEN** R1 的 `key_metrics` 含凭空数字（如 features 无 32 却引"ROE 32%"），且 `core_thesis` 出现引用其他 agent 名字的元叙述（如 "munger 看好长期价值"）
- **THEN** 质量门 SHALL 标记为"幻觉产出 + R1 信息隔离被破坏"，因为 R1 无 other_opinions 输入，引用他人只能是模型编造

#### Scenario: 环形引用检测
- **WHEN** R1（other_opinions=None，本该隔离）的 `core_thesis` 中出现其他 agent_id 的名字（如 buffett 写 "munger 看好..."）
- **THEN** 质量门 SHALL 标记为"R1 信息隔离被破坏/幻觉引用"，不通过 AD-09 gate

#### Scenario: 校验模块可单元测试
- **WHEN** 实现反向校验逻辑
- **THEN** SHALL 将校验抽成可导入函数（如 `verify_r1_feature_grounding(output: AgentOutput, features: dict) -> tuple[bool, list[str]]`），而非仅内联在 CLI 脚本中——当前 `verify_quality_gate.py` 是 argparse+print 的 CLI 脚本，需重构为可导入模块后才能写单测
