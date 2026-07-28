## Context

G1-4「300 样本规模预检」暴露的不是单点脚本 bug，而是 **G1 快筛闭环的数据能力与缺失语义从未冻结**：最近一次样本生成从 5533 只原始股票经 canonical 去重 + 行业分组后只剩 18 只，行业分布全部 `未分类`、`size_meets_minimum=false`、无真实 L1→L2 evidence bundle。根因之一是 `industry_mapper.build_industry_map()` 依赖东财行业接口、失败后**静默返回空 dict**（`industry_mapper.py:104-107`），下游抽样把全市场归入单一「未分类」组每组取 10 只；`risk.py` 质押率仍是东财单一来源无 fallback（`risk.py:99` `fallback_providers=[]`）。

更深一层的问题是：**同一字段缺失，在 L1 三道漏斗里被给了三种相反语义**——`risk.pledge_ratio=None` 时，`factor_scores` safety_margin 返 0 分（惩罚，`factor_scores.py:231-232`）、`anti_trap` A5 不扣分（不惩罚，`anti_trap.py:156-157`）、`hard_gates` H6 放行（不惩罚，`hard_gates.py:68-71`）。这意味着「字段缺失如何影响排名」从未被当作契约冻结过，每处 `.get(key)` 各自决定。且 `pledge_ratio` 的 `None` 既可能是 provider 失败、也可能是「查无质押记录」（`risk.py:37-38` `rows.empty→return None`），两种成因被混为一谈。

**当前仓库状态（实证，代码扫描得出）**：

- **L1 消费的 5 个量化维度**（`main.py:30` `G1_QUANT_DIMENSIONS`，已由 `g1-staged-fetch-boundary` 冻结）：`basic` / `financials` / `kline` / `valuation` / `risk`。dossier 三维（`main_business`/`peers`/`research`）属 G2/L3，L1 不采（`batch_fetcher.py:31-41` 注册 8 维，`dimensions=None` 兜底采全 8 维，但 L1 显式传 5 维绕过）。
- **L2 消费 21 key feature snapshot**（`scout/input_assembly.py:242` `assemble_snapshot`），其中 10 个直读、10 个派生、1 个 ticker；`critical_fields = ["name","market_cap"]`（缺失→fail-fast）、`financials_floor = ["pe_ttm","roe_3y","net_margin"]`（缺失→L2 degraded/L3 fail-fast，`input_assembly.py:350-408`）。
- **canonical run identity 已冻结**（`g1-canonical-run-identity` + repair）：`canonical_ticker()` SoT、`run_id`（UUID4 execution identity）、`profile_version`、`input_ticker_set_hash`、as_of/采集日。本 design 复用其作 provenance 载体，不重开。

**约束**（不重复搬运，只引用）：

- **AD-10**（串行 Gate）：G1 数据能力未冻结前不 archive G1-4、不勾选 umbrella 4.1/4.2、不开 G2 runtime；本 design child 是 G1-4 解冻的前置。
- **AD-02**（不择时/低热度作排除维度）：契约冻结不改变 H1-H8/factor/anti-trap/heat filter 阈值，只定义缺失语义。
- **AD-03**（L2 成本闸门）：required 字段集合明确后，G1 技术验收 Gate「关键字段可用率 ≥95%、降级与失败单独统计」才有可计算口径。
- **G1-1/G1-2/G1-3 已冻结**：L1 数值口径、分层采集边界、L2 full-result contract、canonical run identity。本 design 不修改其 requirement，只在其上定义数据缺失契约。

**本 child 性质**：纯 design/spec child，不动 runtime。所有「应如何处理缺失」是契约定义，不是代码改动；若 design 过程发现必须改 runtime，拆出 implementation/repair child（见 D9）。

## Goals / Non-Goals

**Goals:**

