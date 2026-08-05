# trade-agent Capability Gate 与完整执行 Handoff

> 日期：2026-08-05
>
> 类型：永久性总 Handoff / 最新完整执行规划
>
> 状态：取代 `capability-gate-and-execution-handoff-2026-08-04.md` 成为最新
> dated 执行 Handoff；08-04 及更早版本保留为历史快照
>
> 产品能力第一参考源：`design/three-goal-capability-roadmap.md`
>
> 架构决策：`design/architecture-decisions.md`
>
> 当前 main integration baseline：
> `bce6bc6 merge: integrate g1 field qualification canonical promotion`
>
> 当前直接执行入口：
> `design/m1-m2-g1-provider-canonical-runtime-rolling-handoff-2026-08-05-r1.md`

## 1. 本文件的职责

本文件是当前开发的阶段性里程碑母规划，记录：

- G1「快」→ G2「深」→ G3「拿得住」的稳定产品方向；
- M0–M7 的目标、依赖、状态、放行条件和停止条件；
- 当前 main、worktree、OpenSpec、真实 evidence 的实际位置；
- 当前正在推进的里程碑子轨；
- 哪些工程已完成，哪些 capability 尚未成立；
- 下一窗口可以直接执行的合理工作；
- 何时需要暂停、review、repair、archive 或进入下一 milestone。

它不替代：

- `three-goal-capability-roadmap.md` 的产品 Goal/Gate；
- `total-design.md` 的第一性原理和原始架构；
- `architecture-decisions.md` 的跨 change 决策；
- OpenSpec proposal/design/spec/tasks；
- child rolling handoff；
- 独立 code review；
- live provider/LLM 运行产物；
- capability evidence bundle。

## 2. 文档治理

### 2.1 总 Handoff

总 Handoff 负责稳定的 M0–M7 阶段规划。

在以下情况新建 dated 总 Handoff，不原位覆盖历史：

- main baseline 明显变化；
- milestone 真实状态发生跨阶段变化；
- 执行主轨切换；
- 新需求改变阶段依赖或 Gate；
- 旧总 Handoff 的下一入口已经失效。

本次 08-05 版本没有改变 G1/G2/G3 目标或 M0–M7 顺序，主要更新：

- G2 fallback integration 已进入 main；
- M1/M2 provider/canonical 工程已进入 main；
- provider health 与 field promotion 的 active 状态；
- M0 与 M1/M2 两条子轨的正确区分；
- canonical promotion 的剩余合同 blocker；
- 下一窗口直接任务。

### 2.2 Rolling Handoff

Rolling handoff 必须声明：

```text
所属总 Handoff
所属 milestone / 子轨
workspace / branch / worktree / HEAD
OpenSpec active/archive 状态
实现与未实现边界
focused/full tests
真实运行 evidence
独立 review
archive / commit / merge
剩余 blocker
下一 child
exact commands
```

Rolling handoff 不得：

- 重新命名或重排 M0–M7；
- 把局部子轨描述成全局进度；
- 用 tasks complete、测试或 merge 替代 capability pass；
- 把历史 evidence 冒充当前代码的 live evidence。

## 3. 当前真实基线

### 3.1 Main runtime/integration baseline

```text
path:   /Users/admin/Documents/trade-agent
branch: main
runtime/integration baseline:
        bce6bc644333d09e7339e005edf35dfcd6a036b2
        bce6bc6 merge: integrate g1 field qualification canonical promotion
remote before this docs-only closure:
        ahead of origin/main by 34 commits
```

本文件和新的 M1/M2 rolling handoff 将作为一个 docs-only closure 提交。该提交
只推进文档 HEAD，不改变上述 runtime/integration baseline。下一窗口仍必须先运行
`git status --short --branch` 和 `git log -5 --oneline` 获取最终 docs commit。

### 3.2 Worktree / branch

#### f3c mainline

```text
path:   /Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline
branch: f3c-harness-mainline
HEAD:   a041314
main ancestor: no
status: dirty
```

包含未提交的 f3c/f3e archive、runtime scripts、tests、live artifacts、
debate/watchlist 和 dynamic closure handoff。不能描述成 main 能力或已完成
closure。

#### 旧 stacked f3c

