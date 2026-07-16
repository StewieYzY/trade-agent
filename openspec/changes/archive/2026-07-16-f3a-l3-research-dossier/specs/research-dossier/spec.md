## ADDED Requirements

### Requirement: 分层研究档案结构
`build_research_dossier(symbol: str, core_snapshot: dict | None = None) -> dict` SHALL 组装分层 dossier（L3 专用结构化研究档案层——把 L3 输入从 21 扁平量化字段升级为分层 dossier：公共底座 + 角色侧重，制造 R1 信息不对称；`core_snapshot` 全员共享、定性维度按角色分发，不污染 L2 快管线 `assemble_snapshot` 不变），返回结构：

```python
{
  "core_snapshot": {...21 量化字段...},        # 全员共享（来自 assemble_council_features）
  "research_dossier": {                         # 角色分发
    "main_business": {...分产品/行业/地区营收占比...},
    "peers": {...peer_avg_pe, 行业排名...},
    "capex_proxy": {...CONSTRUCT_LONG_ASSET...},
    "research": {...consensus_eps, target_price, buy_rating_pct, coverage_count...},
    "degraded_fields": [...缺失的降级维度名...],
  }
}
```

- `core_snapshot` 缺省时 SHALL 调 `assemble_council_features(symbol)` 采集（复用，不重复采）
- `core_snapshot` 含 `"error"`（insufficient_data）时 SHALL 向上传播 fail-fast（不组装 dossier）
- capex_proxy SHALL 由 dossier 读已采的 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]`（list，近3年），取 `[-1]` 最新期或多年均值；SHALL NOT 改 `scout/input_assembly.py`
- `degraded_fields` SHALL 记录所有降级（缺失但未 fail-fast）的维度名

> 背景：f3a 核心新概念（[[design]] D1/D4）。`assemble_snapshot`（L2 扁平 21 字段）保持不变，capex 由 dossier 读取不进 input_assembly（[[design]] D4，不污染 L2 快管线）。

#### Scenario: 完整 dossier 组装
- **WHEN** `build_research_dossier("600009.SH")` 被调用，且 core_snapshot + main_business + peers + research + capex 均成功采集
- **THEN** 返回的 dict SHALL 含 `core_snapshot`（21 字段）+ `research_dossier`（含 main_business/peers/capex_proxy/research 四维度）+ `degraded_fields`（空列表）

#### Scenario: core_snapshot 缺省时自动采集
- **WHEN** `build_research_dossier("600009.SH")` 被调用且 `core_snapshot=None`
- **THEN** SHALL 内部调 `assemble_council_features("600009.SH")` 采集 core_snapshot，不重复采

#### Scenario: core_snapshot 不足时 fail-fast 传播
- **WHEN** `assemble_council_features` 返回 `{"error": "insufficient_data", ...}`
- **THEN** `build_research_dossier` SHALL 向上传播 fail-fast（不组装 dossier，不吞错）

#### Scenario: capex_proxy 读已采字段不改 input_assembly
- **WHEN** dossier 组装 capex_proxy
- **THEN** SHALL 从 `data/cache/{ticker}/financials.json` 的 `["cash_flow"]["CONSTRUCT_LONG_ASSET"]` 读取，SHALL NOT 修改 `scout/input_assembly.py`

---

### Requirement: 分层 fail-fast
dossier 组装 SHALL 按维度重要性分层 fail-fast：

- `core_snapshot` + `main_business` 缺失 → **fail-fast**（核心，无这两样不深研，与 f1 `insufficient_data` 同模式）
- `peers` / `research` / `capex_proxy` 缺失 → **降级标注**（不阻断），记入 `research_dossier.degraded_fields`
- 降级维度对应的 agent 角色分发 SHALL 标 degraded 但仍跑（prompt 注明「你的 X 维度缺失，基于 core 判断」），不静默退化、不跳过 agent

> 背景：[[design]] D5。peers/research 覆盖率不稳（小票研报常返 0、industry 缺失致 peers 降级），全 fail-fast 会让很多票跑不了 L3；静默退化失角色不诚实（决策 (ii)，与 f2 L2 降级同哲学）。

#### Scenario: core_snapshot 缺失 fail-fast
- **WHEN** `core_snapshot` 含 `"error"` 或缺失
- **THEN** dossier 组装 SHALL fail-fast，不返回 partial dossier

#### Scenario: main_business 缺失 fail-fast
- **WHEN** `main_business` fetcher 返回 `{"__error__": True}` 或空
- **THEN** dossier 组装 SHALL fail-fast（core + main_business 是核心，无这两样不深研）

#### Scenario: peers 缺失降级不阻断
- **WHEN** `peers` fetcher 返回 `{"__error__": True}`（如 industry 字段缺失）
- **THEN** dossier SHALL 降级标注：`research_dossier.peers` 标 degraded，`degraded_fields` 含 `"peers"`，不阻断组装

#### Scenario: 降级维度对应 agent 标 degraded 仍跑
- **WHEN** peers 降级，巴菲特/芒格/段永平的角色侧重含 peers
- **THEN** 对应 agent 的 user message SHALL 注明「你的竞品维度缺失，基于 core 判断」，agent SHALL 仍跑（不跳过，不静默退化）

---

### Requirement: 3 新建 fetcher + 1 已采字段接入
f3a SHALL 新建 3 个 fetcher + 接入 1 个已采字段：

- `fetch_main_business.py`（新建，`stock_zygc_em` + `stock_zyjs_ths`）— 主营构成，分产品/行业/地区营收占比
- `fetch_peers.py`（新建，`stock_board_industry_cons_em`，依赖 industry 字段）— 竞品对比，peer_avg_pe/行业排名
- `fetch_research.py`（新建，`stock_research_report_em`）— 研报共识，consensus_eps/target_price/buy_rating_pct/coverage_count
- 资本开支代理（**已采接入，零成本**）— 由 dossier 读已采的 `CONSTRUCT_LONG_ASSET`，不新建 fetcher

每个新 fetcher SHALL：
- 继承 `data/fetchers/base.py::BaseFetcher`，设 `dim` 类属性 + 实现 `fetch()` + 设 `fallback_providers`
- 模块级 `_LazyTable`（`data/lib/snapshot.py:22-57`）包全市场表（peers 依赖 industry、research 若全市场表），intra-batch 复用防封禁
- 注册到 `data/lib/batch_fetcher.py:28-34` 的 `_DIM_FETCHERS` dict
- 注册 TTL 到 `data/cache/manager.py:24-32` 的 `_DIM_TTL`（main_business=QUARTERLY，peers/research 待定）
- `fetch_with_fallback` 全失败时返回 `{"ticker", "dim", "error": "all_providers_failed:{dim}", "__error__": True}`，不抛异常（由 dossier 分层 fail-fast 决定阻断与否）

> 背景：[[design]] D2 决策 (c)。f3b 补治理（`stock_ggcg_em`）/解禁（`stock_restricted_release_summary_em`）/cninfo 事件公告为后续独立 change，f3a 不做（scope 控制，避免「一次做 6 类 fetcher」膨胀）。

#### Scenario: 3 fetcher 继承 BaseFetcher
- **WHEN** 实现 fetch_main_business / fetch_peers / fetch_research
- **THEN** 每个 SHALL 继承 `BaseFetcher`，设 `dim` + 实现 `fetch()` + 设 `fallback_providers`

#### Scenario: fetcher 注册到 _DIM_FETCHERS 和 _DIM_TTL
- **WHEN** 新 fetcher 实现
- **THEN** SHALL 在 `batch_fetcher.py:_DIM_FETCHERS` 注册（如 `"main_business": MainBusinessFetcher`），在 `manager.py:_DIM_TTL` 注册 TTL 档位

#### Scenario: 全市场表 _LazyTable 复用防封禁
- **WHEN** fetch_peers / fetch_research 涉及全市场表
- **THEN** SHALL 用模块级 `_LazyTable` 包一层，intra-batch 只取一次（300s 失败冷却期内不重试）

#### Scenario: fetcher 全失败返回 __error__ 不抛
- **WHEN** 某新 fetcher 的主选 + 所有 fallback 都失败
- **THEN** `fetch_with_fallback` SHALL 返回 `{"__error__": True, ...}`，不抛异常，由 dossier 分层 fail-fast 决定阻断与否

#### Scenario: capex_proxy 不新建 fetcher
- **WHEN** dossier 组装 capex_proxy
- **THEN** SHALL 读已采的 `CONSTRUCT_LONG_ASSET`，SHALL NOT 新建 capex fetcher（零成本接入）

---

### Requirement: 角色分发映射
dossier 的定性维度 SHALL 按 agent_id 角色分发，`core_snapshot` 全员共享、定性维度按角色侧重子集：

| agent | 角色侧重维度 |
|---|---|
| buffett | main_business + peers + capex_proxy |
| munger | main_business + peers + pledge（代理治理） |
| duan | main_business + peers + research |
| feng_liu | research + capex_proxy |
| da / synthesizer | 全量（research_dossier 所有维度） |

- pledge（芒格代理治理）SHALL 从已采的 `data/cache/{ticker}/risk.json` 的 `pledge_ratio` 读取，不新建 fetcher
- DA / Synthesizer SHALL 走全量路径（仲裁要全知，不分发），与 agent 分发路径区分

> 背景：[[design]] D1/D2/D3。角色分发改 user message 层（`_build_user_message` 加 `agent_id`），不改 prompt 层（system prompt 静态，承载角色哲学不需重复）。芒格的「治理」、冯柳的「解禁/事件」用已有数据做代理（pledge / capex+研报），f3b 补真实 fetcher。

#### Scenario: core_snapshot 全员共享
- **WHEN** 任意 agent 的 user message 构造
- **THEN** SHALL 含完整 `core_snapshot`（21 量化字段），不按角色裁剪

#### Scenario: 定性维度按 agent_id 分发
- **WHEN** 构造 buffett 的 user message
- **THEN** SHALL 含 main_business + peers + capex_proxy 子集，SHALL NOT 含 research（段永平/冯柳维度）
- **AND** **WHEN** 构造 feng_liu 的 user message
- **THEN** SHALL 含 research + capex_proxy 子集，SHALL NOT 含 main_business/peers（巴菲特/芒格/段永平维度）

#### Scenario: 芒格 pledge 代理治理不新建 fetcher
- **WHEN** 构造 munger 的 user message
- **THEN** SHALL 从已采的 `data/cache/{ticker}/risk.json` 读 `pledge_ratio` 作治理代理，SHALL NOT 新建 fetch_governance.py

#### Scenario: DA / Synthesizer 走全量路径
- **WHEN** 构造 DA 或 Synthesizer 的 user message
- **THEN** SHALL 含 `research_dossier` 全部维度（不分发），区别于 agent 的角色分发路径

#### Scenario: 降级维度分发标注
- **WHEN** peers 降级，构造巴菲特 user message
- **THEN** SHALL 注明「你的竞品维度缺失，基于 core 判断」，不静默退化

---

### Requirement: prompt 物理分区
agent 的 user message SHALL 物理分区，研报不当事实：

- 「公司事实特征」段：core_snapshot + main_business + peers + capex_proxy
- 「市场共识/外部预期」段：research（单独成段，不混进公司事实段）
- 研报引用 SHALL 写明「市场预期认为……」，不当事实（像 Kimi 处理赔率：研究变量不是预测依据）

> 背景：[[design]] Risks（研报当事实风险）。研报共识（consensus_eps/target_price）是市场预期不是公司事实，混进事实段会误导。

#### Scenario: user message 物理分区
- **WHEN** 构造含 research 的 agent（段永平/冯柳）user message
- **THEN** SHALL 分「公司事实特征」段 + 「市场共识/外部预期」段，research 单独成段不混进公司事实段

#### Scenario: 研报引用写明市场预期
- **WHEN** user message 含研报数据
- **THEN** SHALL 标注「市场预期认为……」，不当事实陈述
