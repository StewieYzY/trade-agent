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
