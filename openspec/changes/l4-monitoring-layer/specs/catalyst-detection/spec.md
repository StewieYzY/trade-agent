## ADDED Requirements

### Requirement: MVP 阶段基本面催化维度为空
系统 SHALL 在 MVP 阶段将基本面催化检测设为空（无可用数据源），仅检测风险信号。

> **P0 设计约束**：AD-02 要求估值提醒 = 估值低位 AND 基本面催化。§7.1 明确区分"估值低位"（状态）和"催化事件"（影响基本面的离散事件）。MVP 阶段基本面催化数据源全部缺失（财报/分红/政策/管理层/减持/业绩预告/审计意见），`pe_percentile_5y` 边际变化是估值状态变化而非基本面催化事件，不归入 `catalyst.py`（归入 `diff.py` 的 `valuation_low` 类型）。`pledge_ratio_spike` 是风险信号，只归风险扫描。

#### Scenario: MVP 阶段无基本面催化事件输出
- **WHEN** MVP 阶段运行 `detect_catalysts()`
- **THEN** `catalyst_report` 中基本面催化事件列表为空，估值提醒使用 placeholder `"⏸️ 估值提醒暂不可用——基本面催化事件数据源待补齐（event-fetcher TODO）"`

#### Scenario: 风险信号检测（非催化）
- **WHEN** `pledge_ratio` 周环比上升 > 5ppt
- **THEN** 标记为风险信号 `pledge_ratio_spike`（用于风险扫描提醒，不用于估值提醒的催化判断）

#### Scenario: 估值分位边际变化（归 diff，非催化）
- **WHEN** `pe_percentile_5y < 20%` 且上一快照 `pe_percentile_5y >= 20%`
- **THEN** 由 `diff.py` 标记为 `valuation_low` 类型（严重度 `significant`），不归入 `catalyst.py`

### Requirement: 催化事件 TODO 标记
系统 SHALL 在代码中显式标记未实现的催化事件类型。

#### Scenario: TODO 标记存在
- **WHEN** 查看 `monitor/catalyst.py` 源码
- **THEN** 包含以下 TODO 注释：
  - `# TODO: event-fetcher - 财报超预期（业绩预告/快报）`
  - `# TODO: event-fetcher - 分红提升（分红公告）`
  - `# TODO: event-fetcher + LLM - 行业政策（新闻/公告 + LLM 判断）`
  - `# TODO: event-fetcher + LLM - 管理层变动（高管变动 + LLM 判断）`
  - `# TODO: event-fetcher - 减持（减持公告）`
  - `# TODO: event-fetcher - 业绩预告差（业绩预告）`
  - `# TODO: audit-opinion - 审计意见变更（数据源不可靠，待后续验证）`

### Requirement: 催化判断原则（完整态，待启用）
系统 SHALL 遵循 §7.1 催化判断原则：必须影响基本面 + 必须有可验证数据支撑。

#### Scenario: 催化信号必须影响基本面（完整态，待启用）
- **WHEN** event-fetcher 补齐后检测催化事件
- **THEN** 只标记影响公司基本面的离散事件（财报超预期/分红提升/行业政策/管理层变动），不标记纯状态变化（估值分位）或风险信号（质押率）

### Requirement: LLM 催化判断预留接口
系统 SHALL 预留 LLM 催化判断接口（后续启用）。

#### Scenario: 预留函数存在
- **WHEN** 查看 `monitor/catalyst.py` 源码
- **THEN** 包含 `_llm_catalyst_check(ticker, features)` 函数，标注 `# TODO: activate when event-fetcher available`

#### Scenario: 预留函数未被调用
- **WHEN** weekly_monitor 运行催化检测
- **THEN** 不调用 `_llm_catalyst_check`（MVP 不做 LLM 催化判断）
