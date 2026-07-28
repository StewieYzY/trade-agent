## Why

G1-4「300 样本规模预检」暴露的不是单点脚本 bug，而是 **G1 快筛闭环的数据能力与缺失语义从未冻结**：最近一次样本生成从 5533 只原始股票经 canonical 去重 + 行业分组后只剩 18 只，行业分布全部 `未分类`、`size_meets_minimum=false`、无真实 L1→L2 evidence bundle。根因之一是 `industry_mapper.build_industry_map()` 依赖东财行业接口、失败后静默返回空 dict，下游抽样把全市场归入单一「未分类」组每组取 10 只，`risk.py` 质押率仍是东财单一来源无 fallback。这说明：在「G1 真正需要哪些数据 / 每个数据缺失时系统该 error、skip、degraded 还是提示人工 / G1·G2·G3 数据边界如何划分」被显式冻结之前，无法靠继续加重试、并发或样本脚本逻辑掩盖数据源缺失——AD-10 串行 Gate 要求 G1 数据能力未明确前不 archive G1-4、不勾选 umbrella 4.1/4.2、不开 G2 runtime。本 change 只做 G1 数据最小契约的 design/spec，不碰 runtime。

## What Changes

- **冻结 G1 最小数据契约**：定义 G1 快筛闭环（全市场采集 → L1 量化筛选 → L2 成本闸门 → 候选结果）真正需要的最小字段集合，逐项核对真实消费者（hard gate / factor ranking / anti-trap / heat filter / L2 成本闸门 / G1 evidence 元数据），而非把现有 21 字段底座数量直接当作 G1 required 数量。
- **定义字段级缺失状态机**：`required_missing` / `degraded` / `manual_action_required` / `diagnostic_only` 四态，挂到字段/维度/结果三层，禁止把缺失静默压成「整只股票成功」或用默认值改写排名语义。
- **定义人工补充契约（只定义、不实现 UI）**：字段级 `manual_action_required` 的最小结构（canonical ticker / field / status / reason / attempted_sources / as_of_date / blocks / provenance_required），明确人工补充是否阻断 ranking、补充后是否需重跑该 ticker，不得绕过 G1 Gate。
- **建立 G1/G2/G3 coverage map（只登记依赖、不实现 G2/G3 字段）**：G1 基础元数据（canonical ticker / run identity / as_of / freshness / provenance / 缺失状态）可被 G2/G3 复用；G2 的 `main_business`/`peers`/`research`/`capex_proxy`/evidence/counter-evidence/`key_variables`/`what_would_change_my_mind`、G3 的成本价/持仓/`HoldingContract`/`MonitorSignal` 只登记责任与依赖，不在本 child 实现，且 MUST NOT 反向污染 G1 全市场批量路径。
- **保留与兼容原则**：不删除、不替换、不绕过现有 fetcher / provider fallback chain / cache·resume / BatchFetcher / 已有输出字段；新契约通过 status/provenance 标注现有能力而非隐藏失败；后续 provider 新增或修复只能开独立 implementation/repair child；不修改 G1-1/G1-2/G1-3 已冻结的 runtime contract。

## Capabilities

### New Capabilities

- `data-minimum-contract`: G1 数据最小契约——G1 最小闭环所需字段集合与真实消费者映射、字段/维度/结果三层缺失状态机（`required_missing`/`degraded`/`manual_action_required`/`diagnostic_only`）、字段级 status·missing reason·provenance 语义、人工补充契约、G1/G2/G3 coverage map 与边界规则、provider 保留与兼容要求。该 capability 只定义数据契约语义，不承载 runtime 实现。

### Modified Capabilities

无。本 child 不修改 `quantitative-screener`、`scout-agent`、`staged-fetch-boundary`、`run-identity`、`l1-numeric-correctness`、`screening-validation-sample` 等既有 spec 的 requirement。本 change 的产物是 design + 一份新增 capability spec（`data-minimum-contract`），不动 runtime；既有 requirement 的具体行为变更（若有）由后续 implementation/repair child 提交 delta specs。

## Impact

- **受影响产物**：`openspec/changes/g1-data-minimum-contract/`（proposal / design / specs / tasks），纯设计 spec，不动 `value-screener/` 源码。
- **不动 runtime**：现有 `data/fetchers/`、`data/lib/industry_mapper.py`、`data/fetchers/risk.py`、`data/batch_fetcher.py`、`data/cache/`、`screener/`、`scout/` 代码不修改。
- **AD 引用**（不重复搬运）：
  - **AD-10**（串行 Gate）：G1 数据能力未冻结前不 archive G1-4、不勾选 umbrella 4.1/4.2、不开 G2 runtime；本 design child 是 G1-4 解冻的前置。
  - **AD-02**（不择时/低热度作排除维度）：契约冻结不改变 hard gate / anti-trap / heat filter 阈值，只定义缺失语义。
  - **AD-03**（L2 成本闸门）：L2 required 字段集合明确后，字段可用率（G1 技术验收 Gate「关键字段可用率 ≥95%」）与降级/失败单独统计才有可计算口径。
- **依赖关系**：承接 G1-1/G1-2/G1-3（L1 数值口径 / 分层采集 / L2 full-result contract / canonical run identity 已冻结），承接 G1-4 实证证据（5533→18 / 全 `未分类` / 单一来源质押）。本 design child 通过后，再由用户决定下一步：开 `g1-4-data-source-resilience` implementation/repair child、按新契约调整 G1-4 harness 重跑真实 Gate、或对特定关键字段开窄的人工补充/来源 repair child。
- **不接触**：L3 council、G2/G3 runtime、前端、部署、Top 20 人工复核、300+ 样本重跑、H1-H8/factor/anti-trap/heat filter 阈值修改。
