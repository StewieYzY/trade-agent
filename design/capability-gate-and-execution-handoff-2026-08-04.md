# trade-agent Capability Gate 与完整执行 Handoff

> 日期：2026-08-04
>
> 类型：历史完整执行 Handoff
>
> 状态：`SUPERSEDED / HISTORICAL / READ-ONLY`
>
> 当前执行必须从 `design/capability-gate-and-execution-handoff.md` 进入，
> 不得从本文件恢复工作。
>
> 适用范围：G1「快」→ G2「深」→ G3「拿得住」全部后续开发
>
> 当前 main 基线：`main@dd52d11`
>
> 当前首要执行入口：`design/m0-g2-trust-foundation-handoff-2026-08-03.md`
>
> 新增产品需求：`design/growth-expectation-capitalization-prd-2026-08-04.md`

## 1. 本文件的用途

本文件保存项目当前真实基线、稳定目标、Capability Gate、总体里程碑、child change 拆分原则和停止条件。

它回答：

- 当前 main、worktree、OpenSpec 与真实能力分别到了哪里；
- G1/G2/G3 的关键路径是什么；
- 新增“成长预期资本化诊断”应插入哪里；
- 每个大里程碑可以拆成哪些独立 OpenSpec child change；
- 什么证据能够放行，什么情况必须停止；
- 下一次开发会话应从哪里开始。

它不替代：

- `design/three-goal-capability-roadmap.md`：产品能力与 Capability Gate 第一参考源；
- `design/total-design.md`：总体设计与第一性原理；
- `design/architecture-decisions.md`：跨 change 架构决策；
- `design/growth-expectation-capitalization-prd-2026-08-04.md`：成长股预期资本化产品需求；
- 各 OpenSpec proposal/design/spec/tasks：具体 change 的执行合同；
- 每个 child change 完成后的 dated rolling handoff；
- 独立 code review、真实运行产物和 capability evidence bundle。

## 2. 文档版本与治理

### 2.1 Dated Handoff 规则

dated Handoff 是某个日期的完整规划快照。

新增重大需求、里程碑顺序变化或真实 baseline 明显变化时：

1. 创建新的日期版本；
2. 保留旧版本，不覆盖历史；
3. 在新版本中说明替代关系；
4. 同步 active umbrella OpenSpec；
5. 不用聊天结论替代永久文档。

### 2.2 Rolling Handoff 规则

每个 child change 完成后生成独立 rolling handoff，至少记录：

```text
workspace / branch / worktree / HEAD
change proposal/design/spec/tasks
实现内容
focused tests / relevant suite / strict validation
真实运行产物
独立 review 结论
archive / commit / merge 状态
剩余 blocker
下一 child
exact commands
```

archive、task checked、commit、绿测、真实实验任一单项都不等于 Capability Gate 通过。

## 3. 当前真实基线（2026-08-04 核验）

### 3.1 主工作区

```text
path:   /Users/admin/Documents/trade-agent
branch: main
HEAD:   dd52d11
```

main 当前未跟踪设计文件：

```text
design/capability-gate-and-execution-handoff-2026-08-03.md
design/growth-expectation-capitalization-prd-2026-08-04.md
design/m0-g2-trust-foundation-handoff-2026-08-03.md
design/tradingagents-cn-comparative-assessment-2026-08-03.md
```

本文件创建后同样保持未跟踪，直到用户决定以 docs-only change 提交。

这些文档存在于工作区不等于已经进入 main 历史。

### 3.2 f3c mainline worktree

```text
path:   /Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline
branch: f3c-harness-mainline
HEAD:   a041314
```

HEAD 已包含：

- `22ab9f8 feat(f3c): stabilize measurement harness and live evidence`
- `a041314 feat(g2): add strong single-agent fallback foundation`

但当前 worktree 非 clean，存在：

- `f3c-r1-crosstalk-root-cause` active change 删除与 archive 目录新增；
- f3e provider schema compatibility 相关实现、测试、review 和 archive 产物；
- live experiment run artifacts；
- debate/watchlist 输出；
- dated dynamic closure handoff；
- 对 canonical handoff 和 preliminary report 的未提交修改。

因此：

> f3c/f3e closure 处于动态收口状态，不能仅因 archive 目录出现或测试文件存在就宣称已完成、已合并或 main 已具备能力。

### 3.3 G2 integration worktree

```text
path:   /Users/admin/Documents/trade-agent/.worktrees/g2-integration-mainline
branch: codex/g2-integration-mainline
HEAD:   f47db88
status: clean
```

