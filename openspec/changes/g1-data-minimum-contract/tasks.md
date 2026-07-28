## 1. 基线保护与上下文确认

- [x] 1.1 保护 G1-4 dirty work：把 `openspec/changes/g1-300-sample-scale-precheck/`、`value-screener/scripts/generate_g1_4_sample.py`、`value-screener/scripts/collect_g1_4_evidence.py`、`value-screener/tests/test_g1_4_*.py`、`value-screener/.gitignore` 这组未提交改动保护到独立分支/checkpoint 或独立 worktree，确认与本 change 基线不互相污染
- [x] 1.2 确认新 change 基线在 `main` HEAD `75c4a13`，本 change 只写 `openspec/changes/g1-data-minimum-contract/`，不触碰 G1-4 partial work 与 `value-screener/` 源码
- [x] 1.3 复核 G1-4 实证证据：5533→18、行业全 `未分类`、`size_meets_minimum=false`、无真实 L1→L2 evidence bundle；`industry_mapper` 静默空 dict 与 `risk.py` 单源质押是数据能力缺口而非脚本 bug

## 2. 设计依据阅读

- [x] 2.1 读 `design/three-goal-capability-roadmap.md`（G1 快/G2 深/G3 拿得住、串行 Gate、umbrella/child 治理）
- [x] 2.2 读 `design/total-design.md` 与 `design/architecture-decisions.md`（AD-01~AD-10），确认本 change 引用而非重复搬运
- [x] 2.3 读 G1/G2/G3 umbrella specs：`openspec/changes/g1-fast-personal-value-screening/`、`g2-deep-investment-thesis/`、`g3-holding-discipline/`
- [x] 2.4 读 G1-1/G1-2/G1-3 已归档 specs（`quantitative-screener`/`staged-fetch-boundary`/`scout-agent`/`run-identity`/`l1-numeric-correctness`）确认已冻结契约边界，本 change 不重开

## 3. 实际消费者盘点（代码实证，禁止凭字段名猜测）

- [x] 3.1 从 `screener/hard_gates.py` 盘点 H1-H8 各 gate 消费的字段 key、来源 dim、缺失行为（H2 缺失误杀 vs 其余放行）
- [x] 3.2 从 `screener/factor_scores.py` 盘点 quality/value/safety_margin 三子项消费的字段、规则编号、缺失行为（含「缺失即 0」点 `factor_scores.py:231-232,297,41-42`）
- [x] 3.3 从 `screener/anti_trap.py` 盘点 A1-A7 扣分规则消费的字段（A3/A7 MVP 跳过），确认 pledge_ratio 三漏斗语义冲突
- [x] 3.4 从 `screener/heat_filter.py` 盘点 HF1/HF2 消费的 kline 字段与「缺失即放行」位置
- [x] 3.5 从 `scout/input_assembly.py::assemble_snapshot` 盘点 L2 21 key（10 直读 + 10 派生 + ticker）、`critical_fields`、`financials_floor`、`data_fields`
- [x] 3.6 从 `data/lib/industry_mapper.py`、`data/fetchers/risk.py`、`data/lib/batch_fetcher.py` 盘点 provider 产出字段、失败语义（静默空 dict / 单源无 fallback / `__error__`）、`dimensions=None` 兜底

## 4. G1 最小字段矩阵（六维属性，独立 artifact）

- [x] 4.1 起草 `design/data-minimum-field-matrix.md`：定义六维（decision_scope/criticality/missing_policy/rule_effect/result_effect/availability_status），加 `validation_gate` decision_scope
- [x] 4.2 逐字段行（无 `balance_sheet.*` 通配）填 producer/consumers(规则+file:line)/freshness/future_owner，覆盖 basic/financials/kline/valuation/risk/identity·meta
- [x] 4.3 特殊字段裁决：industry（双消费者 degrade/block）、pledge_ratio（三态）、kline（block heat）、financials.years（H2 not_evaluable）、pe_ttm（present_but_degraded）、risk.goodwill（diagnostic）
- [x] 4.4 写 pledge_ratio 三态（record_not_found 满分/source_failed manual/invalid_value，决策 A 选 iii）
- [x] 4.5 写「缺失即 0」禁止清单（含实证 file:line）与可用率五拆口径（含 fallback 不计 usable）

