## ADDED Requirements

### Requirement: 聚合 L1/L2/L3 三路产出
系统 SHALL 在 `watchlist/{date}.json` 中聚合 L1 candidates、L2 deep_dive 列表、L3 深研结果为统一视图。

#### Scenario: 读取 L1 产出文件
- **WHEN** 调用聚合函数
- **THEN** 从 `screen --output` 生成的 JSON 文件读取 L1 candidates 列表（不自己运行 L1 筛选）
- **AND** 如果文件不存在或过期（> 7 天），报错退出并提示"请先跑 `screen`"

#### Scenario: L1 单独聚合
- **WHEN** 只有 L1 candidates（无 L2/L3 结果）
- **THEN** 产出 `watchlist/{date}.json`，`candidates[]` 每项含 `ticker/name/stage=l1/l1_score/f_score/pe_ttm/pb/pledge_ratio`，`pe_percentile_5y=null`（stage=l1 不 fetch），`l2_verdict`/`l2_confidence`/`l3_verdict`/`l3_conviction`/`key_variables` 为 null

#### Scenario: L1+L2 聚合
- **WHEN** L1 candidates 存在且 ScoutCache 有对应 ticker 的 deep_dive 结果
- **THEN** 填充 `l2_verdict`/`l2_confidence`，`stage=l2`，L3 字段仍为 null

#### Scenario: L1+L2+L3 完整聚合
- **WHEN** L1 candidates 存在且 ScoutCache 有 L2 结果且 `watchlist/{date}_{ticker}.json` 存在
- **THEN** 填充 `l3_verdict`/`l3_conviction`/`key_variables`，`stage=l3`

#### Scenario: stage 字段计算逻辑
- **WHEN** 聚合单个 candidate
- **THEN** 按以下规则计算 `stage` 字段：
  - 如果有 L3 verdict（不管 verdict 是什么）→ `stage=l3`
  - 如果 L2 verdict 是 `deep_dive` → `stage=l2`
  - 如果 L2 verdict 是 `pass`/`reject`（评估过但不值得深研）→ `stage=l1`
  - 如果没有 L2 结果 → `stage=l1`

### Requirement: watchlist JSON 结构（§7 子集 + L2/L3 扩展字段）
系统 SHALL 产出 L4 聚合结构的 watchlist.json，包含 L1 基础字段的子集和 L2/L3 扩展字段。

> **与 §7 的差异**：§7 定义的 `roe_5y_avg` / `dividend_yield` / `safety_margin_pct` / `heat_rank` / `flags` / `red_flags` / `green_flags` / `rationale` 字段在 L4 聚合中**不填充**（L1/L2 未直接产出或需要额外 feature 组装）。L4 新增 `stage` / `l2_verdict` / `l2_confidence` / `l3_verdict` / `l3_conviction` / `key_variables` 字段。

#### Scenario: 顶层字段
- **WHEN** 产出 `watchlist/{date}.json`
- **THEN** 包含 `generated_at`（ISO 8601 时间戳）、`l1_candidates`（int，L1 candidates 列表长度）、`l2_shortlist`（int，candidates[] 中 `stage >= l2` 的数量）、`candidates`（list）

#### Scenario: candidate 字段
- **WHEN** 聚合单个 candidate
- **THEN** 包含 `ticker`/`name`/`stage`/`l1_score`/`f_score`/`pe_ttm`/`pe_percentile_5y`/`pb`/`pledge_ratio`/`l2_verdict`/`l2_confidence`/`l3_verdict`/`l3_conviction`/`key_variables`/`last_updated`

#### Scenario: pe_percentile_5y 字段来源
- **WHEN** `stage >= l2`（deep_dive 或已深研的 candidate）
- **THEN** 调用 `ValuationFetcher().fetch_with_fallback(ticker)` 补充 `pe_percentile_5y` 字段
- **AND** 如果 fetch 失败，`pe_percentile_5y: null`，不阻断聚合
- **WHEN** `stage = l1`（仅通过 L1 的 candidate）
- **THEN** `pe_percentile_5y: null`（L4 的估值关注聚焦已 deep_dive 或已深研的票，不为 change 5 前端的 200 只展示需求买单）

### Requirement: 按日归档
系统 SHALL 将每次聚合结果按日期归档为 `watchlist/{date}.json`。

#### Scenario: 同一天多次运行
- **WHEN** 同一天内多次运行聚合
- **THEN** 覆盖同日的 `watchlist/{date}.json`（幂等）

#### Scenario: 跨天运行
- **WHEN** 不同日期运行聚合
- **THEN** 保留历史快照（如 `watchlist/2026-06-23.json`、`watchlist/2026-06-30.json`）

### Requirement: L3 null 字段防御
系统 SHALL 对 L3 产出中的 null 字段做完整防御，不填默认值。

#### Scenario: L3 字段为 null
- **WHEN** `watchlist/{date}_{ticker}.json` 中 `conviction`/`consensus_summary`/`dissent_points`/`pending_verification` 为 null
- **THEN** 聚合时保留 null（`l3_conviction: null`），不填 0 或空字符串

#### Scenario: key_variables 为 null 或空
- **WHEN** L3 产出 `key_variables` 为 null 或空列表
- **THEN** 聚合时 `key_variables: null`，不触发 key_variable 提醒

#### Scenario: final_verdict 为 null
- **WHEN** L3 产出 `final_verdict` 为 null
- **THEN** 聚合时 `l3_verdict: "unknown"`，diff 视为无变化

### Requirement: watchlist 健康检查
系统 SHALL 检测 L3 产出完整性，标记不完整的记录。

#### Scenario: L3 产出不完整
- **WHEN** `watchlist/{date}_{ticker}.json` 存在但 `conviction`/`consensus_summary`/`dissent_points`/`pending_verification` 全部为 null
- **THEN** 聚合时标记 `l3_incomplete: true`

#### Scenario: L3 产出完整
- **WHEN** L3 产出所有字段均有值
- **THEN** 聚合时标记 `l3_incomplete: false` 或不包含该字段
