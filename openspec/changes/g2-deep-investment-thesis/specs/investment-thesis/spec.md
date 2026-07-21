## ADDED Requirements

### Requirement: 可信 Investment Thesis 能力边界
系统 SHALL 将 G2 定义为：针对指定股票生成可验证、可证伪、可持续跟踪的 Investment Thesis，回答“好不好、为什么、什么情况下改变”。Multi-Agent Council SHALL 仅作为候选实现形态，MUST NOT 作为能力完成的替代指标。

#### Scenario: 结构化辩论不等于能力通过
- **WHEN** Council 完成所有轮次但最终结果缺少可溯源证据、反证或改变条件
- **THEN** G2 capability status MUST 保持未通过

#### Scenario: 数据不足时诚实拒绝
- **WHEN** dossier 缺少支撑方向性结论的关键事实或股票超出能力圈
- **THEN** 系统 SHALL 标记 warning/failed 或拒绝判断，并 MUST NOT 强行输出高 conviction bullish/bearish

### Requirement: InvestmentThesis 稳定输出契约
G2 最终输出 SHALL 使用稳定 `InvestmentThesis` contract，至少包含 `thesis_id`、`ticker`、`run_id`、`core_thesis`、`evidence`、`counter_evidence`、`assumptions`、`risks`、`key_variables`、`what_would_change_my_mind`、`dissent`、`pending_verification` 和 `quality_status`。

每个 key variable SHALL 能表达当前值或状态、预期方向、warning threshold、thesis-break threshold、来源和 `as_of`。

#### Scenario: Thesis 可供下游跟踪
- **WHEN** G2 产生可发布结果
- **THEN** 输出 SHALL 包含足以让 G3/L4 识别关键变量变化和 Thesis 破坏条件的完整字段

#### Scenario: 质量状态不可丢失
- **WHEN** 运行存在数据降级、soft warning、Agent 失败或待验证事项
- **THEN** `quality_status` 和 `pending_verification` SHALL 显式反映该状态，下游 MUST NOT 接收到无标记 clean result

### Requirement: 事实接地与来源追溯
G2 发布结果中的高严重度凭空数字 MUST 为 0。至少 95% 的关键事实与数字 SHALL 可定位到 dossier 输入来源、报告期或 `as_of`；无法追溯的内容 MUST 标记为假设、推断或待验证，不得表述为已确认事实。

#### Scenario: 高严重度数字无来源
- **WHEN** Thesis 使用影响核心判断的营收、利润、现金流、估值或市场份额数字，但无法在输入或来源元数据中定位
- **THEN** quality gate MUST 失败，结果 MUST NOT 作为 passed Thesis 发布

#### Scenario: 推断与事实分离
- **WHEN** Agent 基于多个事实形成推断
- **THEN** 输出 SHALL 将支撑事实与推断结论分开，并保留事实来源

### Requirement: 完整运行审计链
canonical ticker、`run_id`、prompt version、dossier snapshot/version、模型配置、各轮输入输出、quality report 和最终 InvestmentThesis SHALL 100% 对应。持久化 MUST 防止不同 ticker 或不同 run 之间覆盖、复用或混合。

#### Scenario: 任一身份不一致
- **WHEN** dossier ticker、debate ticker、最终 ticker 或 run_id 任一不一致
- **THEN** 运行 MUST fail closed，结果 MUST NOT 写入成功缓存或发布接口

#### Scenario: 同日重复运行不覆盖
- **WHEN** 同一 ticker 在同一天执行两次 G2
- **THEN** 两次运行 SHALL 使用不同 `run_id` 并保留各自完整审计证据

### Requirement: 零显性与隐性串台
G2 的显性串台和隐性串台 MUST 均为 0。Agent 不得引用当前运行中不存在的角色发言、其他 ticker 的事实或前一运行的上下文；共享缓存与 prompt 组装 MUST 以当前 ticker/run 为边界。

#### Scenario: 引用其他股票事实
- **WHEN** 当前分析股票为 A，但任一输出使用只属于股票 B 的主营、财务或结论
- **THEN** quality gate MUST 失败并记录 crosstalk evidence

#### Scenario: R1 引用其他 Agent 当轮观点
- **WHEN** R1 设计要求信息隔离，但某 Agent 输出引用另一 Agent 的当轮观点或名字
- **THEN** 运行 SHALL 被判定为显性串台并 MUST NOT 发布 passed Thesis

