## MODIFIED Requirements

### Requirement: 分层研究档案结构
`build_research_dossier(symbol: str, core_snapshot: dict | None = None) -> dict` SHALL
组装分层 dossier（L3 专用结构化研究档案层——把 L3 输入从 21 扁平量化字段升级为分层
dossier：公共底座 + 角色侧重，制造 R1 信息不对称；`core_snapshot` 全员共享、定性维度
按角色分发，不污染 L2 快管线 `assemble_snapshot` 不变），返回结构：

```python
{
  "core_snapshot": {...21 量化字段...},        # 全员共享（来自 assemble_council_features）
  "research_dossier": {                         # 角色分发
    "main_business": {...分产品/行业/地区营收占比...},
    "peers": {...peer_avg_pe, 行业排名...},
    "capex_proxy": {...CONSTRUCT_LONG_ASSET...},
    "research": {...consensus_eps, target_price, buy_rating_pct, coverage_count...},
    "degraded_fields": [...缺失的降级维度名...],
  },
  "fact_contract": {...},                       # 新增：字段级事实契约与追溯率
  "quality_status": "clean" | "degraded",       # 新增：dossier 证据质量状态
  "quality_reasons": [...],                      # 新增：降级/非 clean 原因
}
```

- `core_snapshot` 缺省时 SHALL 调 `assemble_council_features(symbol)` 采集（复用，不重复采）
- `core_snapshot` 含 `"error"`（insufficient_data）时 SHALL 向上传播 fail-fast（不组装 dossier）
- capex_proxy SHALL 由 dossier 读已采的 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]`（list，近3年），取 `[-1]` 最新期或多年均值；SHALL NOT 改 `scout/input_assembly.py`
- `degraded_fields` SHALL 记录所有降级（缺失但未 fail-fast）的维度名
- `fact_contract` SHALL 描述从角色 payload 提取的关键事实的来源、时间基准、新鲜度和
  降级状态，并输出可复核追溯率
- `quality_status` 和 `quality_reasons` SHALL 从 `fact_contract` 导出；高严重度事实
  不可追溯时 SHALL fail closed，不返回 clean dossier

> 背景：f3a 核心新概念（[[design]] D1/D4）。`assemble_snapshot`（L2 扁平 21 字段）保持
> 不变，capex 由 dossier 读取不进 input_assembly（[[design]] D4，不污染 L2 快管线）。

#### Scenario: 完整 dossier 组装
- **WHEN** `build_research_dossier("600009.SH")` 被调用，且 core_snapshot + main_business + peers + research + capex 均成功采集
- **THEN** 返回的 dict SHALL 含 `core_snapshot`（21 字段）+ `research_dossier`（含 main_business/peers/capex_proxy/research 四维度）+ `degraded_fields`（空列表）+ `fact_contract` + `quality_status` + `quality_reasons`

#### Scenario: core_snapshot 缺省时自动采集
- **WHEN** `build_research_dossier("600009.SH")` 被调用且 `core_snapshot=None`
- **THEN** SHALL 内部调 `assemble_council_features("600009.SH")` 采集 core_snapshot，不重复采

#### Scenario: core_snapshot 不足时 fail-fast 传播
- **WHEN** `assemble_council_features` 返回 `{"error": "insufficient_data", ...}`
- **THEN** `build_research_dossier` SHALL 向上传播 fail-fast（不组装 dossier，不吞错）

#### Scenario: capex_proxy 读已采字段不改 input_assembly
- **WHEN** dossier 组装 capex_proxy
- **THEN** SHALL 从 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]` 读取，SHALL NOT 修改 `scout/input_assembly.py`

#### Scenario: dossier 携带事实契约和质量状态
- **WHEN** `build_research_dossier` 成功返回
- **THEN** 顶层 SHALL 含 `fact_contract`、`quality_status` 和 `quality_reasons`，且
  `quality_status` 只能为 `clean` 或 `degraded`

---

### Requirement: 分层 fail-fast
dossier 组装 SHALL 按维度重要性分层 fail-fast：

- `core_snapshot` + `main_business` 缺失 → **fail-fast**（核心，无这两样不深研，与 f1 `insufficient_data` 同模式）
- 高严重度事实缺失来源、时间基准或来源与数字不匹配 → **fail-fast**（禁止无来源数字进入 clean dossier）
- `peers` / `research` / `capex_proxy` 缺失 → **降级标注**（不阻断），记入 `research_dossier.degraded_fields`
- 降级维度对应的 agent 角色分发 SHALL 标 degraded 但仍跑（prompt 注明「你的 X 维度缺失，基于 core 判断」），不静默退化、不跳过 agent

> 背景：[[design]] D5。peers/research 覆盖率不稳（小票研报常返 0、industry 缺失致
> peers 降级），全 fail-fast 会让很多票跑不了 L3；静默退化失角色不诚实（决策 (ii)，
> 与 f2 L2 降级同哲学）。

#### Scenario: core_snapshot 缺失 fail-fast
- **WHEN** `core_snapshot` 含 `"error"` 或缺失
- **THEN** dossier 组装 SHALL fail-fast，不返回 partial dossier

#### Scenario: main_business 缺失 fail-fast
- **WHEN** `main_business` fetcher 返回 `{"__error__": True}` 或空
- **THEN** dossier 组装 SHALL fail-fast（core + main_business 是核心，无这两样不深研）

#### Scenario: 高严重度数字无来源 fail-fast
- **WHEN** dossier 中出现影响核心判断的高严重度数字，但无法定位来源或时间基准
- **THEN** `build_research_dossier` SHALL fail closed，不返回 clean dossier

#### Scenario: peers 缺失降级不阻断
- **WHEN** `peers` fetcher 返回 `{"__error__": True}`（如 industry 字段缺失）
- **THEN** dossier SHALL 降级标注：`research_dossier.peers` 标 degraded，`degraded_fields` 含 `"peers"`，不阻断组装

#### Scenario: 降级维度对应 agent 标 degraded 仍跑
- **WHEN** peers 降级，巴菲特/芒格/段永平的角色侧重含 peers
- **THEN** 对应 agent 的 user message SHALL 注明「你的竞品维度缺失，基于 core 判断」，agent SHALL 仍跑（不跳过，不静默退化）