提交链：

```text
a6341a1 feat(g2): add strong single-agent fallback foundation
85b3011 feat(g2): integrate fallback prerequisites on mainline
f47db88 chore(g2): archive mainline fallback integration
```

该分支已形成干净 integration 证据，但尚未进入 main。

不能把 `f47db88` 描述为 main capability。

### 3.4 旧 stacked f3c worktree

```text
path:   /Users/admin/Documents/trade-agent-f3c-strong-model-control
branch: codex/f3c-strong-model-control
HEAD:   f83bb85
```

该 worktree 仍是旧 stacked 资产，只用于历史对照和必要的选择性移植，不作为可整体合并分支。

### 3.5 main 上的 OpenSpec 状态

在本次同步 active G2 umbrella 后：

| Change | 状态 | 任务 | 真实含义 |
|---|---|---:|---|
| `g2-deep-investment-thesis` | in-progress | 0/27 | 已增加成长预期资本化 M4.5 治理，尚无 umbrella closure |
| `f3c-r1-crosstalk-root-cause` | in-progress | 5/17 | main 仍显示 active；worktree closure 尚未合并 |
| `g1-4-data-source-resilience` | in-progress | 0/48 | runtime 修复存在，真实 provider/sample Gate 未闭 |
| `g1-fast-personal-value-screening` | in-progress | 6/16 | G1 umbrella 未通过 |
| `g3-holding-discipline` | in-progress | 0/29 | 仅允许设计，runtime 锁定 |

OpenSpec list 是 main 当前文件视角，不能替代其他 worktree 的 branch/commit 核验。

### 3.6 当前能力状态

```text
G1：未通过
  - 数据缺失语义和部分 runtime 韧性修复已存在
  - 300+ 多行业真实样本 Gate 未通过
  - 全市场 warm-cache 性能/成本未验证
  - Top 20 用户风格复核未完成

G2：建设中，未通过
  - f3c measurement/live evidence 与 fallback foundation 已在独立 worktree 前进
  - clean G2 integration branch 已存在但未进入 main
  - 真实 dossier、完整审计、双路径 A/B、盲评和 InvestmentThesis evidence bundle 未闭
  - 成长预期资本化 PRD 已确认，尚未实现 M4.5 child changes

G3：runtime 未开始
  - HoldingContract、状态机和 shadow mode 继续锁定
  - 只允许完善输入合同和设计
```

## 4. 稳定产品目标

```text
G1 快：个人价值风格筛选
    ↓
G2 深：可信 InvestmentThesis
    ↓
G3 拿得住：持仓纪律副驾驶
```

三个目标没有发生变化。

### 4.1 G1「快」

目标不是拥有更多因子或调用更多在线接口，而是：

```text
provider 同步
→ normalized raw response
→ canonical snapshot
→ 本地漏斗筛选
→ L2 成本闸门
→ 符合用户价值风格的可信候选池
```

### 4.2 G2「深」

目标不是拥有更多 Agent 或辩论轮次，而是生成：

```text
可信事实
+ 可审计推断
+ 明确假设
+ 反证与风险
+ 关键变量
+ 什么情况下改变判断
= InvestmentThesis
```

新增成长预期资本化诊断后，G2 还需要回答：

```text
当前价格由多少现有经营能力支撑？
市场已经定价了多少未来增长？
当前价格隐含多高增长和多长增长期？
该要求是否超出公司证据支持的可信范围？
```

### 4.3 G3「拿得住」

目标不是自动替用户持有或交易，而是：

```text
保存用户确认的 HoldingContract
→ 比较价格波动与 Thesis 变化
→ 区分情绪扰动、预期兑现偏差和 Thesis 破坏
→ 提醒用户按纪律复核
```

系统不连接券商、不自动下单，最终决策始终由用户作出。

## 5. 新增成长预期资本化需求的定位

### 5.1 它不是新的第四个 Goal

成长预期资本化诊断属于 G2 的确定性分析子能力，不改变 G1→G2→G3 的整体产品结构。

### 5.2 它不是 Agent 角色

该能力必须由独立、版本化、可复现的 deterministic engine 产生：

```text
冻结数据
+ 用户确认假设
+ 版本化公式
→ growth_expectation_diagnostic artifact
→ Agent 解释、质疑和形成 Thesis
```

Agent 不得：

- 自行修改底层计算结果；
- 编造折现率、维护性资本开支比例或可信增长区间；
- 隐藏 warning/failed/not_evaluable；
- 将 diagnostic 数值写成确定目标价；
- 用语言表达替代数值合同。