### Requirement: 角色决策框架与轮次信息增量
角色差异 SHALL 来自版本化的决策框架，而非仅来自语言风格。R2 MUST 新增证据、修订观点或明确给出基于证据的坚持理由；DA MUST 发现遗漏、事实错误或证据不足，不能仅重复泛化风险。所有质量结论 SHALL 进入最终状态。

#### Scenario: R2 仅改写 R1
- **WHEN** R2 未新增证据、未修改判断且未给出坚持原判断的具体证据理由
- **THEN** R2 quality check SHALL 失败或产生可见 warning，且该轮 MUST NOT 被计为信息增量

#### Scenario: DA 只有泛化风险
- **WHEN** DA 仅输出适用于任何公司的宏观或通用风险，未定位遗漏、事实错误或证据不足
- **THEN** DA MUST NOT 被计为有效增量，最终质量状态 SHALL 反映该缺口

### Requirement: 成功缓存与降级状态
只有运行完整且主质量门通过的结果 SHALL 写入成功缓存。incomplete、warning、failed、DA skipped 或 runtime degraded 结果可以保留用于诊断，但 MUST 以独立状态持久化，消费者 MUST 能区分。

#### Scenario: 不完整结果不能命中成功缓存
- **WHEN** 前一运行在 R2、DA、Synthesizer 或最终 validation 前中断
- **THEN** 后续运行 MUST NOT 将该产物作为完整成功缓存复用

#### Scenario: soft warning 被持久化
- **WHEN** quality gate 返回非阻断 warning
- **THEN** warning SHALL 写入最终 InvestmentThesis 或关联 quality report，并在后续读取时保持可见

### Requirement: 强单 Agent 与 Council 公平对照
G2 Capability Gate SHALL 使用 8-10 只类型分散股票，在相同模型、相同 dossier snapshot、相同工具权限和可比预算下，对强单 Agent 与 Council 进行盲评。样本 SHALL 覆盖稳定白马、高估值成长、周期、困境反转、治理风险、预期差、数据不足和能力圈外中的主要类型。

#### Scenario: A/B 输入不一致
- **WHEN** 单 Agent 与 Council 使用不同 dossier、不同模型能力或未披露的额外工具
- **THEN** 该样本 MUST 从正式 Gate 统计中排除并重新运行

#### Scenario: 固定样本完成盲评
- **WHEN** 8-10 只预注册样本均产生两份匿名结果
- **THEN** 用户 SHALL 在不知道实现路径的情况下按同一 rubric 逐只评分并保留理由

### Requirement: Council 信息增量 Gate 与失败回退
Council SHALL 在至少 70% 样本中补充强单 Agent 未发现的实质风险、反证或关键变量；用户盲评 Council 更好的比例 SHALL 至少为 60%；Council 明显更差的比例 MUST 不高于 20%。若任一核心比例未通过，默认产品形态 MUST 回退为“强单 Agent + 独立 DA/事实检查器 + Synthesizer”。

#### Scenario: Council 通过相对价值 Gate
- **WHEN** 固定样本的事实质量与审计 Gate 均通过，且信息增量、用户盲评和负增量比例同时满足阈值
- **THEN** Council SHALL 被允许作为默认 G2 实现形态

#### Scenario: Council 未通过相对价值 Gate
- **WHEN** 任一核心比例未满足阈值
- **THEN** G2 MUST 采用强单 Agent + 独立 DA/事实检查器 + Synthesizer，且 MUST NOT 通过增加轮数或 Agent 数量规避回退

### Requirement: G2 依赖与 umbrella 治理
G2 正式能力验收 SHALL 在 G1 capability passed 后进行。所有运行时代码变更 MUST 由引用 `g2-deep-investment-thesis` 的独立 child change 实现，并说明推进的 Gate。G2 只有在真实 evidence bundle 通过后才能放行 G3 runtime。

#### Scenario: G1 未通过
- **WHEN** G1 capability status 尚未 passed
- **THEN** G2 可以继续设计和修复前置缺陷，但 MUST NOT 宣称已完成正式能力验收

#### Scenario: 放行 G3
- **WHEN** G2 的事实、来源、审计、串台、质量状态和 A/B Gate 全部通过，并已发布稳定 InvestmentThesis contract
- **THEN** G2 SHALL 标记 capability passed，并允许开始 G3 运行时代码 child changes
