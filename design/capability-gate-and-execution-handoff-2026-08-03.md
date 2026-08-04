# trade-agent Capability Gate 与完整执行 Handoff

> 日期：2026-08-03
>
> 类型：永久性总 handoff
>
> 适用范围：G1「快」→ G2「深」→ G3「拿得住」全部后续开发
>
> 当前核验基线：`main@dd52d11`
>
> 关联细化 handoff：`design/m0-g2-trust-foundation-handoff-2026-08-03.md`

## 1. 本文件的用途

本文件保存稳定的项目推进方向、能力 Gate、里程碑顺序和 child change 拆分原则。

它不替代：

- `design/three-goal-capability-roadmap.md`：产品目标与 Capability Gate 第一参考源；
- `design/total-design.md`：总体设计与第一性原理；
- `design/architecture-decisions.md`：跨 change 架构决策；
- 各个 OpenSpec proposal/design/spec/tasks：具体 change 的执行合同；
- rolling handoff：某次开发完成后的动态 baseline、测试、产物和 blocker。

每个 child change 完成后，应单独生成新的 dated rolling handoff，记录：

```text
当前分支 / worktree / HEAD
上一 child 的实现、review、archive 和 commit 证据
真实运行产物
剩余 blocker
下一 child
exact commands
```

不能用本文件中的静态路线替代动态状态核验。

## 2. 当前真实基线（2026-08-03 核验）

### 2.1 Git 与 worktree

```text
主工作区：
  /Users/admin/Documents/trade-agent
  branch: main
  HEAD: dd52d11

f3c mainline：
  /Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline
  branch: f3c-harness-mainline
  HEAD: 1984ffc

旧 stacked f3c worktree：
  /Users/admin/Documents/trade-agent-f3c-strong-model-control
  branch: codex/f3c-strong-model-control
  HEAD: f83bb85
```

当前主工作区存在一个未跟踪文件：

```text
design/tradingagents-cn-comparative-assessment-2026-08-03.md
```

该报告应作为独立文档提交，不与 runtime change 混合。

### 2.2 OpenSpec 状态

当前 main 上可见的 active umbrella/child：

| Change | 当前状态 | 真实含义 |
|---|---:|---|
| `f3c-r1-crosstalk-root-cause` | 5/17 | 前置诊断尚未收口 |
| `g1-4-data-source-resilience` | 0/48 | runtime 修复存在，但真实样本 Gate 未完成 |
| `g1-fast-personal-value-screening` | 6/16 | G1 umbrella 仍未通过 |
| `g2-deep-investment-thesis` | 0/23 | G2 umbrella 不能视为完成 |
| `g3-holding-discipline` | 0/29 | 仅允许设计，runtime 锁定 |

`g2-deep-investment-thesis@daf2111` 与 `f3c-harness-mainline@1984ffc` 不是 main 已合并内容。不能把 branch 上的工程提交写成 main 的 capability 事实。

### 2.3 能力状态

```text
G1：未通过
  - D1-D6 数据韧性 runtime 修复已存在
  - 300+ 多行业真实样本 Gate 未通过
  - 全市场性能/成本/Top 20 人工复核未完成

G2：工程基础存在，但未通过
  - runtime trust、审计链、dossier、质量门、baseline、A/B harness、
    InvestmentThesis 代码主要存在于独立 G2 分支
  - f3c 真实强弱模型实验未收口
  - 真实 dossier、双路径、成本和盲评证据未完成

G3：未开始 runtime
  - HoldingContract、状态机和 shadow mode 继续锁定
```

## 3. 目标是否发生偏移

产品目标没有改变：

```text
G1 快：个人价值风格筛选
    ↓
G2 深：可信 InvestmentThesis
    ↓
G3 拿得住：持仓纪律副驾驶
```

但工程实现存在三处需要校正的偏移。

### 3.1 G1 的“快”需要重新落地

G1 不应继续理解为“每次运行时更快地调用更多外部接口”。

应修正为：

```text
provider 同步
→ normalized raw response
→ canonical snapshot
→ 本地漏斗筛选
→ L2 成本闸门
```

TradingAgents-CN 的对照报告证明，长期快筛更适合建立可信本地数据底座，再在本地快照上完成查询和排序。

当前不立即引入 MongoDB、Redis 或完整数据平台。先使用现有文件缓存实现：

- snapshot manifest；
- source/provider；
- `as_of`；
- `profile_version`；
- 字段状态；
- failure summary；
- snapshot hash。

只有 warm-cache 性能实测证明文件缓存不足时，才评估 SQLite 或其他本地存储。

### 3.2 G2 不应继续以 Agent 形态扩张代替证据

G2 的目标仍是可信 `InvestmentThesis`，不是：