## 5. G1/G2/G3 coverage map（独立 artifact）

- [x] 5.1 起草 `design/g1-g2-g3-data-coverage-map.md`：列 field/owner/source/downstream consumer/prerequisite Gate/blocking dependency/planned child
- [x] 5.2 G2 字段登记（main_business/peers/research/capex_proxy/evidence/key_variables/what_would_change_my_mind/InvestmentThesis）+ G3 字段登记（成本价/持仓/HoldingContract/MonitorSignal/thesis-break），只登记不实现
- [x] 5.3 写边界规则（G1 元数据复用、G2/G3 不污染 G1 路径、AD-10 不掩盖、dossier 复用 G1 已采字段）与 prerequisite Gate 依赖链

## 6. 缺失状态机、优先级表与人工补充契约

- [x] 6.1 定义 `required_missing` / `degraded` / `manual_action_required` / `diagnostic_only` 四态语义
- [x] 6.2 定义字段/维度/结果三层关系：阻断/改分字段→`degraded:true`；非阻断 manual→带 `manual_action_required_fields` 标记但不强盖 degraded（修 spec 原「任一 required_missing/manual→degraded:true」冲突）
- [x] 6.3 冻结结果优先级表（字段情况→规则结果→L1 去向→L2 verdict，决策 C 选 i：只钉目标契约语义，runtime 机制留 repair child）
- [x] 6.4 定义 L1 单 ticker 排名 vs G1-4 样本 Gate 双消费者区分（`validation_gate` decision_scope，决策 D）
- [x] 6.5 定义人工补充契约最小结构（含 ranking_blocked 区分阻断/不阻断、manual_action_rate 记 provider 不足）

## 7. 事实更正与 provider 保留

- [x] 7.1 更正 4 个事实错误：main.py None→""（仅 key 缺失触发）、pledge_ratio None（区分 record_not_found/source_failed）、CNINFO fallback（全市场均值非行业均值，provenance 改名）、risk.py:38 注释代码不符
- [x] 7.2 确认 provider 保留原则：不删除 fetcher/fallback chain/cache·resume/BatchFetcher/已有输出字段，新契约通过 status/provenance 标注而非隐藏失败

## 8. spec scenarios 覆盖

- [x] 8.1 写覆盖「成功」场景（字段齐全正常 ranking）
- [x] 8.2 写覆盖「缺失」场景（required_missing 阻断、degraded 携带标记、manual_action_required 不填默认值、diagnostic_only 不进排名）
- [x] 8.3 写覆盖「降级」场景（industry 单 ticker degrade、financials 年份不足因子失效、valuation fallback 不塞全市场均值当真值）
- [x] 8.4 写覆盖「人工补充」场景（pledge source_failed 契约、阻断 ranking 字段契约、人工补充率过高记 provider 不足）
- [x] 8.5 写覆盖「禁止默认值」场景（F-Score 不当 0、H2 不误杀、heat_filter 不放行、三层状态聚合可见标记、非阻断 manual 不压成 watch）
- [x] 8.6 写覆盖「pledge 三态」「双消费者区分」「可用率五拆」「G2/G3 不污染 + provider 保留 + 不改已冻结 contract」场景

## 9. 验证与 review gate

- [x] 9.1 `openspec validate g1-data-minimum-contract --strict` 通过
- [x] 9.2 放行判断自查：能明确回答 handoff §7 八个问题（G1 最少需要哪些字段、21 字段哪些 required、每个字段缺失做什么、哪些可人工补充是否阻断、哪些只保留采集不参与 G1、东财失败如何区分三态、G2/G3 缺口由谁负责、G1-4 真实 Gate 依赖哪些字段和 evidence）
- [ ] 9.3 停下交用户 review，不直接 apply runtime；apply 中若需改 runtime（H2/heat_filter/valuation fallback/industry_mapper/risk fallback 等）拆 `g1-4-data-source-resilience` implementation/repair child
- [ ] 9.4 design child 通过后由用户决定下一步：开 repair child / 按新契约调整 G1-4 harness 重跑 / 部分字段降 diagnostic-only / 对特定关键字段开窄人工补充 child；在数据契约与关键 provider 能力未明确前，不 archive G1-4、不勾选 umbrella 4.1/4.2、不开 G2 runtime