```text
path:   /Users/admin/Documents/trade-agent-f3c-strong-model-control
branch: codex/f3c-strong-model-control
HEAD:   f83bb85
main ancestor: no
status: clean
```

只作为历史/选择性移植来源，不整体合并。

#### G2 integration

```text
path:   /Users/admin/Documents/trade-agent/.worktrees/g2-integration-mainline
branch: codex/g2-integration-mainline
HEAD:   f47db88
main ancestor: yes
status: clean
```

`g2-mainline-fallback-integration` 已归档并进入 main。该工程基础不等于 G2
capability passed。

#### 历史 provider adapter

```text
path:   /Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter
branch: codex/g1-provider-batch-adapter
HEAD:   a6e6699
main ancestor: no
status: clean
```

当前 main 已通过另一条 integration 提交链包含 provider adapter。该 worktree
只作历史对照，不作为恢复入口或整体合并来源。

#### 已清理的 provider integration

```text
path:   /Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter-mainline
state:  merged to main, worktree removed, local branch deleted
```

### 3.3 当前 OpenSpec

| Change | 状态 | Tasks | 真实含义 |
|---|---|---:|---|
| `g1-provider-health-and-failure-visibility` | complete / active | 19/19 | 工程冻结，已 review，待 archive |
| `g1-field-qualification-canonical-promotion` | complete / active | 12/12 | 已进入 main，待独立 review/repair/archive |
| `g2-strong-single-agent-fallback` | complete / active | 12/12 | fallback foundation，不是 A/B 或 G2 pass |
| `g2-deep-investment-thesis` | in-progress | 0/27 | G2 umbrella，含 M4.5 |
| `f3c-r1-crosstalk-root-cause` | in-progress | 5/17 | M0 前置诊断未闭 |
| `g1-4-data-source-resilience` | in-progress | 0/48 | real sample/provider Gate 未闭 |
| `g1-fast-personal-value-screening` | in-progress | 6/16 | G1 umbrella 未通过 |
| `g3-holding-discipline` | in-progress | 0/29 | 设计可继续，runtime 锁定 |

Active change 的 tasks 数量、目录存在或 commit 都不能替代 archive/canonical
spec sync/independent review。

### 3.4 Fresh verification baseline

当前 main 已记录：

```text
full pytest:
  1292 passed, 1 skipped in 61.02s

compileall:
  passed

openspec validate g1-provider-health-and-failure-visibility --strict:
  passed

openspec validate g1-field-qualification-canonical-promotion --strict:
  passed

git diff --check:
  passed
```

该证据只证明工程 checkout 的自动化基线。项目没有 `package.json`，因此没有
可运行的 `npm run lint`。

## 4. 稳定产品目标

```text
G1 快：个人价值风格筛选
    ↓ Capability Gate
G2 深：可信 InvestmentThesis
    ↓ Capability Gate
G3 拿得住：持仓纪律副驾驶
```

### G1「快」

```text
provider 同步
→ normalized raw response
→ canonical snapshot
→ 本地漏斗筛选
→ L2 成本闸门
→ 符合个人价值风格的可信候选池
```

目标不是更多因子、更多 provider 或短期涨跌预测。

### G2「深」

```text
可信事实
+ 可审计推断
+ 明确假设
+ 反证/风险/关键变量
+ 什么情况下改变判断
= InvestmentThesis
```

Multi-Agent 是候选形态。若 Council 没有稳定增量，回退：

```text
强单 Agent + 独立 DA/事实检查器 + Synthesizer
```

### G3「拿得住」

```text
passed InvestmentThesis
→ 用户确认 HoldingContract
→ 区分价格扰动、预期兑现偏差和 Thesis 破坏
→ 提醒用户按纪律复核
```

不连接券商、不自动下单，用户保留最终判断。

## 5. 当前里程碑总览