- Agent 数量更多；
- 辩论轮次更多；
- Prompt 更像投资大师；
- 强制输出目标价；
- 永远输出 bullish/bearish。

下一阶段必须优先完成：

```text
f3c 根因实验
→ G2 干净 integration review
→ 真实 dossier snapshot
→ strong single-agent / Council A/B
→ 盲评与回退决策
```

### 3.3 G3 不能被外部项目的模拟交易能力提前带偏

模拟账户可以作为未来 G3 的纪律验证沙盒，但它不等于 `HoldingContract`。

G2 通过前不实现：

- 持仓状态机；
- 自动持仓建议；
- 模拟交易主链；
- 券商连接；
- 自动下单。

## 4. 外部借鉴的吸收边界

### 可以吸收

- provider 配置和健康度；
- 定期数据同步；
- 本地 canonical snapshot；
- 任务状态、节点进度、耗时、token、成本；
- 报告和 Thesis 历史；
- evidence/counter-evidence diff；
- G1 数据 coverage 与 failure distribution。

### 不直接引入

- 完整 TradingAgents-CN；
- LangGraph/LangChain 作为本项目核心编排；
- Bull/Bear 强制立场 Prompt；
- 强制目标价；
- LLM/API 失败时默认“持有”；
- 未经授权直接复制 `app/` 或 `frontend/`；
- 现在就建设模拟交易和完整前端。

## 5. 总体开发里程碑

## M0：G2 前置可信基础收口

### 目标

完成 f3c 受控实验与 G2 工程分支的干净整合，使后续 G2 真实 A/B 建立在可审计、可失败闭环的基础上。

### 主要 change / 小目标

1. `f3c-r1-crosstalk-root-cause`
   - rebase 到最新 main；
   - 完成真实 weak/strong controlled experiment；
   - 判断 prompt、模型/provider stack、混合因素或新假设；
   - 不稳定时保持 active。

2. 可能的后续 `f3d-*` 或 `f3e-*`
   - 只根据 f3c 真实实验结论创建；
   - 不预先修 Prompt 或切换模型；
   - 每个修复独立验证串台、grounding 和信息增量。

3. G2 clean integration review
   - 从 f3c 合并后的最新 main 新建干净 G2 branch；
   - 分组移植并 review G2 runtime trust/audit 与 baseline/A-B/Thesis；
   - 不整体 merge stacked G2 branch。

### 放行条件

- f3c 有真实产物和明确判读；
- 显性串台为 0；
- 实验输入、模型、ticker、features、prompt、provider 可追溯；
- f3c 结果完成独立 review；
- G2 代码在干净 branch 上测试和 strict validation 通过。

### 不放行的条件

- 同一模型冒充 weak/strong；
- 使用 fixture 冒充 live；
- ticker/features 错配；
- 实验结果不稳定却强行 archive；
- G2 branch 整体带入旧 f3c/G1 artifacts。

详细执行见：

`design/m0-g2-trust-foundation-handoff-2026-08-03.md`

## M1：A 股 Provider Qualification

### 目标

确认 Longbridge/LongPort 是否能以字段级、可追溯方式补强 G1/G2 数据，不直接接入生产 ranking。

### 主要 change / 小目标

1. `a-share-provider-qualification`
   - 对 5 只代表性 A 股执行只读 probe；
   - 验证 `static_info`、`quote`、`calc_indexes`、历史 K 线、财报、估值历史；
   - 输出 raw response、字段差异、单位、报告期和权限证据。

2. `provider-contract-and-provenance`
   - 定义 `provider_family`、provider、method、market、as_of、report_period、unit、raw_field、field_status；
   - 定义 `record_not_found/source_failed/permission_denied/invalid_value/not_evaluated`；
   - 明确 Longbridge 文档和 LongPort SDK 不计为两个独立 provider。

### 放行条件

- 至少 5 只不同类型 A 股完成字段级 probe；
- 关键字段单位和报告期规则固定；
- 与现有 AkShare/东财/同花顺/百度数据源完成字段级差异报告；
- 无未验证字段进入 ranking 或 Gate。

## M2：G1 Canonical Snapshot 与分层筛选 Runtime

### 目标

让 G1 的“快”变成真正的本地快照筛选，而非全量逐股在线取数。

### 主要 change / 小目标

1. `g1-canonical-snapshot-sync`
   - 建立原始数据与 canonical snapshot 的边界；
   - 增加 snapshot manifest、source-set hash、as-of 和字段状态；
   - 保留现有消费者字段结构，metadata 先以 sidecar 方式加入；
   - 缓存失败和降级必须可见。

