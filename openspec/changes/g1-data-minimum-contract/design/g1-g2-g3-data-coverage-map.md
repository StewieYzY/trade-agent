# G1/G2/G3 数据 Coverage Map（data-minimum-contract supporting artifact）

> 本文件是 `openspec/changes/g1-data-minimum-contract/` 的 supporting design artifact，属于该 change 的一部分（非游离文档），由 `design.md` 引用。
> 数据来源：`three-goal-capability-roadmap.md` §3/§4/§5、`g2-deep-investment-thesis`/`g3-holding-discipline` proposal、`research-dossier` spec、`holding-discipline` spec（G3，未落地代码）。
> 原则：G1 基础元数据可被 G2/G3 复用；G2/G3 业务字段只登记责任与依赖，不在本 child 实现；G2/G3 业务字段 MUST NOT 反向污染 G1 全市场批量路径（dossier 三维由 L3 `research_dossier.py` 独立路径采，绕开 BatchFetcher，已由 `staged-fetch-boundary` + `scout-agent` f3a 防污染 requirement 冻结）。

## 1. 字段→Goal 归属总表

| field | owner | source | downstream consumer | prerequisite Gate | blocking dependency | planned child |
|---|---|---|---|---|---|---|
| canonical ticker / run_id / profile_version / input_ticker_set_hash / as_of / provider status | **G1（横切，G2/G3 复用）** | run-identity SoT `data/lib/identity.py` | G1 输出/L2 payload/G2 dossier/G3 contract provenance | G1 | identity 不可审计→G1 Gate 视未通过 | `g1-canonical-run-identity`（已归档） |
| L1 量化五维（basic/financials/kline/valuation/risk）各 required 字段 | **G1** | 5 fetcher + BatchFetcher | L1 hard_gates/factor/anti_trap/heat_filter; L2 assemble_snapshot 21 key | G1 | 见字段矩阵 §2 | `g1-staged-fetch-boundary`（已归档） |
| `financials.cash_flow.CONSTRUCT_LONG_ASSET` | **G1 采（G2 消费）** | FinancialsFetcher（已采） | G1 DCF 诊断（已移出）; G2 dossier capex_proxy | G2 dossier 启用前 G1 已采 | dossier 读已采字段，零成本（`research-dossier` spec） | f3a `g2-deep-investment-thesis` child |
| `risk.pledge_ratio` | **G1 采（G2 消费）** | RiskFetcher 单源 | G1 H6/safety/A5/L2; G2 munger pledge 代理 | G2 dossier 启用前 G1 已采 | G2 dossier 从 `risk.json` 读，不新建 fetcher | f3a |
| `main_business` | **G2** | MainBusinessFetcher（新建，`stock_zygc_em`+`stock_zyjs_ths`） | G2 dossier（buffett/munger/duan 角色分发） | G2 Gate | L3 dossier 独立路径采，不进 G1 BatchFetcher | `g2-deep-investment-thesis` child（f3a 起步） |
| `peers` | **G2** | PeersFetcher（新建，`stock_board_industry_cons_em`，**依赖 G1 industry 字段**） | G2 dossier（buffett/munger/duan） | G2 Gate | 依赖 G1 `basic.industry`——industry 缺失则 peers 降级 | G2 child |
| `research` | **G2** | ResearchFetcher（新建，`stock_research_report_em`） | G2 dossier（duan/feng_liu/DA/synth） | G2 Gate | research 当市场预期不当事实（`research-dossier` spec prompt 分区） | G2 child |
| `capex_proxy` | **G2** | dossier 读已采 `CONSTRUCT_LONG_ASSET`（不新建 fetcher） | G2 dossier（buffett/feng_liu） | G2 Gate | 复用 G1 financials 采字段 | G2 child |
| `evidence` / `counter_evidence` / `key_variables` / `what_would_change_my_mind` | **G2** | L3 council 生成（非 fetcher） | InvestmentThesis 输出 | G2 Gate | G2 Gate 通过才有可信 Thesis | `g2-deep-investment-thesis` child |
| `InvestmentThesis` | **G2** | L3 synthesizer | G3 HoldingContract draft 输入 | G2 Gate（G3 前置） | G2 Gate 未通过→G3 不实现 runtime（AD-10） | `g2-deep-investment-thesis` |
| 用户成本价 / 持仓数量 / 仓位·最大仓位 / 回撤承受力 / 预期持有期 / 复核周期 / 卖出冷静期 | **G3** | 用户主动输入（非 fetcher） | G3 HoldingContract `holding/contract_service` | G3 Gate | G2 InvestmentThesis Gate 通过 | `g3-holding-discipline` child |
| `HoldingContract` | **G3** | `holding/contract_service.py`（draft→用户确认→生效） | G3 evaluator / pre_trade_check | G3 Gate | 依赖 G2 InvestmentThesis + 用户仓位参数 | G3 child |
| `MonitorSignal` | **G3** | L4 monitor（标准化）+ `holding/evaluator` | G3 状态机（Green/Yellow/Red/Blue/Rebalance） | G3 Gate | HoldingsRepository 是持仓真值源，不依赖 G1 candidates | G3 child |
| thesis-break 监控 / 人工 override | **G3** | `holding/history.py` + 用户确认 | G3 状态变化证据链 | G3 Gate | append-only 版本化 | G3 child |