| Milestone | 当前状态 | 已有 | 关键缺口 | 是否放行 |
|---|---|---|---|---|
| M0 G2 前置可信基础 | 部分完成 | fallback integration 已入 main | f3c/f3e dirty closure、live 根因证据 | 否 |
| M1 Provider Qualification | 工程合同完成，能力未过 | qualification/provenance archive | 当前 completed live run、候选 provider、shadow coverage | 否 |
| M2 Canonical Runtime | 工程基础前进 | canonical/adapter、health/promotion | contract repair、archive、真实 snapshot、consumer/staged runtime | 否 |
| M3 G1 Capability Gate | 未开始真实验收 | umbrella 前置 6/16 | 300+、全市场、性能/成本、Top 20 | 否 |
| M4 G2 Dossier Quality | 未启动新 child | research dossier foundation | source-aware quality、状态/单位/报告期 | 否 |
| M4.5 Growth Diagnostic V0 | 规划完成 | PRD + umbrella | contract、engine、integration | 否 |
| M5 Thesis 与 A/B | foundation only | strong fallback foundation | 同输入 A/B、盲评、稳定 Thesis | 否 |
| M6 G3 Runtime | 锁定 | design/umbrella | G2 passed、domain/lifecycle/shadow | 否 |
| M7 产品化与 V1 | 未启动 | 部分旧 Docker 骨架 | capability passed 后的 UI/ops/V1 | 否 |

## 6. M0：G2 前置可信基础收口

### 目标

关闭 f3c/f3e runtime trust 与 clean integration，使后续 dossier、M4.5 和 A/B
建立在可审计、可失败闭环的基础上。

### 当前已完成

- G2 fallback clean integration 已归档并进入 main；
- strong single-agent fallback foundation 已存在；
- f3c harness/live evidence 在独立 worktree 有历史进展；
- f3e bounded schema compatibility 有 worktree 产物。

### 尚缺

- dirty f3c worktree 的 archive/commit/artifact 对齐；
- weak/strong model、ticker/features/prompt/provider/usage 的最终 live 证据；
- f3c root-cause change 的真实 closure；
- current main 上的 OpenSpec/runtime 一致性；
- 不确定结论不得伪装 root cause pass。

### 当前状态

```text
M0: not passed
global blocker: f3c-r1-crosstalk-root-cause 5/17
```

M1/M2 子轨前进不等于 M0 已关闭。

## 7. M1：A 股 Provider Qualification

### 目标

证明 provider 对 A 股消费字段的真实 runtime coverage、单位、报告期、权限、
限流和失败语义；未经 qualification 的字段不得进入 ranking、diagnostic 或 Gate。

### 已完成

- `a-share-provider-qualification` archived；
- `provider-contract-and-provenance` archived；
- 固定五只 A 股 probe plan；
- field-level provenance/status；
- historical baseline/health evidence。

### 尚缺

- 与当前 main 绑定的新 completed live qualification run；
- 当前 policy 下 field eligibility decision；
- AkShare/东财/同花顺/百度当前字段差异报告；
- LongPort/Longbridge runtime qualification；
- M4.5 shadow fields coverage。

### 执行优先级

先验证当前 baseline provider 的关键消费字段。LongPort/Longbridge defer 是执行
优先级调整，不修改 M1 最终放行条件。

### 当前状态

```text
M1: not passed
```

## 8. M2：G1 Canonical Snapshot 与分层筛选 Runtime

### 目标

让 G1 从可信、可复现、failure-visible 的本地 snapshot 运行漏斗，而不是全市场
逐股在线取数。

### 已完成/前进

- `g1-canonical-snapshot-sync` archived；
- `g1-provider-batch-adapter` archived；
- `g1-provider-health-and-failure-visibility` 19/19 active complete；
- `g1-field-qualification-canonical-promotion` 12/12 active complete；
- provider adapter/health/promotion 进入 main。

### 当前合同 blocker

Canonical spec 要求 rejected/failed/conflicted/stale evidence：

```text
canonical value = null
snapshot sidecar 保留 status/reason/provenance
```

当前 promotion 仅把 qualified `promoted_evidence` 传给 snapshot writer。部分
qualified run 中 rejected evidence 可能只留在 `decision.json`，未进入 canonical
`provenance.json`，record 也可能缺字段而不是显式 null。

该问题必须在 promotion child archive 前独立 review 并决定：

- 修复实现以保留全部 evaluated evidence；或
- 显式修改 canonical contract 和 consumer migration。

默认推荐保持已有 failure-visible canonical contract，不弱化它。

### 尚缺

- promotion merged-main 独立 review/repair/re-review；
- health/promotion archive；
- 新 completed live qualification evidence；
- 真实 `decision.json + canonical snapshot`；
- `g1-canonical-snapshot-consumer`；
- `g1-staged-screening-runtime`；
- Stage A/B/C provider calls 随 ticker 漏斗下降的证据。