2. `g1-provider-batch-adapter`
   - 支持批量 provider 调用；
   - LongPort `calc_indexes/static_info` 先 shadow；
   - 不把完整维度 first-non-empty 当成成功；
   - 支持字段级 merge 和冲突标记。

3. `g1-staged-screening-runtime`
   - Stage A：basic/current valuation；
   - Stage B：financials/risk；
   - Stage C：历史估值/K 线；
   - 使用 ticker 集合缩小证据证明 fetch calls 随漏斗下降。

4. `g1-provider-health-and-failure-visibility`
   - 统计 source failure、permission、rate limit、manual action、degraded；
   - 单股失败不阻断批次；
   - 不使用 silent default。

### 重要边界

LongPort 暂不替代：

- 历史换手率；
- 质押率；
- 审计意见；
- 未验证的完整 F-Score 财务科目。

## M3：G1 真实 Capability Gate

### 目标

证明 G1 能从全市场形成可用、可解释、成本可控的候选池。

### 主要 change / 小目标

1. `g1-300-sample-validation`
   - 固定 300+ 只、多行业、多风险类型样本；
   - 验证字段覆盖、失败隔离、行业覆盖和 verdict 分布；
   - 失败时保持 `blocked`。

2. `g1-full-market-performance-cost`
   - warm-cache 全市场运行；
   - 验证 ≤15 分钟、关键字段可用率 ≥95%、L2 成本 ≤¥2；
   - 落盘完整漏斗、failure summary 和 usage。

3. `g1-top20-style-review`
   - 冻结 ScreeningProfile 与 run；
   - 用户复核 Top 20；
   - 至少 70% 被判断为值得进一步研究；
   - 不凑数、不降低门槛。

### 放行条件

所有 G1 技术 Gate、产品 Gate 和 evidence bundle 同时通过，才可正式标记 G1 passed。

## M4：G2 Evidence Dossier Quality

### 目标

让 G2 研究输入本身具备来源、报告期、新鲜度、降级状态和角色可消费性。

### 主要 change / 小目标

1. `g2-evidence-dossier-quality`
   - 主营、同行、研报、capex proxy 数据质量；
   - 公司事实与市场预期物理分区；
   - 关键字段 provenance 完整。

2. `g2-source-aware-dossier`
   - 将 canonical snapshot 和 LongPort qualification 结果接入 dossier；
   - 多源字段并列保存，不静默覆盖；
   - 失败原因从 generic reason 恢复为可审计状态。

### 放行条件

- 高严重度凭空数字为 0；
- 关键事实追溯率 ≥95%；
- dossier snapshot 可以冻结、复现和比较；
- 数据不足能输出 degraded/insufficient_data。

## M5：G2 InvestmentThesis 与 A/B Closure

### 目标

证明 Council 相比强单 Agent 是否产生稳定的信息增量，并发布稳定 `InvestmentThesis`。

### 主要 change / 小目标

1. `g2-strong-single-agent-baseline`
   - 冻结强单 Agent 输入、模型、prompt、预算和输出；
   - 形成 baseline。

2. `g2-council-ab-evaluation`
   - 同 ticker、同 dossier、同工具、可比预算；
   - 8-10 只多类型股票；
   - 匿名评分与成本记录。

3. `g2-investment-thesis-interface-and-closure`
   - 发布稳定 `InvestmentThesis`；
   - evidence/counter-evidence/assumptions/risks/key_variables/
     what_would_change_my_mind/pending_verification/quality_status；
   - 形成 G2 evidence bundle。

### 放行条件

- Council 实质增量 ≥70%；
- 用户盲评 Council 更好 ≥60%；
- Council 明显更差 ≤20%；
- 未通过时回退为强单 Agent + DA/事实检查器 + Synthesizer；
- G2 整体 review 通过后才能放行 G3。

## M6：G3 Holding Discipline Runtime

### 目标

把通过 G2 的 `InvestmentThesis` 转换为用户确认的持有纪律，不自动交易。

### 主要 change / 小目标

1. `g3-holding-domain-model`
   - `HoldingsRepository`、Holding、HoldingContract draft；
   - CandidateWatchlist 与真实持仓解耦。

2. `g3-contract-lifecycle`
   - 用户输入成本、仓位、回撤、复核周期、冷静期；
   - draft → user-confirmed → active。

3. `g3-monitor-signal-and-evaluator`
   - price review 与 thesis-break 分离；
   - Green/Yellow/Red/Blue/Rebalance Review。

4. `g3-shadow-mode`
   - 历史场景回放；
   - 3-5 只真实或模拟持仓连续四周；
   - 只记录系统会如何提示，不执行交易。

## M7：Gate 通过后的产品化

### 目标

把已经验证的能力做成可持续使用的工作台。

