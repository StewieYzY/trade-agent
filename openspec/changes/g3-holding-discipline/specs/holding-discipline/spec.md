## ADDED Requirements

### Requirement: G3 产品边界与依赖
系统 SHALL 将 G3 定义为持仓纪律副驾驶：将通过 G2 质量门的 InvestmentThesis 转译为用户确认的 HoldingContract，并在新信息出现时提供可解释的复核状态。系统 MUST NOT 连接券商、自动下单或替用户作出最终交易决定。G2 capability passed 前 MUST NOT 实现 G3 运行时代码。

#### Scenario: G2 未通过
- **WHEN** G2 InvestmentThesis capability status 尚未 passed
- **THEN** G3 只允许设计和 child change 规划，MUST NOT 激活 runtime HoldingContract 流程

#### Scenario: 任一输出涉及交易
- **WHEN** G3 判断某项仓位变化通过纪律检查
- **THEN** 系统 SHALL 明确要求用户最终确认，自动下单次数 MUST 为 0

### Requirement: HoldingContract 草稿、确认与生命周期
系统 SHALL 仅从 `quality_status=passed` 的 InvestmentThesis 生成 HoldingContract 草稿。用户 MUST 补充并确认成本价、当前仓位、目标仓位、最大仓位、可承受回撤、预期持有期、固定复核周期和卖出冷静期，合同才能从 draft 进入 active。规则修订 SHALL 生成新版本，旧版本 MUST 保留。

#### Scenario: 必填纪律参数缺失
- **WHEN** 任一必填仓位或复核参数缺失、格式非法或交叉约束不成立
- **THEN** 合同 MUST 保持 draft，并 SHALL 返回具体字段错误与修复提示

#### Scenario: 用户确认后激活
- **WHEN** InvestmentThesis passed、所有参数校验通过且用户确认合同摘要
- **THEN** 系统 SHALL 创建不可混淆的 contract id/version 并将状态设为 active

#### Scenario: 激活后修改规则
- **WHEN** 用户修改最大仓位、卖出条件或复核周期
- **THEN** 系统 SHALL 创建新 contract version，并 MUST NOT 覆盖旧版本及其历史状态

### Requirement: 候选池与持仓池分离
系统 SHALL 使用独立 `HoldingsRepository` 维护真实或模拟持仓。CandidateWatchlist 的加入、退出或排序变化 MUST NOT 自动创建、关闭或停止监控 HoldingContract。

#### Scenario: 持仓退出本期候选池
- **WHEN** active holding 不再出现在当前 G1 shortlist
- **THEN** HoldingsRepository SHALL 继续保留并监控该持仓，除非用户按合同生命周期显式关闭

#### Scenario: 候选进入 shortlist
- **WHEN** 某股票进入 G1 shortlist 但用户没有持仓或未激活合同
- **THEN** 系统 MUST NOT 自动将其加入 HoldingsRepository

### Requirement: 标准化 MonitorSignal
L4 SHALL 向 G3 提供标准化 MonitorSignal，至少包含 signal id、ticker、observed_at、signal type、severity、source、evidence reference、关联 key variable 和数据质量状态。MonitorSignal MUST NOT 直接包含自动交易动作或绕过 evaluator 修改 HoldingState。

#### Scenario: 监控发现关键变量变化
- **WHEN** L4 检测到财务、治理、估值或 Thesis key variable 变化
- **THEN** L4 SHALL 生成带来源和证据引用的 MonitorSignal，并交由 holding evaluator 判断合同规则

#### Scenario: 信号数据不足
- **WHEN** 监控数据过期、缺失或来源冲突
- **THEN** MonitorSignal SHALL 标记数据质量问题，evaluator MUST NOT 将其直接作为确定性 Red 证据

### Requirement: 确定性状态机与证据链
HoldingState SHALL 取 `green`、`yellow`、`red`、`blue` 或 `rebalance_review`。每次状态变化 MUST 映射到具体 contract version、规则、MonitorSignal/evidence 和评估时间；没有新证据时 MUST NOT 自动从 Green 跳到 Red。LLM 输出 MUST NOT 单独决定状态。

#### Scenario: 无重大变化
- **WHEN** Thesis 未破坏、没有待复核信号且仓位未超上限
- **THEN** evaluator SHALL 返回 `green` 并记录下一复核时间

#### Scenario: 无证据尝试进入 Red
- **WHEN** 没有命中任何 hard thesis-break rule 或可验证证据
- **THEN** evaluator MUST NOT 返回 `red`

#### Scenario: LLM 判断与规则不一致
- **WHEN** LLM 将某事件描述为 Thesis 破坏，但确定性规则和结构化证据未命中
- **THEN** 系统 SHALL 保持原状态或进入 `yellow` 人工复核，MUST NOT 直接进入 `red`

### Requirement: 价格波动与 Yellow 纪律
价格下跌 SHALL 只触发复核，MUST NOT 单独触发卖出或减仓授权。当价格跌幅命中合同阈值但 Thesis 未破坏时，状态 SHALL 为 `yellow`，系统 SHALL 显示需要复核且禁止仅因价格卖出。

#### Scenario: 下跌 20% 但 Thesis 完整
- **WHEN** 当前价格较合同基准下跌 20%、命中价格复核阈值，且关键变量和基本面未出现 Thesis-break evidence
- **THEN** 状态 SHALL 为 `yellow`，required action SHALL 为重跑 G2 或人工复核，卖出理由仅为价格时 MUST 被拦截