### 当前状态

```text
M2: not passed
current active execution track: M1/M2 G1 input trust
```

直接执行入口：

```text
design/m1-m2-g1-provider-canonical-runtime-rolling-handoff-2026-08-05-r1.md
```

## 9. M3：G1 真实 Capability Gate

### 目标

证明 G1 能从全市场形成可用、可解释、成本可控、符合用户风格的候选池。

### 必须拆分

1. `g1-300-sample-validation`
   - 300+ 多行业、多风险样本；
   - coverage、failure isolation、行业/verdict 分布；
   - 不通过则 blocked。

2. `g1-full-market-performance-cost`
   - warm-cache 全市场；
   - ≤15 分钟；
   - 关键字段可用率 ≥95%；
   - L2 成本 ≤¥2；
   - 未处理异常为 0；
   - 保存漏斗、failure summary、usage。

3. `g1-top20-style-review`
   - 冻结 ScreeningProfile/run/input；
   - 用户逐只复核 Top 20；
   - ≥70% 值得进一步研究；
   - 不降低门槛凑数。

### 当前状态

```text
M3: not started
G1 capability: not passed
```

M2 consumer/staged runtime 不得与 M3 三个 Gate 合并为巨型 child。

## 10. M4：G2 Evidence Dossier Quality

### 目标

让 G2 输入具备来源、报告期、新鲜度、单位、降级状态、冻结能力和确定性诊断可
消费性。

### 后续 child

1. `g2-evidence-dossier-quality`
2. `g2-source-aware-dossier`
3. `g2-diagnostic-input-contract-foundation`

### 放行条件

- 高严重度凭空数字为 0；
- 关键事实追溯率 ≥95%；
- dossier snapshot 可冻结/复现/比较；
- 公司事实、市场预期、用户假设物理分区；
- 单位/报告期支持确定性计算；
- 数据不足输出 degraded/insufficient/not_evaluable。

### 当前状态

```text
M4: not started as current milestone
```

可继续完善设计，但不得越过 M1/M2 数据资格或以 G2 扩展掩盖 G1 Gate。

## 11. M4.5：Growth Expectation Diagnostic V0

### 定位

属于 G2 deterministic analysis，不是第四个 Goal、不是 Agent 角色、不是当前
G1 ranking 因子。

### Child 顺序

1. `g2-growth-expectation-contract`
   - 输入/输出；
   - `AssumptionSnapshot`；
   - EPV proxy + 成熟期估值交叉锚；
   - reverse 模式；
   - 状态/失败语义；
   - golden cases。

2. `g2-growth-expectation-v0-engine`
   - deterministic，无 LLM；
   - normalized owner earnings；
   - 用户确认 maintenance capex；
   - 双锚；
   - 固定增长率求年限 / 固定年限求增长率；
   - sensitivity；
   - formula/input/assumption/provenance hash。

3. `g2-growth-expectation-dossier-integration`
   - immutable diagnostic；
   - dossier/DA/Thesis；
   - `valuation_expectation`；
   - 两条 A/B 路径共享同一 artifact。

### 前置

- M0 credible mainline baseline；
- M4 dossier 字段/单位/状态/assumption 分区稳定；
- provider 已 qualification；
- PRD 继续保持 V0 diagnostic scope。

### 当前状态

```text
M4.5: planned, no child started
```

不能直接从 calculator 开始，也不能把 V0 接入 G1 hard gate/主排序。

## 12. M5：InvestmentThesis 与 A/B Closure

### 目标

证明 Council 相比强单 Agent 是否有稳定信息增量，并发布包含
`valuation_expectation` 的稳定 InvestmentThesis。

### 必须完成

1. strong-single-agent baseline；
2. Council A/B harness；
3. 8–10 只多类型固定样本；
4. 相同模型、dossier、diagnostic、tools、可比 budget；
5. 匿名评分与成本；
6. InvestmentThesis interface/closure。

### Gate

- Council 实质增量 ≥70%；
- 用户盲评 Council 更好 ≥60%；
- Council 明显更差 ≤20%；
- 审计对齐率 100%；
- 高严重度凭空数字 0；
- 关键事实追溯率 ≥95%；
- 失败时回退强单 Agent + DA/事实检查器 + Synthesizer。