### 5.3 它不进入当前 G1 critical path

G1 最多在未来增加低成本：

```text
high_expectation_risk
```

但该标签：

- 不进入 hard gate；
- 不改变主排序；
- 不因高 PE 自动排除成长股；
- 不在 M0–M3 当前关键路径中实现；
- 如未来实现，必须新建独立 child change。

### 5.4 它为 G3 提供原始预期基线

G3 在 G2 passed 后可保存：

- 初始隐含增长率；
- 初始隐含高增长年限；
- 初始未来价值占比；
- 用户确认的可信增长区间；
- 关键经营变量和失效条件。

G3 监控实际经营是否追上原始预期，但不覆盖或重算 G2 的历史基线。

## 6. 总体开发里程碑

## M0：G2 前置可信基础收口

### 目标

完成 f3c 动态 closure 与 G2 clean integration，使后续 dossier、deterministic diagnostic 和 A/B 建立在可审计、可失败闭环的基础上。

### 主要 change / 小目标

1. `f3c-r1-crosstalk-root-cause`
   - 核验 live weak/strong evidence；
   - 核验 ticker/features/prompt/model/provider 绑定；
   - 完成独立 review；
   - archive、commit 和 merge 状态一致。

2. 由实验产生的 f3d/f3e
   - 只处理真实发现的 provider schema、positive-data boundary 或其他根因；
   - 每个修复独立测试和归档；
   - 不预先重写全部 Prompt。

3. `g2-mainline-fallback-integration`
   - 复核 `codex/g2-integration-mainline@f47db88`；
   - 验证 clean branch 不携带 stacked ancestors；
   - 形成可合并、可回退、可审计的 mainline integration。

### 放行条件

- f3c/f3e change 状态、archive、commit 和产物一致；
- 显性串台为 0；
- live run 输入、模型、ticker、features、prompt、provider 和 usage 可追溯；
- fixture/reference 不冒充 live evidence；
- G2 fallback integration 独立 review 通过；
- relevant tests 与 strict validation 通过；
- main merge 后重新核验 OpenSpec 与 runtime。

### 不放行条件

- worktree dirty closure 被描述成已完成；
- archive 目录未提交却宣称 archived；
- 同一模型冒充 weak/strong；
- ticker/features 错配；
- provider schema 失败被当成模型质量结论；
- branch 上能力被描述为 main 能力。

### 详细入口

`design/m0-g2-trust-foundation-handoff-2026-08-03.md`

当前执行时还应读取 f3c worktree 内最新 dynamic closure handoff。

## M1：A 股 Provider Qualification

### 目标

确认 Longbridge/LongPort 是否能以字段级、可追溯方式补强 G1/G2，不直接接入生产 ranking 或 diagnostic。

### 主要 change / 小目标

1. `a-share-provider-qualification`
   - 对至少 5 只代表性 A 股执行只读 probe；
   - 验证 `static_info`、`quote`、`calc_indexes`、历史 K 线；
   - 验证 IS/BS/CF、估值历史、行业估值和 consensus 候选能力；
   - 保存 raw response、单位、报告期、权限、限流和失败状态。

2. `provider-contract-and-provenance`
   - 定义 provider family、provider、method、market；
   - 定义 `as_of/report_period/currency/unit/raw_field`；
   - 定义字段级 status 和冲突规则；
   - 不把文档存在等同于 A 股 runtime 可用。

3. Growth diagnostic shadow probe
   - 只登记 5–10 年财务、现金/有息债务、折旧摊销、营运资本、行业估值、多年度 consensus 是否候选可得；
   - 不把这些字段设为当前 G1 Gate blocker；
   - 未 probe 通过不得进入 M4.5 正式输入。

### 放行条件

- 至少 5 只不同类型 A 股完成字段级 probe；
- 关键字段单位和报告期规则固定；
- 与 AkShare/东财/同花顺/百度完成字段级差异报告；
- 无未验证字段进入 ranking、diagnostic 或 Gate；
- provider 失败状态可追溯。

## M2：G1 Canonical Snapshot 与分层筛选 Runtime

### 目标

让 G1 从可信本地快照完成快速筛选，而不是全市场逐股在线取数。

### 主要 change / 小目标

1. `g1-canonical-snapshot-sync`
   - raw response 与 canonical snapshot 分层；
   - snapshot manifest、source-set hash、as-of、field status；
   - 缓存失败、降级和冲突可见；
   - 现有消费者先通过 sidecar metadata 兼容。

