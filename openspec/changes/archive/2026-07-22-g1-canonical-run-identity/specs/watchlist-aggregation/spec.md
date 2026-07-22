## MODIFIED Requirements

### Requirement: 聚合 L1/L2/L3 三路产出
系统 SHALL 在 `watchlist/{date}.json` 中聚合 L1 candidates、L2 deep_dive 列表、L3 深研结果为统一视图。读取 L3 per-ticker 产出时 SHALL 用 canonical ticker 做**双向回退**文件名匹配（纯数字 ↔ 带后缀），MUST NOT 只匹配单一命名形式导致读到空壳而漏掉真数据。

> g1-canonical-run-identity 修改：原 requirement 的 `_read_l3_output`（`monitor/aggregation.py:131-134`）只匹配 `{date}_{ticker}.json` 与 `{date}_{ticker.replace('.', '_')}.json` 两种 pattern，**不含「去后缀纯数字」回退**。实地证据：`watchlist/` 下同一天同一只票存在 `2026-07-13_600009.json`（549B 空壳）与 `2026-07-13_600009.SH.json`（3091B 真数据），聚合时 `_read_l3_output(ticker="600009")` 只匹配到空壳 pattern、读不到真数据。根因是 `council/debate.py` 内部命名口径不一致——`_debate_path`（debate.py:236）用 `ticker.split(".")[0]` 纯数字写 debate md，但 `_write_council_output`（debate.py:890）用 `result.ticker`（带 `.SH`）写 watchlist JSON。本修改要求聚合层用 canonical ticker 双向回退（canonical 带后缀 → 纯数字回退；canonical 纯数字 → 带后缀回退），并要求 council 内部命名口径统一到 canonical ticker（run-identity SoT）。既有 19 个 watchlist 文件保留只读，不迁移不清空。

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

#### Scenario: L3 文件名 canonical ticker 双向回退
- **WHEN** `_read_l3_output` 查找 canonical ticker `600009.SH` 的 L3 产出文件
- **THEN** SHALL 按以下顺序回退匹配：`{date}_600009.SH.json` → `{date}_600009.json`（去后缀纯数字回退），优先返回含真实数据的文件（非空壳）；反之 canonical ticker `600009`（纯数字）SHALL 回退匹配 `{date}_600009.SH.json`（带后缀回退）。MUST NOT 只匹配单一命名形式

#### Scenario: 空壳与真数据并存时读真数据
- **WHEN** `watchlist/` 下同一天同一 canonical ticker 同时存在空壳文件（如 `2026-07-13_600009.json`，549B）与真数据文件（如 `2026-07-13_600009.SH.json`，3091B）
- **THEN** 聚合 SHALL 读取真数据文件（非空壳），通过内容完整性判断（`conviction`/`consensus_summary` 等字段非全 null）或文件大小启发式选择，MUST NOT 默认读空壳

#### Scenario: stage 字段计算逻辑
- **WHEN** 聚合单个 candidate
- **THEN** 按以下规则计算 `stage` 字段：
  - 如果有 L3 verdict（不管 verdict 是什么）→ `stage=l3`
  - 如果 L2 verdict 是 `deep_dive` → `stage=l2`
  - 如果 L2 verdict 是 `pass`/`reject`（评估过但不值得深研）→ `stage=l1`
  - 如果没有 L2 结果 → `stage=l1`