### 当前状态

```text
fallback foundation: complete engineering
final baseline/A-B: not ready
G2 capability: not passed
```

Canonical snapshot 冻结不是最终 A/B 的充分条件；必须先经过 M4 和 M4.5。

## 13. M6：G3 Holding Discipline Runtime

### 前置

- G2 capability passed；
- 稳定 InvestmentThesis；
- `valuation_expectation` 可版本化消费；
- 用户保留最终判断。

### 后续 child

1. `g3-holding-domain-model`
2. `g3-contract-lifecycle`
3. `g3-monitor-signal-and-evaluator`
4. `g3-shadow-mode`

### 当前状态

```text
design/umbrella: available
runtime: locked
```

G2 未 passed 时不实现 G3 runtime。

## 14. M7：Gate 后产品化与 V1

只在相应 capability 通过后推进：

- G1 funnel observability UI；
- data health/provider ops；
- Thesis history/export；
- growth diagnostic interaction；
- growth expectation V1；
- task progress/run history；
- G3 holding review UI。

前端、任务队列、复杂 V1、模拟账户或产品壳不能反向证明 capability 成立。

## 15. 里程碑依赖

```text
M0 runtime trust / clean integration
 ├─→ M1 provider qualification
 └─→ M2 canonical runtime
        → M3 G1 real Gate

M1 qualification + M2 canonical runtime
        → M4 dossier quality
        → M4.5 deterministic growth diagnostic
        → M5 strong baseline / Council A-B / InvestmentThesis
        → G2 capability passed
        → M6 G3 runtime
        → M7 productization / V1
```

### 允许并行

- M0 closure 与 M1/M2 工程准备可在独立子轨推进；
- G1 建设期间可完善 M4/M4.5 spec；
- M0/G2 前置期间可准备 golden cases。

### 禁止并行放行

- M0 dirty worktree 不得描述为 main closure；
- provider 未 qualification 不得进入正式计算；
- M2 未形成真实 snapshot 不得迁移 consumer；
- M3 未通过不得标记 G1 passed；
- M4.5 未冻结不得运行最终 A/B；
- G1 未通过不得宣称 G2 passed；
- G2 未通过不得实现 G3 runtime。

## 16. 全局 change 生命周期

标准顺序：

```text
OpenSpec proposal/design/spec/tasks
→ RED test / failure evidence
→ minimal implementation
→ focused tests
→ full relevant tests
→ strict validation
→ independent review
→ repair / re-review
→ archive
→ commit
→ merge/main verification
→ rolling handoff
```

当前 promotion child 已发生：

```text
implementation/tests → commit → merge → independent review pending
```

这是需修复的生命周期偏差，不是新的标准流程。应在当前 main 上补独立 review、
repair/re-review 和 archive，再形成 closure commit/handoff。

每个 child：

- 只推进一个主要 Gate；
- 引用所属 umbrella/milestone；
- 不跨 Goal 偷带实现；
- 可独立 review/archive/rollback；
- 归档记录真实 evidence；
- fixture/绿测不冒充 capability。

## 17. 数据与证据规则

- provider 文档不等于 A 股 runtime coverage；
- LongPort/Longbridge qualification → adapter → production；
- 不使用未经验证的 fallback；
- `record_not_found`、`source_failed`、`invalid_value`、
  `permission_denied`、`rate_limited`、`not_evaluated` 不混淆；
- canonical snapshot 必须 failure-visible；
- unqualified/failed/conflicted/stale 字段不得静默消失或变默认值；
- provider metadata 随 snapshot/dossier/diagnostic 传递；
- 公司事实、市场预期、用户假设物理分区；
- live evidence 保存 code version、dirty state、run/ticker/input hash；
- secret 不进入 repo 或 evidence。

## 18. 当前最近执行顺序

### 当前唯一直接执行主线：M1/M2 contract closure

```text
1. merged-main 独立 review field qualification/canonical promotion
2. 核验 rejected evidence 的 canonical null/status/provenance
3. 若确认问题，在当前 active child 内更新 spec/tasks 并 TDD repair
4. focused/full tests + strict validation
5. 独立 re-review
6. archive provider health
7. archive field qualification/canonical promotion
8. 生成当前 main 的 completed live qualification evidence
9. 执行真实 promotion，审计 decision + snapshot
10. 创建 g1-canonical-snapshot-consumer
11. 创建 g1-staged-screening-runtime
12. M2 closure 后进入 M3 三个独立 Gate
```

