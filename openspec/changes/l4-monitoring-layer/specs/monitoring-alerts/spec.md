## ADDED Requirements

### Requirement: 估值区间提醒（AD-02 双条件）
系统 SHALL 在估值低位 AND 催化出现时触发提醒（AD-02 硬约束）。

> **MVP 阶段退化声明**：MVP 阶段基本面催化事件数据源全部缺失，🟢 估值提醒暂停输出。`alert.py` 保留 AD-02 双条件框架代码，但该段落输出：`"⏸️ 估值提醒暂不可用——基本面催化事件数据源待补齐（event-fetcher TODO）"`。待 event-fetcher 补齐后启用。

#### Scenario: MVP 阶段估值提醒输出
- **WHEN** MVP 阶段运行 weekly_monitor
- **THEN** 周报中估值提醒段落输出 `"⏸️ 估值提醒暂不可用——基本面催化事件数据源待补齐（event-fetcher TODO）"`

#### Scenario: 估值低位 + 催化出现（完整态，待启用）
- **WHEN** `pe_percentile_5y < 20%` AND 基本面催化事件检测命中（event-fetcher 补齐后）
- **THEN** 触发提醒 `🟢 {ticker} {name} 估值低位 + 催化出现！建议关注`

#### Scenario: 估值低位但无催化（完整态，待启用）
- **WHEN** `pe_percentile_5y < 20%` 但催化事件检测未命中
- **THEN** 不触发提醒（AD-02：不允许只用估值低位）

#### Scenario: 催化出现但估值非低位（完整态，待启用）
- **WHEN** 催化事件检测命中但 `pe_percentile_5y >= 20%`
- **THEN** 不触发估值提醒（催化事件仍记录在催化检测报告中）

### Requirement: 风险事件扫描（硬规则）
系统 SHALL 用硬规则扫描风险事件。

#### Scenario: 质押率急升风险
- **WHEN** `pledge_ratio` 周环比上升 > 5ppt
- **THEN** 触发风险提醒 `🔴 {ticker} {name} 质押率急升，建议重新审视`

#### Scenario: TODO 风险事件标记
- **WHEN** 查看 `monitor/alert.py` 源码
- **THEN** 包含以下 TODO 注释：
  - `# TODO: event-fetcher - 减持风险（减持公告）`
  - `# TODO: event-fetcher - 业绩预告差风险（业绩预告）`
  - `# TODO: audit-opinion - 审计意见变更风险（数据源不可靠，待后续验证）`

### Requirement: key_variables 变化提醒（MVP 人工核对）
系统 SHALL 列出 L3 产出的 key_variables 供人工核对（不做自动检测）。

#### Scenario: key_variables 非空
- **WHEN** L3 产出 `key_variables` 非 null 且非空列表
- **THEN** 在周报中列出 `⚠️ {ticker} {name} 关键变量：{key_variables}`，并附加提示 `💡 结合近期动态核对是否发生变化`

#### Scenario: key_variables 为 null 或空
- **WHEN** L3 产出 `key_variables` 为 null 或空列表
- **THEN** 不触发 key_variable 提醒

#### Scenario: key_variables 自动检测 TODO
- **WHEN** 查看 `monitor/alert.py` 源码
- **THEN** 包含 TODO 注释：`# TODO: key_variable auto-detection - LLM 判断或规则映射`

### Requirement: 提醒不自动触发 L3
系统 SHALL 在估值提醒和风险扫描时不自动触发 L3 深研。

#### Scenario: 估值提醒不触发 L3
- **WHEN** 触发估值区间提醒
- **THEN** 只产出提醒文本，不调用 `council` 跑 L3 深研

#### Scenario: 风险提醒不触发 L3
- **WHEN** 触发风险事件提醒
- **THEN** 只产出提醒文本，不调用 `council` 跑 L3 深研

### Requirement: 提醒生成的错误处理
系统 SHALL 在提醒生成过程中处理数据缺失和上游失败的情况。

#### Scenario: L2 重跑失败影响提醒生成
- **WHEN** L2 重跑时 LLM API 错误
- **THEN** 该 ticker 的提醒文本中标注"L2 评估失败"，不生成基于 L2 verdict 的提醒（如 stage 变化提醒）

#### Scenario: 催化检测数据缺失
- **WHEN** 催化检测时 `pe_percentile_5y` 或 `pledge_ratio` 为 None
- **THEN** 跳过该催化信号的提醒生成，不报错

### Requirement: what_would_change_my_mind 适用范围
系统 SHALL 区分持仓股（已跑 L3）和新发现股（仅 L1/L2）的催化处理方式。

#### Scenario: 持仓股催化必须与 key_variables 相关
- **WHEN** candidate 的 `stage=l3` 且检测到催化事件
- **THEN** 提醒中标注"请核对催化事件是否与 key_variables 相关"（不自动判断相关性）

#### Scenario: 新发现股催化作为加分项
- **WHEN** candidate 的 `stage=l1` 或 `stage=l2` 且检测到催化事件
- **THEN** 提醒中标注"催化事件可作为进入 L3 深研的加分项"（不约束，因无 key_variables）