2. `g1-provider-batch-adapter`
   - 支持批量 provider 调用；
   - LongPort/Longbridge 先 shadow；
   - 字段级 merge，不使用 first-non-empty 伪成功；
   - 保留 provider provenance。

3. `g1-staged-screening-runtime`
   - Stage A：basic/current valuation；
   - Stage B：financials/risk；
   - Stage C：历史估值/K 线；
   - 用 ticker 集合和调用统计证明 fetch calls 随漏斗下降。

4. `g1-provider-health-and-failure-visibility`
   - source failure、permission、rate limit、manual action；
   - 单股失败不阻断批次；
   - 无 silent defaults。

### 重要边界

- G1 不采集 `main_business/peers/research`；
- G1 不运行成长预期 V0；
- G1 不恢复未经验证的 DCF 排序；
- LongPort 暂不替代历史换手率、质押率、审计意见和未验证财务科目。

## M3：G1 真实 Capability Gate

### 目标

证明 G1 能从全市场形成可用、可解释、成本可控、符合用户个人风格的候选池。

### 主要 change / 小目标

1. `g1-300-sample-validation`
   - 固定 300+ 只、多行业、多风险类型样本；
   - 验证字段 coverage、failure isolation、行业覆盖和 verdict 分布；
   - 失败时保持 blocked。

2. `g1-full-market-performance-cost`
   - warm-cache 全市场运行；
   - 验证 ≤15 分钟；
   - 关键字段可用率 ≥95%；
   - L2 成本 ≤¥2；
   - 落盘漏斗、failure summary 和 usage。

3. `g1-top20-style-review`
   - 冻结 ScreeningProfile、run 和输入集合；
   - 用户人工复核 Top 20；
   - 至少 70% 被判断为值得进一步研究；
   - 不降低门槛凑数。

### 放行条件

所有技术 Gate、产品 Gate 和 evidence bundle 同时通过后，才能标记 G1 passed。

成长预期资本化 PRD 不新增当前 G1 Gate 条件。

## M4：G2 Evidence Dossier Quality

### 目标

让 G2 输入具备来源、报告期、新鲜度、单位、降级状态、冻结能力和确定性分析可消费性。

### 主要 change / 小目标

1. `g2-evidence-dossier-quality`
   - 主营、同行、研报、capex proxy 数据质量；
   - 公司事实、市场预期和用户输入物理分区；
   - 关键字段 provenance；
   - 缺失和降级状态。

2. `g2-source-aware-dossier`
   - canonical snapshot 接入 dossier；
   - qualification 合格 provider 才可接入；
   - 多源字段并列保存；
   - generic reason 恢复为可审计状态。

3. `g2-diagnostic-input-contract-foundation`
   - 为 M4.5 准备价格、市值、财务、capex、同行和 consensus 输入；
   - 保存币种、单位、report period、as-of；
   - 支持 assumption snapshot；
   - 缺字段时不静默回填。

### 放行条件

- 高严重度凭空数字为 0；
- 关键事实追溯率 ≥95%；
- dossier snapshot 可冻结、复现、比较；
- 公司事实/市场预期/用户假设分区稳定；
- 单位和报告期能够支持确定性计算；
- 数据不足输出 degraded/insufficient_data/not_evaluable。

## M4.5：G2 Growth Expectation Diagnostic V0

### 目标

建立独立于 Agent 的成长预期资本化诊断，回答：

- 现有经营能力价值区间；
- 当前市值中的未来价值占比；
- 当前价格隐含的增长率或高增长年限；
- 市场隐含要求与可信增长区间的差距；
- 计算不适用或数据不足的原因。

该里程碑必须在强单 Agent baseline 与 Council A/B 冻结之前完成。

### Child 1：`g2-growth-expectation-contract`

#### 目标

冻结 V0 输入、输出、假设、模型适用性、状态语义和 golden cases。

#### 开发思路

- 定义 `GrowthExpectationDiagnostic` contract；
- 定义 `AssumptionSnapshot`；
- 固定 EPV proxy + 成熟期估值交叉锚；
- 固定两种互斥 reverse 模式；
- 固定 `complete/partial/not_evaluable/failed`；
- 固定 `maintenance_capex_unconfirmed/no_finite_solution/unit_mismatch` 等原因；
- 注册高 ROIC 成长、高 capex、研发型、周期顶部、负现金流、历史正反例；
- 不实现 runtime calculator。

#### 验收