- 从代码实证建立 G1 最小闭环的真实消费者清单（L1 hard_gates/factor_scores/anti_trap/heat_filter + L2 assemble_snapshot 21 key + G1-4 样本 Gate），不凭字段名猜测。
- 生成 G1 最小字段矩阵：每个字段标 `decision_scope` / `criticality` / `missing_policy` / `rule_effect` / `result_effect` / `availability_status` 六个正交维度（详见 [design/data-minimum-field-matrix.md](design/data-minimum-field-matrix.md)）。
- 定义字段/维度/结果三层缺失状态机（`required_missing` / `degraded` / `manual_action_required` / `diagnostic_only`），禁止把字段缺失静默压成「整只股票成功」或用默认值改写排名语义。
- 冻结结果优先级表（字段情况→规则结果→L1 去向→L2 verdict），只钉目标契约语义，runtime 机制留给 repair child（决策 C：选 i）。
- 区分「L1 单 ticker 排名缺失」与「G1-4 样本 Gate 缺失」两类消费者（决策 D：加 `validation_gate` decision_scope）。
- 定义人工补充契约（只定义结构、不实现 UI）。
- 建立 G1/G2/G3 coverage map：G1 基础元数据可被 G2/G3 复用；G2/G3 业务字段只登记责任与依赖，不在本 child 实现，MUST NOT 反向污染 G1 全市场批量路径（详见 [design/g1-g2-g3-data-coverage-map.md](design/g1-g2-g3-data-coverage-map.md)）。
- 明确 provider 保留与兼容原则：不删除/替换/绕过现有 fetcher、provider chain、cache·resume、BatchFetcher、已有输出字段。
- 产出可 review 的 design + spec，覆盖成功、缺失、降级、人工补充与禁止默认值场景。

**Non-Goals:**

- 不修复东财反爬、不新增/替换/大规模重构 provider。
- 不删除任何现有数据获取代码，不重构 BatchFetcher 或所有 fetcher。
- 不实现人工录入 UI，不重新跑 300+ 样本，不做真实 G1-4 performance/cost Gate，不做 Top 20 人工复核。
- 不修改 H1-H8、factor、anti-trap、heat filter 阈值（AD-02 硬约束），不修改 G1-1/G1-2/G1-3 已冻结的 runtime contract。
- 不标记 G1 capability passed，不实现 G2/G3 运行时代码，不动前端/部署。
- 不在本 design child 中顺手实现 runtime；发现必须改 runtime 时暂停并拆 implementation/repair child。

## Decisions

> 完整字段矩阵与 coverage map 落在两个 supporting artifacts。本节只保留决策摘要、两文件引用、关键边界、与 spec 的关系。两文件属于本 OpenSpec change 的一部分，非游离文档。

### D1：G1 最小闭环定义——L1 5 维 + L2 21 key + G1-4 样本 Gate，不含 dossier 三维

**决策**：G1 快筛闭环 = 全市场批量采集（5 维）→ L1 量化筛选（hard_gates→factor_scores→anti_trap→heat_filter）→ L2 成本闸门（assemble_snapshot 21 key + verdict 缓冲带 + top-20 cap）→ 候选结果（full_results + shortlist 派生）。G1 共用的是：canonical ticker / run identity / 数据日期·as_of·freshness / 字段级来源·失败原因·provenance / L1·L2 实际消费的量化字段 / 明确的缺失与降级状态 / 可审计的 input snapshot·evidence 元数据。G1-4 样本 Gate（≥300/≥8 行业/每行业≥10）是作用于**样本集**的校验消费者，不是作用于单只 ticker——见 D6。

**实证依据**：`main.py:30` `G1_QUANT_DIMENSIONS`（已由 `g1-staged-fetch-boundary` 冻结）；dossier 三维（`batch_fetcher.py:35-41`）在 L1 漏斗与 L2 `assemble_snapshot` 中**从未被 `.get()` 读取**。本 design 不重新发明维度集合，复用 `G1_QUANT_DIMENSIONS`。

### D2：字段六维属性——拆「是否参与 G1」与「缺失后状态」

**决策**：每个字段标六个正交维度（`decision_scope` / `criticality` / `missing_policy` / `rule_effect` / `result_effect` / `availability_status`），不混在单一 `G1_status` 列。`criticality=required` 只回答「是否参与 G1」，不回答「缺失后怎么办」——后者由 `missing_policy`+`rule_effect`+`result_effect` 决定。`availability_status` 拆出 `present_but_degraded`，使 fallback 派生值（如 CNINFO 全市场均值）不计 `usable_rate`。**逐字段矩阵（含 producer/consumers(file:line)/freshness/future_owner）见 [design/data-minimum-field-matrix.md](design/data-minimum-field-matrix.md) §2。**

**关键裁决摘要**（详见字段矩阵 §3-§4）：

