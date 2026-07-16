## ADDED Requirements

### Requirement: L2 快管线隔离约束（f3a 防污染）
f3a SHALL NOT 修改 `scout/input_assembly.py::assemble_snapshot`，L2 快管线不受 f3a 影响：

- `assemble_snapshot`（L2 扁平 21 字段，`input_assembly.py:242-246`）SHALL 保持不变
- capex_proxy（资本开支代理）SHALL 由 `research_dossier.py` 读已采的 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]`，SHALL NOT 在 `input_assembly.py` 加读取
- pledge（芒格代理治理）SHALL 由 dossier 读已采的 `data/cache/{ticker}/risk.json` 的 `pledge_ratio`，SHALL NOT 在 `input_assembly.py` 加读取
- 新建 3 fetcher（main_business/peers/research）SHALL 注册为新 dim（`data/cache/{ticker}/{dim}.json`），SHALL NOT 改现有 basic/valuation/financials/kline/risk 五个 dim 的采集或结构

> 背景：[[design]] D4。`assemble_snapshot` 是 L1→L2 交接点（`council/features.py:7` 和 `debate.py:22` 都 import），改它污染 L2 快管线（AD-03 成本闸门，200 只 batch）。f3a 的定性维度全部走 dossier 新层，L2 零影响。探索稿 §4.2 已明确此决策。

#### Scenario: assemble_snapshot 保持不变
- **WHEN** f3a 实现 dossier 层
- **THEN** `scout/input_assembly.py::assemble_snapshot` SHALL 保持现有签名和返回的 21 字段结构不变，L2 scout 管线零影响

#### Scenario: capex 由 dossier 读不进 input_assembly
- **WHEN** dossier 组装 capex_proxy
- **THEN** SHALL 从 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]` 读取，SHALL NOT 在 `input_assembly.py` 加 capex 读取逻辑

#### Scenario: pledge 由 dossier 读不进 input_assembly
- **WHEN** dossier 组装芒格的 pledge 代理
- **THEN** SHALL 从 `data/cache/{ticker}/risk.json` 的 `pledge_ratio` 读取，SHALL NOT 在 `input_assembly.py` 加 pledge 读取逻辑

#### Scenario: 新 dim 不污染现有五个 dim
- **WHEN** 新建 fetch_main_business / fetch_peers / fetch_research
- **THEN** SHALL 注册为新 dim（main_business/peers/research），SHALL NOT 改 basic/valuation/financials/kline/risk 五个现有 dim 的采集逻辑或返回结构