- spec 无未定义字段；
- 用户输入校验和错误语义明确；
- golden cases 的经济方向明确；
- V0 最大等级为 diagnostic；
- strict validation 通过。

### Child 2：`g2-growth-expectation-v0-engine`

#### 目标

实现可复现的确定性计算器。

#### 开发思路

- 独立模块，不复用当前 G1 `compute_simple_dcf` 作为决策真值；
- 计算 normalized owner earnings；
- 使用用户确认的维护性资本开支比例；
- 计算 EPV proxy range；
- 计算成熟期 PE cross-check；
- 保留双锚分歧；
- 固定增长率求年限；
- 固定年限求增长率；
- 输出敏感性矩阵；
- 无有限解时 fail closed；
- 记录 formula version、input hash、assumption hash 和 provenance。

#### 验收

- 相同输入和假设结果可复现；
- 折现率、增长率、年限变化符合经济直觉；
- 双锚差异不机械平均；
- 负利润、金融股、单位冲突、无有限解正确拒绝；
- focused tests 与 golden tests 通过；
- 不调用 LLM。

### Child 3：`g2-growth-expectation-dossier-integration`

#### 目标

将不可变 diagnostic artifact 接入 dossier、强单 Agent、Council 和 InvestmentThesis。

#### 开发思路

- dossier 保存 `growth_expectation_diagnostic`；
- 保存 `assumption_snapshot` 与用户确认来源；
- Agent 只解释和质疑；
- DA 回查 diagnostic 与原始输入；
- Thesis 输出 `valuation_expectation`；
- `calculation_status` 和 warning 不丢失；
- 两条 A/B 路径共享完全相同 artifact；
- 共享计算结果不计为 Council 独有增量。

#### 验收

- ticker/run/dossier/diagnostic/Thesis 100% 对齐；
- Agent 不重新计算或篡改数值；
- `not_evaluable` 可被 Thesis 诚实表达；
- 同一 artifact 在两条路径 hash 一致；
- G1 排序和全市场采集不受影响。

### M4.5 放行条件

- 三个 child 独立归档；
- deterministic engine 无 LLM；
- input/assumption/formula/provenance 可追溯；
- golden cases 和受控真实样本通过；
- V0 明确标记 diagnostic；
- 不使用未经 qualification 的 provider；
- 不以完整 V1 模型阻塞 V0。

### M4.5 停止条件

- 需要静默假设才能得出结果；
- 增长率和年限同时无约束求解；
- 总 capex 被直接当作 maintenance capex；
- 行业平均被直接当作成熟期锚；
- Agent 输出被用作底层数值；
- 为实现 V0 开始建设完整三表预测平台；
- V0 被接入 G1 hard gate 或主排序。

## M5：G2 InvestmentThesis 与 A/B Closure

### 目标

证明 Council 相比强单 Agent 是否产生稳定信息增量，并发布包含 `valuation_expectation` 的稳定 InvestmentThesis。

### 主要 change / 小目标

1. `g2-strong-single-agent-baseline`
   - 冻结模型、prompt、工具、预算；
   - 冻结 dossier 与 growth diagnostic；
   - 形成可复现 baseline。

2. `g2-council-ab-evaluation`
   - 同 ticker；
   - 同 dossier snapshot；
   - 同 diagnostic/assumption snapshot；
   - 同工具与可比预算；
   - 8–10 只多类型股票；
   - 至少覆盖高估值成长与 diagnostic not-evaluable；
   - 匿名评分与成本记录。

3. `g2-investment-thesis-interface-and-closure`
   - 发布稳定 `InvestmentThesis`；
   - 包含 `valuation_expectation`；
   - evidence/counter-evidence/assumptions/risks/key_variables；
   - what_would_change_my_mind/pending_verification/quality_status；
   - 形成 G2 evidence bundle。

### A/B 公平性规则

- diagnostic artifact 对两条路径完全相同；
- 共享数值引用本身不计 Council 增量；
- 有效增量必须是新增反证、风险、关键变量、假设质疑或改变条件；
- 任一路径修改底层 diagnostic 即该样本失效；
- diagnostic 缺失时两条路径必须看到同样的 `not_evaluable`。

### 放行条件

- Council 实质增量 ≥70%；
- 用户盲评 Council 更好 ≥60%；
- Council 明显更差 ≤20%；
- ticker/run/dossier/diagnostic/result 审计对齐率 100%；
- 高严重度凭空数字为 0；
- 关键事实追溯率 ≥95%；
- 未通过时回退强单 Agent + DA/事实检查器 + Synthesizer；
- G2 整体独立 review 通过。