- `basic.industry`：`required`，但 `missing_policy` 双消费者区分——单 ticker L1 = `degrade`（允许继续带标记）；G1-4 样本 Gate（`validation_gate`）= `block`（样本 Gate 判不通过或换源）。
- `risk.pledge_ratio`：`required`，`missing_policy` 视 `record_not_found`（known-zero，满分）/ `source_failed`（safety=0 惩罚 + manual，不阻断）/ `invalid_value` 三态（决策 A：选 iii）。
- `kline.close`/`turnover_rate`：`required`，`missing_policy=block`（heat_filter 禁静默放行）。
- `financials.years`：`required`，H2 缺失→`not_evaluable`（禁 `len([])<3` 误杀）。
- `valuation.pe_ttm`：`required`，CNINFO fallback 标 `present_but_degraded`，禁当真值参与 ranking。
- `risk.goodwill` / `valuation.pe_history`/`pb_history`/`pb_percentile_5y` / `kline.dates`/`volume`：`optional`/`diagnostic`，已采集但不参与 G1 决策。

### D3：缺失状态机——四态 + 字段/维度/结果三层

**决策**：定义 `required_missing` / `degraded` / `manual_action_required` / `diagnostic_only` 四态，挂字段/维度/结果三层。字段层有 `status`+`missing_reason`+`provenance`；维度整体失败聚合为维度层 status；ticker 最终结果 MUST 聚合字段层 status——只要存在**阻断或改变打分**的字段缺失，结果层 SHALL 携带可见标记（`degraded:true` + `degraded_fields`），MUST NOT 表现为无标记的干净 `watch`/`deep_dive`。L2 degraded 模式（`scout-agent` spec 已冻结）作结果层标记载体。

**关键修正（reviewer P1）**：`degraded:true` 只在「阻断或改变打分」字段缺失时触发；**不阻断的 `manual_action_required`（`ranking_blocked=false`，如 pledge `source_failed`）带 `manual_action_required_fields` 标记，但不强盖 `degraded:true`**——否则会让正常 ranking 的票被误显示为 `watch`。与结果优先级表（D4）对齐。

### D4：结果优先级表——只钉目标契约语义，runtime 机制留 repair child

**决策**（决策 C：选 i）：补结果优先级表，只定义字段情况→规则结果→L1 去向→L2 verdict 的**目标契约语义**；runtime 机制（`not_evaluable` 的返回形状、`after_hard_gates` 如何计数 `not_evaluable` 的 ticker、L2 verdict 映射的代码实现）是 `g1-4-data-source-resilience` repair child 的实现决策，本 design 不钉死。

| 字段情况 | 规则结果 | L1 去向 | L2 verdict |
|---|---|---|---|
| L2 critical 缺失（required_missing block，仅 name/market_cap，属 L2 critical_fields） | `not_evaluable` | 排除/不计入该 gate 放行 | error |
| Heat filter 字段缺失（required_missing block，kline.close/turnover_rate，不在 L2 critical_fields） | heat `not_evaluable`（阻断 heat 放行） | 继续走漏斗但 heat 不计「放行通过」；漏斗计数由 repair child 定 | continue（不自动 error） |
| 非关键字段缺失（`degraded`，如 industry 单 ticker/pe_ttm 子项） | `not_evaluable` 该规则，其余继续 | 继续 | watch + degraded:true（仅当改分） |
| 人工补充可恢复且不阻断（`manual_action_required` ranking_blocked=false，如 pledge source_failed） | safety=0 惩罚但继续 | 继续，带 `manual_action_required_fields` 标记 | continue（不强盖 degraded:true） |
| 人工补充可恢复但阻断（`manual_action_required` ranking_blocked=true，如 market_cap 缺失） | `not_evaluable` | 排除 | error |
| 已确认查无记录（`record_not_found`，如 pledge known-zero） | 满分/正常 | 继续 | 不改变 verdict |
| 诊断字段缺失（`diagnostic_only`，如 risk.goodwill） | 不影响 | 继续 | 不改变 verdict |

> 按 consumer 拆分：H2 unknown（financials.years 缺失）不误杀，漏斗计数由 repair child 实现；Heat filter unknown 阻断 heat 放行但不自动造成 L2 error（kline 不在 L2 critical_fields）；只有 L2 critical_fields（name/market_cap）缺失才直接 L2 error。`not_evaluable`≠`pass`，依赖该字段的 gate 不计「放行通过」。runtime 计数机制留 repair child（决策 C：只钉目标契约语义）。

> 该表解决 spec.md 原「任一 required_missing/manual → degraded:true」与既有 L2 `verdict=error`/`degraded→watch` 路径冲突：`not_evaluable`≠`pass=False`；`not_evaluable` 的 ticker 不计为「放行通过」；L2 `verdict=error` 与 `degraded→watch` 按上表 result_effect 区分。kline 缺失不自动等同 L2 error（它不阻断 L2 critical_fields，只阻断 heat filter 放行）。