### Requirement: Thesis 破坏与 Red 纪律
当 `what_would_change_my_mind`、hard exit trigger 或核心关键变量的 thesis-break threshold 被可信证据命中时，状态 SHALL 为 `red` 并进入 exit review。系统 MUST NOT 用“长期主义”、持有时间或账面亏损掩盖已证伪 Thesis。

#### Scenario: 核心条件被证伪
- **WHEN** 新证据命中 active contract 的明确 Thesis-break rule
- **THEN** evaluator SHALL 返回 `red`、指出被证伪的 Thesis 条款和证据，并允许进入减仓/退出审查

#### Scenario: 用户以长期主义忽略 Red
- **WHEN** 状态为 `red` 且用户选择继续持有
- **THEN** 系统 SHALL 要求记录人工 override 理由与确认时间，并 MUST 保留 Red evidence，不得静默改回 Green

### Requirement: Blue 与 Rebalance Review 纪律
只有在价格或估值更有吸引力、Thesis 完整或增强、没有 Red trigger 且加仓后不超过最大仓位时，系统才能返回 `blue`。当单票或组合集中度超过合同上限时，系统 SHALL 返回 `rebalance_review`；该状态表示组合风险审查，不等于看空公司。

#### Scenario: 下跌且 Thesis 更强
- **WHEN** 价格下跌、估值更有吸引力、可信新证据强化 Thesis、当前仓位低于上限且没有 Red trigger
- **THEN** 状态 SHALL 为 `blue`，required action SHALL 为 add review，而非直接加仓指令

#### Scenario: 仓位因上涨超限
- **WHEN** Thesis 未破坏但当前仓位超过 `max_position_pct`
- **THEN** 状态 SHALL 为 `rebalance_review`，理由 SHALL 指向组合风险而非公司看空

### Requirement: 所有仓位变化经过 pre_trade_check
所有 `add`、`sell` 和 `trim` 意图 MUST 经过 `pre_trade_check`。输入 SHALL 包含 intended action、理由、目标仓位变化和证据；输出 SHALL 包含 `allowed`、`required_action`、解释、命中的合同规则、待验证项和人工确认要求。检查 MUST NOT 执行交易。

#### Scenario: 仅因价格或恐惧卖出
- **WHEN** intended action 为 sell/trim，理由只包含价格下跌或恐惧，且无 Thesis-break/组合风险证据
- **THEN** `allowed` MUST 为 false，required action SHALL 为 cooldown and review

#### Scenario: 加仓后超过上限
- **WHEN** intended action 为 add 且预计仓位将超过 `max_position_pct`
- **THEN** `allowed` MUST 为 false，required action SHALL 为 position review

#### Scenario: Thesis 破坏证据支持退出审查
- **WHEN** intended action 为 sell/trim 且存在已映射到合同规则的可信 Thesis-break evidence
- **THEN** `allowed` SHALL 为 true，required action SHALL 为 exit review，并仍要求用户最终确认

### Requirement: Append-only 状态与人工决策历史
系统 SHALL append-only 保存每次评估使用的 thesis version、contract version、signal ids、前后状态、规则命中、解释、人工确认和 override。历史记录 MUST 可用于重放且不得被后续合同版本覆盖。

#### Scenario: 状态发生变化
- **WHEN** active holding 从任一状态变为另一状态
- **THEN** 系统 SHALL 新增一条历史记录，包含可重放该判断的全部 identity 和 evidence reference

#### Scenario: 人工 override
- **WHEN** 用户选择与系统纪律状态不同的动作
- **THEN** 系统 SHALL 保留原判断并新增 override 记录，MUST NOT 改写历史证据

### Requirement: 历史回放、shadow mode 与可理解性 Gate
G3 在 capability passed 前 MUST 完成 Green、Yellow、Red、Blue、Rebalance Review 历史场景回放，并对 3-5 只真实或模拟持仓运行至少连续四周 shadow mode。用户 SHALL 能在一分钟内理解当前状态、触发原因、允许动作、禁止动作和待验证事项。

#### Scenario: 历史回放覆盖五类状态
- **WHEN** 执行预注册历史场景集
- **THEN** 每个场景 SHALL 得到预期状态，且每次变化均可定位到合同规则与证据

#### Scenario: 四周 shadow mode 完成
- **WHEN** 3-5 只持仓完成至少连续四周的周期性和事件触发评估
- **THEN** evidence bundle SHALL 记录所有状态、误报、漏报、人工 override 和 pre_trade_check 结果，自动交易次数 SHALL 为 0

#### Scenario: 一分钟内不可理解
- **WHEN** 用户无法在一分钟内说清状态、原因、允许/禁止动作和待验证项
- **THEN** 产品 Gate MUST 保持未通过，并 SHALL 优先修复解释与交互后重新验证

### Requirement: G3 umbrella 与 child change 治理
所有 G3 运行时代码 MUST 由引用 `g3-holding-discipline` 的独立 child change 实现。每个 child change MUST 只推进一个可独立验证的领域里程碑，不得偷带自动交易、完整组合优化或未通过 G2 的 Thesis 修复。Umbrella MUST 以真实场景和 shadow evidence 关闭。

#### Scenario: child change 越界
- **WHEN** G3 child change 包含券商接入、自动下单或与本里程碑无关的 G2 prompt 修复
- **THEN** 该 scope MUST 被拒绝并拆分

#### Scenario: G3 能力通过
- **WHEN** 所有必要 child changes 已归档，五类历史场景、四周 shadow mode、pre_trade_check、证据链和可理解性 Gate 全部通过
- **THEN** G3 SHALL 标记 capability passed；否则 SHALL 保留人工 checklist 或继续 child change 修复