## M6：G3 Holding Discipline Runtime

### 目标

把通过 G2 的 InvestmentThesis 和初始市场预期基线转换为用户确认的持有纪律，不自动交易。

### 主要 change / 小目标

1. `g3-holding-domain-model`
   - `HoldingsRepository`、Holding、HoldingContract draft；
   - CandidateWatchlist 与持仓解耦；
   - 引用 Thesis version 和 diagnostic artifact id。

2. `g3-contract-lifecycle`
   - 用户输入成本、仓位、回撤、复核周期、冷静期；
   - 用户确认预期增长基线和关键变量；
   - draft → user-confirmed → active。

3. `g3-monitor-signal-and-evaluator`
   - price review 与 thesis-break 分离；
   - 实际收入/利润/现金流与原始隐含预期比较；
   - Green/Yellow/Red/Blue/Rebalance Review；
   - 不因价格波动自动改变 Thesis。

4. `g3-shadow-mode`
   - 历史场景回放；
   - 3–5 只真实或模拟持仓连续四周；
   - 只记录系统会如何提示；
   - 不执行交易。

### 放行前置

- G2 capability passed；
- 稳定 InvestmentThesis contract 已发布；
- `valuation_expectation` 能被版本化消费；
- 用户保留最终判断。

## M7：Gate 通过后的产品化与 V1

### 目标

把已经验证的能力做成可持续使用的工作台，并在不阻塞 V0 的前提下补强完整估值数据与模型。

### 主要 change / 小目标

1. `g1-funnel-observability-ui`
   - 为什么进入、排除和降级。

2. `data-health-and-provider-ops`
   - provider health；
   - 字段 coverage；
   - 同步历史；
   - 失败恢复。

3. `g2-thesis-history-and-export`
   - Thesis version diff；
   - evidence/counter-evidence diff；
   - valuation expectation/assumption diff；
   - Markdown/PDF 导出。

4. `g2-growth-expectation-interaction`
   - 用户确认维护性 capex、折现率、增长区间和成熟期锚；
   - 情景与敏感性展示；
   - loading/empty/error；
   - 输入校验与错误提示。

5. `g2-growth-expectation-v1`
   - 5–10 年正常化；
   - NOPAT；
   - 现金/有息债务与净债务；
   - 折旧摊销和营运资本；
   - ROIC、增量 ROIC、再投资率；
   - 多年度 consensus 与 revisions；
   - reverse DCF 或 economic profit。

6. `task-progress-and-run-history`
   - 节点进度；
   - token、耗时、成本；
   - 可恢复失败。

7. `g3-holding-review-ui`
   - HoldingContract；
   - 复核状态；
   - 预期兑现轨迹；
   - pre-trade check。

本阶段才建设完整前端、任务队列、模拟持仓或复杂 V1。产品壳和模型复杂度不能反向证明 capability passed。

## 7. 里程碑依赖关系

```text
M0 runtime trust / clean integration
 ├─→ M1 provider qualification
 └─→ M2 G1 canonical runtime
        → M3 G1 real Gate

M1 qualification + M2 canonical contract
        → M4 G2 dossier quality
        → M4.5 deterministic growth diagnostic
        → M5 strong baseline / Council A-B / InvestmentThesis
        → G2 capability passed
        → M6 G3 runtime
        → M7 productization and V1
```

允许并行：

- M0 与 M1 的只读 qualification 设计；
- G1 建设期间完善 M4/M4.5 spec；
- G2 前置修复期间准备 golden cases。

禁止并行放行：

- G1 未通过时宣称 G2 passed；
- M4.5 未冻结输入时运行最终 G2 A/B；
- G2 未通过时实现 G3 runtime；
- provider 未 qualification 时进入正式计算；
- V1 复杂模型阻塞当前 V0 与 M5。

## 8. 全局执行规则

### 8.1 Change 生命周期

```text
OpenSpec proposal/design/spec/tasks
→ RED test / failure evidence
→ minimal implementation
→ focused tests
→ full relevant tests
→ strict validation
→ independent review
→ archive
→ commit
→ merge/main verification
→ rolling handoff
```

### 8.2 Capability Gate 规则

- archive 不等于 capability passed；
- mock/fixture 不等于真实 Gate；
- branch/worktree 代码不等于 main 能力；
- tests passed 不等于 provider runtime 可用；
- deterministic calculator 可运行不等于投资结论可信；
- G1 未通过不能宣布 G2 passed；
- G2 未通过不能启动 G3 runtime。