### D5：禁止「默认值静默改写排名语义」——明确禁止清单

**决策**：本 design 明确「缺失即默认值」为禁止行为，runtime 改动拆 implementation/repair child（D9）。**完整禁止清单（含实证代码位置 file:line）见 [design/data-minimum-field-matrix.md](design/data-minimum-field-matrix.md) §4。** 核心禁止：financials 缺失→F-Score=0、pledge_ratio None 三漏斗冲突、CNINFO fallback 塞全市场均值（非行业均值，事实更正）、H2 误杀、heat_filter 放行、None→"" 改写（事实更正：仅 key 缺失触发）、risk.py:38 注释代码不符。

**事实更正（reviewer P2）**：

- `main.py:139-140` 的 `basic.get("name","")` 在 key 存在且值为 `None` 时仍返回 `None`——空串兜底**只**在 key 缺失时触发，不掩盖显式 None。契约改为：显式 None 由字段状态/provenance 区分。
- `risk.py:38` 的 `None` 是 `record_not_found`（查无记录），不是 provider 失败——见 D2 pledge 三态。
- `valuation.py:89-95` 的 CNINFO fallback 是对**整张返回表**求均值（全市场均值，注释明示），**非按 ticker 行业匹配**——provenance 名更正为 `fallback_cninfo_full_market_mean`。

### D6：L1 单 ticker 排名 vs G1-4 样本 Gate——双消费者区分（决策 D：加 validation_gate）

**决策**：加 `validation_gate` 作 `decision_scope` 取值，配自己的 `missing_policy`（阻断 Gate，不阻断 ticker）。`basic.industry` 缺失对**单 ticker L1 路径**是 `degraded`（H4/H5 skip、PE 行业折价 skip、L2 渲染「数据缺失」，继续带标记），但对 **G1-4 样本 Gate**（`generate_g1_4_sample.py:182` 把 industry_map 空时归 `未分类`，致 5533→18）是 `block`——样本 Gate MUST 判不通过或换源，不得用「单票 degraded」掩盖「样本集行业覆盖崩塌」。该区分防止「单票 degraded，但样本 Gate 被误认为通过」。

### D7：人工补充契约——只定义结构，不实现 UI

**决策**：字段级 `manual_action_required` 最小结构：canonical ticker / field / status / reason / attempted_sources / as_of_date / requested_action / **affected_rules**（受影响的规则，非被阻断规则）/ ranking_blocked / requires_rerun / provenance_required / manual_value_source / manual_value_note。`affected_rules` 与 `ranking_blocked` 分离：前者列受该字段缺失影响的规则（如 H6/A5/safety_margin），后者表达是否真阻断 ranking（market_cap→true，pledge source_failed→false）。人工提示 SHALL NOT 绕过 G1 Gate；关键字段大量人工补充记为 provider 能力不足（`manual_action_rate`）。本 child 只定义契约，不实现录入 UI。**完整结构与 scenarios 落在 spec.md。**

### D8：G1/G2/G3 coverage map——只登记依赖，不实现 G2/G3 字段

**决策**：coverage map 列 field / owner / source / downstream consumer / prerequisite Gate / blocking dependency / planned child。G1 基础元数据可被 G2/G3 复用；G2（main_business/peers/research/capex_proxy/evidence/key_variables/what_would_change_my_mind/InvestmentThesis）与 G3（成本价/持仓/仓位/HoldingContract/MonitorSignal/thesis-break 监控）只登记责任与依赖，不在本 child 实现。**完整 coverage map 见 [design/g1-g2-g3-data-coverage-map.md](design/g1-g2-g3-data-coverage-map.md)。**

**关键 blocking dependency**：G2 `peers` 依赖 G1 `basic.industry`（industry 不解决则 G2 peers 持续降级）；G2 dossier 的 capex_proxy/munger pledge 代理复用 G1 已采字段（G1 可用率<95% 拖垮 G2 dossier）；G3 HoldingContract 依赖 G2 InvestmentThesis（G2 Gate 未通过则 G3 无可信输入）。

### D9：runtime 改动边界——拆 implementation/repair child，不在本 design 实现

