## ADDED Requirements

### Requirement: 机制门（全天团 4 轮完整跑通）
全天团辩论 SHALL 满足机制门：

- R1×4 + R2×4 + R3×1 + R4×1 = 10 次 LLM 调用全部成功返回
- DA 输出 `extra.blind_spots` 非空且每项有 `title` / `detail` / `which_agents_missed_it`
- Synthesizer 输出 `dissent_points` 和 `pending_verification` 非空

#### Scenario: 全天团 10 次调用成功
- **WHEN** 全天团辩论执行
- **THEN** SHALL 完成 10 次 LLM 调用（R1×4 + R2×4 + R3×1 + R4×1），不报错

#### Scenario: DA blind_spots 结构合法
- **WHEN** DA 输出 AgentOutput
- **THEN** `extra.blind_spots` SHALL 非空，每项含 `title` / `detail` / `which_agents_missed_it`

#### Scenario: Synthesizer 输出关键字段非空
- **WHEN** Synthesizer 输出 SynthesizerOutput
- **THEN** `dissent_points` 和 `pending_verification` SHALL 非空

### Requirement: 质量门（辩论增量）
全天团辩论 SHALL 满足质量门（AD-09）：

- R1 core_thesis 差异：4 个 agent 的 `core_thesis` 两两相似度低（人工检查 1-2 只真实票）
- R2 真实修订：至少 2 个 agent 在 R2 调整了 `conviction`（±5 以上）或修改了 `core_thesis`（与 R1 不完全相同）
- DA 盲点覆盖：`blind_spots` 中至少 1 个盲点的 `which_agents_missed_it` 包含 ≥3 个 agent

#### Scenario: R1 core_thesis 有实质差异
- **WHEN** 4 个 agent 在 R1 输出 `core_thesis`
- **THEN** 人工检查 SHALL 确认两两相似度低（不是同质化表述）

#### Scenario: R2 有真实修订
- **WHEN** 全天团执行 R2
- **THEN** 至少 2 个 agent 的 R2 `conviction` 与 R1 相差 ≥5，或 `core_thesis` 与 R1 不完全相同

#### Scenario: DA 盲点覆盖真实共识盲区
- **WHEN** DA 输出 `blind_spots`
- **THEN** 至少 1 个盲点的 `which_agents_missed_it` 包含 ≥3 个 agent

### Requirement: 质量门验证 task
tasks.md SHALL 包含质量门验证 task：跑 1-2 只真实票（如 600519.SH），人工 + 自动检查辩论增量。

#### Scenario: 验证 task 跑真实票
- **WHEN** 执行质量门验证 task
- **THEN** SHALL 调用 `run_debate("600519.SH")`，人工检查 R1 core_thesis 差异、R2 修订、DA 盲点覆盖

#### Scenario: 质量门不通过则暂停加 agent
- **WHEN** 质量门某项不通过
- **THEN** SHALL 暂停加 agent，先调 prompt（AD-09 迭代原则），tasks 中定义回退路径

### Requirement: 成本验证
全天团辩论 SHALL 实测成本（10 次 LLM 调用：9 次重度推理 + 1 次中度推理），记录 token 消耗和费用，不做硬阈值约束：

#### Scenario: 实测成本记录
- **WHEN** 全天团辩论执行
- **THEN** SHALL 记录 10 次 LLM 调用的 token 消耗和费用，作为后续优化参考

#### Scenario: 缓存命中不重跑
- **WHEN** 同股同日重跑
- **THEN** SHALL 命中 `debate/{ticker}/{date}.md`，不调用 LLM（复用 3a `_check_cache`）

---

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