### 并行但不作为本窗口直接任务

- M0 f3c dirty closure；
- M4/M4.5 spec 思考；
- G2 golden cases。

除非用户明确切换子轨，不在同一 child 中混做。

## 19. 下一窗口直接入口

### 推荐任务

对 `g1-field-qualification-canonical-promotion` 做 merged-main 独立只读 review。

### 推荐启动提示

```text
请完整阅读：
1. design/capability-gate-and-execution-handoff-2026-08-05.md
2. design/m1-m2-g1-provider-canonical-runtime-rolling-handoff-2026-08-05-r1.md
3. openspec/changes/g1-field-qualification-canonical-promotion/
4. openspec/changes/archive/2026-08-04-g1-canonical-snapshot-sync/

从当前 main、OpenSpec、实际代码和测试出发，对
g1-field-qualification-canonical-promotion 做独立只读 review。

本轮不修改代码、不 archive、不调用真实 provider、不 stage/commit。
优先核验：
- rejected/failed evidence 是否进入 canonical null/status/provenance；
- source run completeness/count/hash；
- duplicate/unexpected/cross-provider/freshness/time-basis conflict；
- output path/source path escape；
- decision hash 与 CLI policy；
- spec/implementation/test 是否一致。

先按 P0/P1/P2 列 findings，再列通过项和剩余风险，并判断当前 child 是
ready to archive 还是 request changes。
```

### 新窗口起始命令

```bash
cd /Users/admin/Documents/trade-agent
git status --short --branch
git log -5 --oneline --decorate
git worktree list
openspec list --json
openspec status --change g1-field-qualification-canonical-promotion --json
openspec status --change g1-provider-health-and-failure-visibility --json
```

## 20. 当前不要开始

- 最终 Council A/B；
- `g2-growth-expectation-v0-engine`；
- G3 runtime；
- canonical consumer 与 M3 Gate 的巨型混合 change；
- Growth diagnostic UI；
- 完整 reverse DCF/V1；
- LongPort/Longbridge production integration；
- 为获得 snapshot 而放宽 field policy 或填默认值；
- 未经用户授权的 live provider/LLM 调用。

## 21. 必读文件

```text
design/three-goal-capability-roadmap.md
design/total-design.md
design/architecture-decisions.md
design/capability-gate-and-execution-handoff-2026-08-05.md
design/m1-m2-g1-provider-canonical-runtime-rolling-handoff-2026-08-05-r1.md
design/growth-expectation-capitalization-prd-2026-08-04.md
design/g1-provider-batch-adapter-decision-2026-08-05.md
design/g1-field-qualification-canonical-promotion-decision-2026-08-05.md
openspec/changes/g1-provider-health-and-failure-visibility/
openspec/changes/g1-field-qualification-canonical-promotion/
openspec/changes/g1-fast-personal-value-screening/
openspec/changes/g2-deep-investment-thesis/
```

## 22. Suggested skills

- `openspec-explore`：核验 milestone、scope 和真实 baseline。
- `superpowers:requesting-code-review`：对 current main 做独立 review。
- `superpowers:receiving-code-review`：严格处理 findings，不盲从摘要。
- `superpowers:test-driven-development`：repair 时先 RED。
- `openspec-apply-change`：继续当前 active child。
- `openspec-archive-change`：review 通过后归档。
- `superpowers:verification-before-completion`：closure 前重新运行验证。
- `gitnexus-impact-analysis`：修改 canonical consumer/dossier 前评估影响。

## 23. 最终执行原则

```text
先证明输入可信，
再让可信输入进入本地漏斗，
再证明 G1 候选质量，
再建立 G2 事实与确定性分析，
再比较 Agent 形态，
再发布 InvestmentThesis，
最后建设持仓纪律与产品界面。
```

当前最重要的不是增加 provider、Agent、模型或 UI，而是关闭
qualification → eligibility → canonical snapshot → consumer 之间的可信合同，
并用新的 live evidence 证明该链路真实成立。