**决策**：本 design child 只冻结契约语义。以下 runtime 改动**不在本 child 实现**，确认 design 通过后拆独立 child：`g1-4-data-source-resilience`（修 industry_mapper 静默空 dict、risk.py pledge 加 fallback、valuation.py:95 fallback 不再塞均值、hard_gates.py:46-48 H2 误杀改 not_evaluable、heat_filter.py:29-37 kline 缺失放行改 not_evaluable、stock_features.py:16/factor_scores.py:297 缺失即 0 改 not_evaluable）、按新契约调整 G1-4 harness 重跑真实 Gate、对特定关键字段开窄人工补充/来源 repair child。原则：design 过程若发现必须改 runtime，先暂停，记录缺口，拆后续 child，不顺手实现。

## Risks / Trade-offs

- **[字段矩阵与代码漂移]** 矩阵基于 2026-07-28 代码扫描，未来 fetcher 字段变化会使矩阵过时 → **缓解**：spec scenarios 用「真实消费者」语义而非硬编码字段名，repair child 落实时以代码实证复核；矩阵标注扫描日期。
- **[H2/heat_filter 缺失误杀/放行属 runtime 改动]** 本 design 要求改语义但不在本 child 实现 → **缓解**：D9 明确拆 repair child，design 只冻结目标语义；用户确认 design 后才进 apply。
- **[pledge_ratio record_not_found 满分需 provenance 证明]** known-zero 满分依赖 provenance 区分 `record_not_found` vs `source_failed`，runtime 需 expose 该区分 → **缓解**：契约要求 `pledge_status` 字段，repair child 落实；design 只定义语义。
- **[priority 表 runtime 未钉死]** 决策 C 选 i 留 runtime 机制给 repair child → **缓解**：表钉死目标契约语义（verdict 映射），实现细节由 repair child 定；若 review 认为需更钉死，拆 child。
- **[industry_mapper 根因未修]** 本 design 只标 industry 缺失双消费者语义，不修 industry_mapper → **缓解**：根因修复属 repair child；本 design 确保「industry 缺失可见可统计 + 样本 Gate 不被掩盖」。
- **[Trade-off] design-only 不立即改善 G1-4 实跑结果**：本 child 不跑样本、不修代码 → 接受，本 child 目标是冻结契约使后续 repair 有据可依，G1-4 实跑改善属后续 child。
- **[Trade-off] 两个 supporting artifact 在 openspec validate 外]**：`design/*.md` 不被 `openspec validate` 追踪 → 接受，两文件由 design.md 显式引用且属本 change 目录，review 时一并审；若需 validate 追踪，后续可考虑纳入 spec。

## Migration Plan

本 child 是 design-only，无 runtime 迁移。产物落地顺序：

1. 保护 G1-4 dirty work 到独立分支/checkpoint 或独立 worktree，确认与本 change 基线不互相污染。
2. proposal.md（已完成）。
3. design.md（本文，决策摘要 + 两文件引用 + 关键边界 + 与 spec 关系）。
4. [design/data-minimum-field-matrix.md](design/data-minimum-field-matrix.md)（完整字段矩阵 + pledge 三态 + 禁止清单 + 可用率口径）。
5. [design/g1-g2-g3-data-coverage-map.md](design/g1-g2-g3-data-coverage-map.md)（完整 coverage map + 边界规则 + prerequisite Gate 依赖链）。
6. specs/data-minimum-contract/spec.md（ADDED Requirements + scenarios，含优先级表 + 四态状态机 + 双消费者区分 + 事实更正 + 可用率五拆）。
7. tasks.md（含 `openspec validate --strict` + 用户 review gate，不直接 apply runtime）。
8. `openspec validate g1-data-minimum-contract --strict`。
9. 停下交用户 review；用户确认后才进 apply；apply 中若需改 runtime 拆 implementation/repair child。

**回滚**：所有产物在 `openspec/changes/g1-data-minimum-contract/`（含 `design/` 子目录），`git checkout` 即回滚；不动 `value-screener/` 源码，无 runtime 回归面。

## Open Questions

- **`validation_gate` 的样本 Gate 通过条件是否需在 spec 级冻结**：本 design 只定义「industry 缺失→样本 Gate block」语义，具体通过阈值（≥300/≥8 行业/每行业≥10）由 `screening-validation-sample` spec（G1-4）已冻结，本 child 不重复；review 确认边界清晰。
- **`pledge_status`（record_not_found/source_failed/invalid_value）字段是否需在 spec 级冻结为 runtime 契约**：倾向在 spec 标「契约要求 expose 该区分」，具体字段名由 repair child 定；review 确认。
- **两个 supporting artifact 是否需被 `openspec validate` 追踪**：当前不在追踪范围，由 design.md 引用；若 review 认为必须纳入 spec 级验证，再调整。