### 8.3 数据源规则

- Longbridge/LongPort 先 qualification，再 adapter，再 production；
- 文档映射不等于 A 股 runtime coverage；
- 未验证 fallback 不进入 ranking、diagnostic 或 Gate；
- 字段缺失区分 `record_not_found/source_failed/invalid_value/permission_denied/not_evaluated`；
- provider metadata 随 canonical snapshot/dossier/diagnostic 传递；
- 公司事实、市场预期和用户假设物理分区；
- 不用多个品牌或文档伪造多源冗余。

### 8.4 Growth Diagnostic 规则

- deterministic engine 不调用 LLM；
- formula version、input hash、assumption hash 必须保存；
- 用户确认假设不可伪装为公司事实；
- V0 默认 `decision_grade=diagnostic`；
- `not_evaluable` 是合法结果；
- 两个估值锚差异过大时展示分歧；
- 不输出机械交易建议；
- 不进入当前 G1 排序；
- A/B 两条路径共享相同 artifact。

### 8.5 当前停止规则

- 没有用户授权的真实 LLM/成本，不运行 live experiment；
- weak/strong model id 相同，不运行正式 A/B；
- ticker/features/prompt/dossier/diagnostic 不冻结，不运行 A/B；
- f3c/f3e worktree dirty closure 未核清，不宣称完成；
- G1 provider Gate blocked，不用 mock 解锁；
- provider qualification 未通过，不接入正式链路；
- diagnostic 依赖 silent default，停止计算；
- Council 没有稳定增量，执行回退；
- G2 未通过，不实现 G3 runtime；
- 为追赶外部项目引入无必要依赖，停止并重新评估。

## 9. OpenSpec child change 拆分建议

| 里程碑 | 建议 change | 单一可验证目标 |
|---|---|---|
| M0 | `f3c-r1-crosstalk-root-cause` | 受控实验与根因证据闭环 |
| M0 | `f3e-provider-schema-compatibility` | provider 响应结构兼容性 |
| M0 | `g2-mainline-fallback-integration` | 干净 mainline fallback integration |
| M1 | `a-share-provider-qualification` | A 股字段级 runtime probe |
| M1 | `provider-contract-and-provenance` | 字段级来源与状态合同 |
| M2 | `g1-canonical-snapshot-sync` | canonical snapshot |
| M2 | `g1-provider-batch-adapter` | 批量与字段级 merge |
| M2 | `g1-staged-screening-runtime` | 真正 staged fetch |
| M2 | `g1-provider-health-and-failure-visibility` | provider 可观测性 |
| M3 | `g1-300-sample-validation` | 样本覆盖与失败隔离 |
| M3 | `g1-full-market-performance-cost` | 全市场性能与成本 |
| M3 | `g1-top20-style-review` | 用户风格 Gate |
| M4 | `g2-evidence-dossier-quality` | dossier 事实质量 |
| M4 | `g2-source-aware-dossier` | provenance 与多源并列 |
| M4.5 | `g2-growth-expectation-contract` | contract、假设与 golden cases |
| M4.5 | `g2-growth-expectation-v0-engine` | 确定性双锚与 reverse 求解 |
| M4.5 | `g2-growth-expectation-dossier-integration` | dossier/Thesis/A-B 接入 |
| M5 | `g2-strong-single-agent-baseline` | 强单 Agent 基线 |
| M5 | `g2-council-ab-evaluation` | 公平 A/B 与盲评 |
| M5 | `g2-investment-thesis-interface-and-closure` | 稳定 Thesis 与 G2 closure |
| M6 | `g3-holding-domain-model` | 持仓与合同领域模型 |
| M6 | `g3-contract-lifecycle` | 用户确认生命周期 |
| M6 | `g3-monitor-signal-and-evaluator` | Thesis 与预期兑现监控 |
| M6 | `g3-shadow-mode` | 历史回放与四周 shadow |

每个 change 必须：

- 引用对应 umbrella；
- 只推进一个主要 Gate；
- 有明确 RED/green evidence；
- 可独立 review、archive 和 commit；
- 完成后生成 rolling handoff。

## 10. 当前最近执行顺序

新增 PRD 不改变当前最近执行顺序。

```text
1. 收口 f3c/f3e dirty worktree 的真实状态
2. 独立 review g2-integration-mainline@f47db88
3. 决定 merge/repair/hold
4. 更新 main 与 OpenSpec baseline
5. 推进 M1/M2
6. 在 M4 数据合同稳定后启动 M4.5
```