## 2. G1/G2/G3 边界规则

1. **G1 基础元数据可被 G2/G3 复用**：canonical ticker / run_id / profile_version / input_ticker_set_hash / as_of / provenance / 缺失状态 SHALL 作 G2/G3 provenance 载体，G2/G3 MUST NOT 重新发明身份与 provenance 体系。
2. **G2/G3 业务字段 MUST NOT 反向污染 G1 全市场批量路径**：`main_business`/`peers`/`research` 由 L3 `research_dossier.py` 独立路径采集，绕开 BatchFetcher（`staged-fetch-boundary` + `scout-agent` f3a 防污染 requirement 已冻结）；G1 `screen_a_shares` 传 `G1_QUANT_DIMENSIONS` 5 维，MUST NOT 含 dossier 三维。
3. **G1 未通过前不以 G2/G3 开发掩盖 G1 数据问题**（AD-10）：在数据契约与关键 provider 能力未明确前，不 archive G1-4、不勾选 umbrella 4.1/4.2、不开 G2 runtime。
4. **roadmap 已明确 L1 不采 G2 数据**（`three-goal-capability-roadmap.md` §3.6 技术实现原则 + §4.3）：`main_business`/`peers`/`research` 属 G2/L3，G1 路径不采。
5. **G2 Gate 通过前只允许完善 G3 设计，不实现 G3 runtime**（AD-10）：`holding/` 领域、HoldingContract、MonitorSignal 接入属 G3 child，G2 未通过不得实现。
6. **复用而非重采**：G2 dossier 的 capex_proxy / munger pledge 代理复用 G1 已采字段（`CONSTRUCT_LONG_ASSET` / `risk.pledge_ratio`），零成本接入，不新建 fetcher（`research-dossier` spec）。

## 3. prerequisite Gate 依赖链

```text
G1（数据最小契约冻结 ← 本 child）
  ├─ G1-4 真实样本 Gate（依赖本契约字段矩阵 + 缺失状态机）
  │    └─ g1-4-data-source-resilience（repair child，修 industry_mapper 静默/risk 单源/valuation fallback/H2 误杀/heat 放行/F-Score 0）
  ├─ G1-5 全市场 performance/cost Gate
  └─ G1-6 Top 20 人工复核
        ↓ G1 Capability Gate 通过
G2（Investment Thesis）
  ├─ f3a L3 research dossier（main_business/peers/research/capex 复用 G1 字段）
  ├─ f3c R1 串台根因（G2 前置诊断）
  └─ G2 Gate（强单 Agent vs Council 信息增量盲评）
        ↓ G2 Gate 通过
G3（持仓纪律）
  └─ holding/ 领域（HoldingContract/MonitorSignal/state machine/pre_trade_check/shadow mode）
```

> **blocking dependency 关键点**：
> - G2 `peers` 依赖 G1 `basic.industry`——G1 industry 能力不解决（industry_mapper 静默空 dict），G2 peers 持续降级。这是本 data-minimum-contract child 冻结 G1 industry 缺失语义的直接下游价值。
> - G2 dossier 的 capex_proxy / munger pledge 依赖 G1 已采字段——G1 字段可用率 < 95% 直接拖垮 G2 dossier 质量。
> - G3 HoldingContract 依赖 G2 InvestmentThesis——G2 Gate 未通过，G3 contract_service 无可信输入。