### 主要 change / 小目标

1. `g1-funnel-observability-ui`
   - 为什么进入、为什么排除、哪里降级。

2. `data-health-and-provider-ops`
   - provider health、字段 coverage、同步历史、失败恢复。

3. `g2-thesis-history-and-export`
   - Thesis version diff；
   - evidence/counter-evidence diff；
   - Markdown/PDF 导出。

4. `task-progress-and-run-history`
   - 节点级进度；
   - token、耗时、成本；
   - 可恢复失败。

5. `g3-holding-review-ui`
   - HoldingContract；
   - 复核状态；
   - pre-trade check。

本阶段才考虑前端、任务队列、模拟持仓等平台能力。不能用产品壳的完整度反向宣称 G1/G2/G3 已通过。

## 6. 全局执行规则

### 6.1 Change 生命周期

```text
OpenSpec proposal/design/spec/tasks
→ RED test / failure evidence
→ minimal implementation
→ focused tests
→ full relevant tests
→ independent review
→ archive
→ commit
→ rolling handoff
```

### 6.2 Capability Gate 规则

- archive 不等于 capability passed；
- mock/fixture 不等于真实 Gate；
- branch 上的代码不等于 main 已具备能力；
- 单测全绿不等于真实 provider 可用；
- fallback 非空不等于字段 usable；
- G1 未通过不能宣布 G2 passed；
- G2 未通过不能启动 G3 runtime。

### 6.3 数据源规则

- Longbridge/LongPort 先 qualification，再 adapter，再 production；
- 未验证 fallback 不得进入 ranking；
- 字段缺失必须区分 `source_failed`、`record_not_found`、`invalid_value`；
- provider 失败不能转换为默认安全值；
- provider metadata 必须随 canonical snapshot 传递；
- 不用多个平台文档伪造多源冗余。

### 6.4 当前停止规则

- 没有用户授权的真实 LLM/成本，不运行 live experiment；
- weak/strong model id 相同，不运行 A/B；
- ticker/features/prompt/dossier 不冻结，不运行 A/B；
- G1-4 provider Gate blocked，不用 mock 解锁；
- f3c 结果不稳定，不 archive；
- Council 没有稳定增量，回退；
- G2 未通过，不实现 G3 runtime；
- 为追赶外部项目而引入无必要依赖，停止并重新评估。

## 7. 下一次会话入口

首个大里程碑的详细执行文档：

`design/m0-g2-trust-foundation-handoff-2026-08-03.md`

启动核验：

```bash
cd /Users/admin/Documents/trade-agent
git status --short --branch
git log -1 --oneline main
git worktree list
openspec list --json
```

## 8. Suggested skills

后续会话按任务选择：

- `handoff`：生成 dated rolling handoff；
- `openspec-apply-change`：实现已确认的 child change；
- `openspec-archive-change`：归档已完成 change；
- `superpowers:using-git-worktrees`：创建隔离 worktree；
- `superpowers:test-driven-development`：实现 runtime 修复；
- `superpowers:verification-before-completion`：完成前验证；
- `superpowers:requesting-code-review`：请求独立 review；
- `gitnexus-impact-analysis`：修改公共数据层前评估 blast radius；
- `gitnexus-debugging`：定位串台、缓存、provider 失败；
- `source-command-opsx-propose`：创建新的 OpenSpec change。

## 9. 参考文件

- [three-goal-capability-roadmap.md](/Users/admin/Documents/trade-agent/design/three-goal-capability-roadmap.md)
- [total-design.md](/Users/admin/Documents/trade-agent/design/total-design.md)
- [architecture-decisions.md](/Users/admin/Documents/trade-agent/design/architecture-decisions.md)
- [capability-gate-and-execution-handoff.md](/Users/admin/Documents/trade-agent/design/capability-gate-and-execution-handoff.md)
- [tradingagents-cn-comparative-assessment-2026-08-03.md](/Users/admin/Documents/trade-agent/design/tradingagents-cn-comparative-assessment-2026-08-03.md)
- [longbridge-a-share-data-field-mapping.md](/Users/admin/Documents/trade-agent/design/longbridge-a-share-data-field-mapping.md)
- [longport-a-share-data-field-mapping.md](/Users/admin/Documents/trade-agent/design/longport-a-share-data-field-mapping.md)
- [data-minimum-contract/spec.md](/Users/admin/Documents/trade-agent/openspec/specs/data-minimum-contract/spec.md)
- G2 旧 Master Handoff 当前仅存在于 `g2-deep-investment-thesis@daf2111`：
  `design/g2-deep-investment-thesis-master-handoff.md`。在 clean integration 前不要把该 branch-only
  文件当作 main 已具备的导航资产。
