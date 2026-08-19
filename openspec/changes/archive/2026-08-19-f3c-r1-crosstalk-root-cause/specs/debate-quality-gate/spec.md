## MODIFIED Requirements

### Requirement: R1 输出引用真实特征校验（反向校验）
质量门 SHALL 新增"R1 输出不得含 features 中不存在的凭空数字"反向校验维度，区分真实产出与空输入幻觉。

> 背景：deviation-analysis §1.3 铁证——600900（水电股）R1 输出"ROE 32%、毛利率 90%+、可口可乐"与 600519（茅台）逐字相同，证明 features 未注入时模型靠 system prompt 案例锚定编造。AD-09 的"辩论增量"gate 之前被这种空壳产出污染（6/7 watchlist 全 null）。
>
> **为何反向校验而非正向**：正向"key_metrics 能否在 features 找到来源"是模糊匹配 NLP 问题。反向校验更可靠——**提取 key_metrics 里的数字，检查该数字是否在 features 任一字段值中出现；若 key_metrics 含具体数字但 features 对应字段为 None 或值不匹配，则判定为凭空编造**。
>
> **f3a 修订（2026-07-13）**：`feature_numbers` 收集改为**递归遍历 dict/list**（[[design]] D7）。f3 dossier 的 `research_dossier` 是嵌套 dict，定性维度数字（peer_avg_pe/consensus_eps/target_price 等）需递归展开才能进 `feature_numbers`，否则 R1 引用这些数字会被误判凭空。抽成共享辅助函数 `_collect_feature_numbers(features) -> list[float]`，`verify_r1_feature_grounding` 和 `verify_r2_new_evidence` 都调它。
>
> **f3c 修订（2026-07-16）**：本 requirement 从「仅在 `verify_mechanism_gate` 人工检查路径 print [WARNING]」升级为「`run_debate` 主流程 R1 后断路器」。f1 实现了检测器但只在 `verify_quality_gate.py:473-495` print 不 `return False`，`debate.py::run_debate` 主流程零调用——污染产出照样落盘（CLAUDE.md 悬案：7 份 watchlist 6 份 null 闭环根因）。f3c 把显性环形引用接成 **hard fail（阻断产出落盘）**，凭空数字/隐性串台保持 **soft warning（记入产出不阻断）**，与 f2/f3a 降级哲学一致。[[design]] D2。

#### Scenario: R1 key_metrics 数字在 features 中有来源
- **WHEN** R1 AgentOutput 的 `key_metrics` 含 `"PE_TTM 26.42"`，且 `features`（分层 dossier）中存在值为 26.42 的字段
- **THEN** 质量门 SHALL 标记该数据点为"有来源"，通过校验

#### Scenario: R1 key_metrics 含 features 中不存在的凭空数字（soft warning 不阻断）
- **WHEN** R1 的 `key_metrics` 含 `"ROE 32%"`，但 `features` 中无任何字段值为 32
- **THEN** 质量门 SHALL 标记该轮 R1 为"幻觉产出/数据未注入"**soft warning**（记入 watchlist JSON quality 字段，不阻断产出落盘），触发根因排查而非继续加 agent
- **AND** `run_debate` 主流程 SHALL 不因此中断（凭空数字有 f3a dossier 嵌套误判风险，保持 soft）

#### Scenario: 嵌套 dossier 数字递归收集（f3a）
- **WHEN** `features` 是分层 dossier（含 `research_dossier` 嵌套 dict，其中 `peer_avg_pe=15.3`）
- **AND** R1 的 `key_metrics` 含 `"行业平均 PE 15.3"`
- **THEN** `feature_numbers` SHALL 递归遍历 dossier 的 dict/list 收集到 15.3，该数据点被标记为"有来源"通过校验（**不误判凭空**）

#### Scenario: 显性环形引用 hard fail 阻断产出（f3c 接线）
- **WHEN** R1（other_opinions=None，本该隔离）的 `core_thesis` 中出现其他 agent_id 的名字（如 buffett 写 "munger 看好..."）
- **AND** `detect_circular_reference(agent)` 返回 `(False, issues)`
- **THEN** `run_debate` 主流程 SHALL 在 R1 后、R2 前**阻断**：不继续 R2/R3/R4（省 LLM 成本，AD-03），不产出"成功"watchlist JSON 落盘
- **AND** SHALL 按现有 error 路径处理（抛错或标记 `quality_gate_failed`，与 `insufficient_data` fail-fast 一致模式），记录阻断原因含命中的 agent 与串台引用

#### Scenario: 幻觉产出 + 环形引用同时出现按 hard fail 处理
- **WHEN** R1 的 `key_metrics` 含凭空数字（soft），且 `core_thesis` 出现引用其他 agent 名字的元叙述（如 "munger 看好长期价值"）（hard）
- **THEN** `run_debate` SHALL 按 hard fail（环形引用）阻断产出，R1 信息隔离被破坏是铁证无歧义

#### Scenario: 600009 真实完整产出通过断路器（回归基线）
- **WHEN** 对 600009.SH 真实完整产出（f1 已验证四 agent 全通过环形检测 + R1 接地）执行 f3c 断路器
- **THEN** `run_debate` SHALL 通过（不误杀真实产出）：无显性环形引用、key_metrics 有来源
- **AND** 若 600009 含隐性串台（不点名引用），SHALL 仅 soft warning 不阻断

#### Scenario: 环形引用检测模块可单元测试
- **WHEN** 实现反向校验 + 环形检测逻辑
- **THEN** SHALL 将校验抽成可导入函数（如 `verify_r1_feature_grounding(output: AgentOutput, features: dict) -> tuple[bool, list[str]]` + `detect_circular_reference(output: AgentOutput, agent_ids=None) -> tuple[bool, list[str]]`），数字收集抽成共享辅助函数 `_collect_feature_numbers(features: dict) -> list[float]` 递归遍历 dict/list
- **AND** `run_debate` SHALL 在 R1 后调用上述函数，显性环形命中走 hard fail 路径，凭空数字走 soft warning 路径

## ADDED Requirements

### Requirement: 隐性串台逃逸面采样评估（f3c 实验性）
质量门 SHALL 提供「隐性串台」采样评估能力，量化 `detect_circular_reference` 字符串匹配的逃逸面（模型不直呼 agent_id 即绕过）。

> 背景：`detect_circular_reference` 是字符串子串匹配（`aid in thesis`）。模型若写「另一位价值投资者也看好」「价值投资派达成共识」不出现 agent_id 字面即绕过检测。f3c 不升级语义检测（scope 控制，[[design]] D3），但在 D1 实验组2（features 缺失）采样真实产出统计隐性串台占比，决定是否需开独立 change 升级语义级检测。

#### Scenario: 隐性串台采样规则定义
- **WHEN** 采样 R1 `core_thesis` 判隐性串台
- **THEN** 采样规则 SHALL 前置定义：`core_thesis` 含「其他/另一位/共识/也看好/大家/都看好」等**不点名**引用他人观点的措辞，即标记为隐性串台候选
- **AND** SHALL 记录候选占比到实验报告，不阻断产出（实验性，soft）

#### Scenario: 隐性串台占比高触发语义检测升级建议
- **WHEN** D1 实验组2 采样的隐性串台占比 > 阈值（阈值待实验定）
- **THEN** 实验报告 SHALL 记录「需开独立 change 升级语义级串台检测（LLM-judge / embedding）」，本 change 不实施