当前不要直接开始：

- `g2-growth-expectation-v0-engine`；
- 最终 Council A/B；
- G3 runtime；
- Growth diagnostic UI；
- V1 reverse DCF。

## 11. 下一次会话入口

### 11.1 M0 入口

```bash
cd /Users/admin/Documents/trade-agent
git status --short --branch
git log -1 --oneline main
git worktree list
openspec list --json

git -C .worktrees/f3c-harness-mainline status --short --branch
git -C .worktrees/f3c-harness-mainline log -5 --oneline

git -C .worktrees/g2-integration-mainline status --short --branch
git -C .worktrees/g2-integration-mainline log -5 --oneline
```

必读：

- `design/m0-g2-trust-foundation-handoff-2026-08-03.md`
- f3c worktree 内最新 dynamic closure handoff
- G2 integration branch 的 archived change 与 tests

### 11.2 M4.5 未来入口

只有满足以下条件才创建首个 M4.5 child：

- M0 已形成可信 mainline baseline；
- M4 dossier 字段、单位、状态和 assumption 分区已冻结；
- PRD 仍保持 V0 diagnostic scope；
- OpenSpec umbrella strict validation 通过。

第一个 child 应为：

```text
g2-growth-expectation-contract
```

不能直接从 calculator 实现开始。

## 12. Suggested skills

- `handoff`：每个 child 后生成 dated rolling handoff；
- `openspec-propose`：创建独立 child change；
- `openspec-apply-change`：实现已确认 change；
- `openspec-archive-change`：归档已完成 change；
- `superpowers:using-git-worktrees`：隔离实现 worktree；
- `superpowers:test-driven-development`：实现 deterministic engine 和 runtime 修复；
- `superpowers:verification-before-completion`：完成前验证；
- `superpowers:requesting-code-review`：独立 review；
- `gitnexus-impact-analysis`：修改 dossier、InvestmentThesis 或公共数据层前评估 blast radius；
- `gitnexus-debugging`：定位串台、缓存和 provider 失败。

## 13. 参考文件

- [three-goal-capability-roadmap.md](/Users/admin/Documents/trade-agent/design/three-goal-capability-roadmap.md)
- [total-design.md](/Users/admin/Documents/trade-agent/design/total-design.md)
- [architecture-decisions.md](/Users/admin/Documents/trade-agent/design/architecture-decisions.md)
- [capability-gate-and-execution-handoff-2026-08-03.md](/Users/admin/Documents/trade-agent/design/capability-gate-and-execution-handoff-2026-08-03.md)
- [m0-g2-trust-foundation-handoff-2026-08-03.md](/Users/admin/Documents/trade-agent/design/m0-g2-trust-foundation-handoff-2026-08-03.md)
- [growth-expectation-capitalization-prd-2026-08-04.md](/Users/admin/Documents/trade-agent/design/growth-expectation-capitalization-prd-2026-08-04.md)
- [tradingagents-cn-comparative-assessment-2026-08-03.md](/Users/admin/Documents/trade-agent/design/tradingagents-cn-comparative-assessment-2026-08-03.md)
- [longbridge-a-share-data-field-mapping.md](/Users/admin/Documents/trade-agent/design/longbridge-a-share-data-field-mapping.md)
- [longport-a-share-data-field-mapping.md](/Users/admin/Documents/trade-agent/design/longport-a-share-data-field-mapping.md)
- [G2 umbrella proposal](/Users/admin/Documents/trade-agent/openspec/changes/g2-deep-investment-thesis/proposal.md)
- [G2 umbrella design](/Users/admin/Documents/trade-agent/openspec/changes/g2-deep-investment-thesis/design.md)
- [G2 umbrella tasks](/Users/admin/Documents/trade-agent/openspec/changes/g2-deep-investment-thesis/tasks.md)
- [InvestmentThesis spec](/Users/admin/Documents/trade-agent/openspec/changes/g2-deep-investment-thesis/specs/investment-thesis/spec.md)
- [data-minimum-contract](/Users/admin/Documents/trade-agent/openspec/specs/data-minimum-contract/spec.md)

## 14. 最终执行原则

```text
先证明输入可信，
再建立确定性分析，
再比较 Agent 形态，
再发布 Thesis，
最后建设持仓纪律和产品界面。
```

新增成长预期资本化诊断强化了 G2 的内容深度，但不改变当前最近执行入口，也不允许以更复杂的估值模型掩盖 runtime trust、数据质量和真实 Gate 尚未关闭的问题。
