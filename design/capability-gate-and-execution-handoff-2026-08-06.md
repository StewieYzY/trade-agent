# trade-agent Capability Gate 与完整执行 Handoff

> 日期：2026-08-21
>
> Master ID：`MASTER-2026-08-06`
>
> 类型：唯一当前生效的大规划 Handoff
>
> 状态：`CURRENT`
>
> 稳定入口：`design/capability-gate-and-execution-handoff.md`
>
> 取代：`design/capability-gate-and-execution-handoff-2026-08-05.md`
>
> 产品能力第一参考源：`design/three-goal-capability-roadmap.md`
>
> 架构决策：`design/architecture-decisions.md`
>
> runtime/integration baseline：
> `dcfbcae merge: g2 growth expectation v0 repair`
>
> 当前 main/docs baseline：
> 代码合入基线为 `dcfbcae`；本 handoff 以本次 docs-only sync 为准，当前 push
> 状态以 Git 实况为准。
> 根目录既有 untracked user WIP（`.cache/`、`data/`、`debate/`、`watchlist/`
> 等）保持 untouched，未被本次 stage/commit。
>
> 历史 GitHub 审查入口：
> `PR #1 codex/mainline-sync-2026-08-05 → main`
>
> 当前本地集成以代码基线 `main@dcfbcae` 为准；本次 handoff docs 仅同步当前
> 状态，不改变代码合入基线。PR #1 以下信息仅作
> 历史审查快照，不再作为当前 branch 或 merge 状态判断依据。
>
> 当前直接执行阶段：
> `g1-full-market-performance-cost` 已 archived / integrated at
> `main@d0aaf9e`；其归档 evidence 保留在
> `openspec/changes/archive/2026-08-12-g1-full-market-performance-cost/evidence/`。
> M3 的 4.1、4.2、5.1、5.2、5.3、6.1、6.2 已有真实证据闭环；
> G1 umbrella 7.1、7.2、7.3 已完成。G1 capability 已通过，并已正式放行
> G2 formal acceptance；G2 capability/runtime 仍未通过。

> 以下 0.1 为 2026-08-18 历史快照；当前状态以 0.2 及后续 CURRENT sections 为准。

## 0.1. 2026-08-18 G2 1.1 child closure sync

- `g2-identity-audit-chain` 已 archive 至
  `openspec/changes/archive/2026-08-18-g2-identity-audit-chain/`。
- child commit：`762d98e feat(g2): add identity audit chain`，已 fast-forward
  合入 `main`；`g2-deep-investment-thesis` umbrella task 1.1 已勾选完成。
- archive 前 focused Council/fallback/audit suite：`142 passed`。
- merge 后全量 `value-screener/.venv/bin/python -m pytest value-screener/tests -q`：
  `990 passed in 59.08s`；compileall、`git diff --check` 和 OpenSpec strict
  `30 passed` 均通过。
- 受用户明确授权执行的真实 LLM run 仅为本地 pre-gate engineering diagnostic：
  使用真实缓存/provider 数据加明确标记的行业 fixture；不作为 G2 capability
  evidence bundle，不改变 G2 verdict，不放行 G3。
- 当前仍保持：G2 1.2、1.3、M4、M4.5、M5/A-B、InvestmentThesis interface
  和 G2 9.3 未完成；G2 capability `not passed`。

## 0.2. 2026-08-19 G2 1.2 child closure sync

- `g2-incomplete-cache-quality-status` 已 archive 至
  `openspec/changes/archive/2026-08-19-g2-incomplete-cache-quality-status/`。
- child commit：`d2d29c8 feat(g2): persist incomplete cache quality status`，已
  fast-forward 合入 `main`；umbrella task 1.2 已勾选完成。
- 独立 CR 最后一个 P2 已修复：损坏的最新 quality record 现在 fail closed，
  不再回溯命中旧成功 cache。
- 全量 `value-screener/.venv/bin/python -m pytest value-screener/tests -q`：
  `1041 passed in 57.58s`；compileall、`git diff --check` 均通过。
- OpenSpec strict：`31 passed, 0 failed`。
- 当前仍保持：G2 1.3、M4、M4.5、M5/A-B、InvestmentThesis interface 和
  G2 9.3 未完成；G2 capability `not passed`。

## 0.3. 2026-08-20 f3e negative diagnosis closure

- `f3e-r1-crosstalk-new-hypothesis` 已 archive 至
  `openspec/changes/archive/2026-08-20-f3e-r1-crosstalk-new-hypothesis/`。
- child commit：`547aeef feat(f3e): archive R1 crosstalk new-hypothesis diagnosis`，
  已 fast-forward 合入 `main` 并 push；`main == origin/main`。
- f3e 为阴性诊断：冻结 `600009.SH` 输入上未复现输入装配、角色分发、
  ticker/dossier/run identity 或编排状态导致的 R1 串台。
- `grounding_unverified_rate=1.0` 已记录为单位/派生值未归一的误报，不作为串台证据。
- 全量测试：`1063 passed`；compileall、`git diff --check` 通过。
- OpenSpec strict：`31 passed, 0 failed`。
- 串台根因仍未找到；下一步进行一次有界诊断 `f3f-r1-crosstalk-failure-repro`：
  冻结并复现 `600519` / `600900` 历史失败快照，不使用 `600009` 继续验证。
- 有界诊断退出条件：
  - 复现并定位根因：另开独立修复 child，闭环 G2 1.3；
  - 无法复现或仍无法定位：记录历史现象与残余风险，停止串台根因循环，
    推进 `g2-dossier-data-quality`；
- 禁止在没有新证据时继续派生新的串台诊断 child。
- 不宣称 G2 capability passed，不启动 G3。

## 0.4. 2026-08-20 f3f bounded diagnosis closure

- `f3f-r1-crosstalk-failure-repro` 已 archive 至
  `openspec/changes/archive/2026-08-20-f3f-r1-crosstalk-failure-repro/`。
- child commits：
  - `e5d21cc feat(f3f): archive historical R1 crosstalk failure repro diagnosis`
  - `2d2a1b6 feat(f3f): add authorized live R1 reproduction evidence`
- fixture/dry-run 复现成功：600519 环形显性串台与 600900 单 agent munger 引用
  均可被现有 `detect_circular_reference` 识别；历史 `insufficient_data` 输入在
  当前预检路径 fail-closed、不会到达 LLM。
- 授权 live 尝试为阴性：`f3f-live-20260820-01` 5/5 R1 调用成功，
  `circular_reference_detected=0/5`；当前 `deepseek-v4-pro` + 当前 prompt +
  insufficient-features 代理未复现历史显性串台。
- 残余风险：live 证据为单次代理输入，隐性串台逃逸面与 prompt 案例锚定设计
  审查仍未闭合。
- 串台诊断循环停止；下一步推进 `g2-dossier-data-quality`。
- 不宣称 G2 capability passed，不启动 G3。

## 0.5. 2026-08-21 G2 2.x dossier data-quality closure

- `g2-dossier-data-quality` 已 archive 至
  `openspec/changes/archive/2026-08-21-g2-dossier-data-quality/`。
- child commit：`6c1eff4 feat(g2): add dossier data quality provenance`，已
  fast-forward 合入 `main`。
- G2 umbrella 2.1、2.2、2.3 已勾选完成：
  - 主营、同行、研报等角色事实补齐；
  - 关键事实携带 source、report_period、published_at、freshness、degradation_status；
  - 高严重度无来源/时间基准/来源不匹配 fail closed，可复核追溯率口径已建立。
- 当前 `main` 相对 `origin/main` ahead 4，尚未 push。
- 不宣称 G2 capability passed，不启动 G3；下一步推进 G2 3.1
  `g2-growth-expectation-contract`。

## 0.6. 2026-08-25 G2 3.1 growth expectation contract closure

- `g2-growth-expectation-contract` 已 archive 至
  `openspec/changes/archive/2026-08-24-g2-growth-expectation-contract/`。
- child commit：`dfd59d4 fix(g2): close growth expectation contract review gaps`；
  已通过 merge commit `ed85508` 合入 `main`。
- contract 已冻结输入/输出、用户 assumption snapshot、模型适用性、失败语义、
  provenance 绑定和 golden cases；不包含计算引擎或 dossier/InvestmentThesis 集成。
- 合并后全量测试：`1240 passed`；OpenSpec strict：`34 passed, 0 failed`；
  compileall、`git diff --check` 通过。
- `main` 与 `origin/main` 已同步；专用 child worktree 和分支已清理。
- G2 capability 仍为 `not passed`，不启动 G3；下一步推进 G2 3.2
  `g2-growth-expectation-v0-engine`。

## 0.7. 2026-08-26 G2 3.2 growth expectation v0 engine repair closure

- `g2-growth-expectation-v0-engine` 已 archive，随后完成 correctness repair；
  repair archive 位于
  `openspec/changes/archive/2026-08-26-g2-growth-expectation-v0-engine-correctness-repair/`。
- repair archive commit：`47251b0 chore(g2): archive growth expectation engine repair`；
  已通过 merge commit `dcfbcae` 合入并 push 到 `main`。
- repair 覆盖 reverse solver 残差/窄区间求根、敏感性完整性、midpoint overdraft、
  failure artifact binding 和 legacy compatibility 边界。
- focused tests：`31 passed`；全量测试：`1271 passed`；
  OpenSpec strict：`34 passed, 0 failed`；compileall、`git diff --check` 通过。
- `dcfbcae` 合入点已 push；repair worktree 和分支仍保留，因其中存在未跟踪
  WIP，未修改、未 stage、未删除。
- 本次 change 未修改 provider-health 文件。此前关于 provider-health 首次时序失败
  后复跑通过的说法，当前归档未保留可独立核验的日志，因此不作为本 handoff 的已验证
  evidence。
- G2 capability 仍为 `not passed`，不启动 G3；下一步推进 G2 3.3
  `g2-growth-expectation-dossier-integration`。

## 1. 本文件的唯一权威地位

本文件是当前唯一生效的大规划 Handoff，统一记录：

- G1「快」→ G2「深」→ G3「拿得住」的产品目标和 Capability Gate；
- M0–M7 的依赖、真实状态、放行条件和停止条件；
- 当前 main、PR、worktree、OpenSpec、测试和 live evidence 状态；
- 所有已知 repair 的唯一登记、归属、状态、退出条件和执行顺序；
- 当前唯一允许的执行入口；
- 防止重复实现、反复修复和无边界成本消耗的治理规则。

任何 rolling handoff、OpenSpec child、review report、PR description 或对话摘要都
不能成为第二份大规划，也不能覆盖本文件的工作优先级。

稳定入口：

```text
design/capability-gate-and-execution-handoff.md
        ↓
design/capability-gate-and-execution-handoff-2026-08-06.md
```

历史 dated Handoff 保留为 read-only milestone snapshot，但不再作为执行入口。

## 2. 单一大规划治理

### 2.1 CURRENT / HISTORICAL

任一时刻只能有一个状态为 `CURRENT` 的完整大规划。

新建 dated 大规划时必须同时：

1. 将新的 dated 文件标为 `CURRENT`；
2. 更新稳定入口文件只指向新的 dated 文件；
3. 将旧 dated 文件标为 `SUPERSEDED / HISTORICAL / READ-ONLY`；
4. 迁移所有未关闭 Repair ID，不能换名、丢失或重复登记；
5. 写明旧版本为何失效、哪些状态发生变化；
6. 不删除历史文件，不把历史 snapshot 冒充当前事实。

### 2.2 Rolling Handoff 的权限

Rolling handoff 是微观执行恢复点，只能领取本文件 Repair Register 或 milestone
queue 中已经存在的工作。

Rolling handoff 不得：

- 新建未在本文件登记的 repair；
- 为同一 finding 换名字建立第二项工作；
- 重排 M0–M7；
- 把局部 child 描述成全局进度；
- 把 tasks complete、archive、commit、PR merge 或绿测写成 capability pass；
- 把历史 fixture/live evidence 冒充当前代码证据；
- 在 G1 rolling 中顺手修 G2，在 G2 rolling 中顺手修 G1-4。

Rolling handoff 发现新问题时必须停止扩 scope，先回到本文件：

```text
search existing Repair ID / OpenSpec task
→ 已存在：复用原 ID
→ 不存在：登记新 ID、owner、退出条件
→ 更新对应 OpenSpec
→ 才能进入 rolling execution
```

### 2.3 一个问题只有一个 owner

每个 repair 只能有一个 canonical owner：

- 一个 Repair ID；
- 一个主 OpenSpec change；
- 一个 root cause；
- 一组 RED tests；
- 一个 closure verdict。

其他 change 可以引用该 ID，但不得复制成自己的 repair。

## 3. 防止重复修复和无限循环

### 3.1 Repair 状态机

```text
identified
→ planned
→ red_confirmed
→ implemented
→ verified
→ independent_review
→ closed
```

异常状态：

```text
blocked
design_escalation
regressed
```

### 3.2 Attempt 计数

一次 repair attempt 必须完整包含：

```text
root-cause evidence
→ RED test
→ minimal fix
→ focused tests
→ relevant/full tests
→ strict validation
→ independent re-review
```

只改代码、只补测试、只改 spec 或只跑绿测都不算完成 attempt。

### 3.3 停止规则

- 同一 Repair ID 连续两次 independent re-review 仍未关闭：
  - 状态改为 `design_escalation`；
  - 停止继续 patch；
  - 重新审查合同/边界/架构；
  - 第三次实现前必须获得用户明确批准。
- 不得通过换文件名、换 child、换 Repair ID 重置 attempt 次数。
- 已关闭问题再次出现时使用原 ID，状态改为 `regressed`。
- deterministic contract repair 未关闭前，不运行新的 live provider/LLM。
- 没有新的 failure evidence 时，不允许“再试一次”式修改。

### 3.4 成本停止条件

- provider/LLM 调用必须有用户授权、冻结 input、run ID 和 repo 外 output root；
- fixture、mock、strict validation 和单测不能触发 live Gate 放行；
- 同一 live run 不因失败被无边界重跑；
- network/provider 失败保持失败证据，不使用未经验证的 fallback；
- secrets、raw provider payload、debate/watchlist/runtime artifacts 不进入 commit。

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
qualified provider
→ normalized raw response
→ failure-visible canonical snapshot
→ staged local funnel
→ L2 cost gate
→ 用户风格候选池
```

目标不是 provider 数量、因子数量或短期预测。

### G2「深」

```text
可信事实
+ 可审计推断
+ 明确假设
+ 反证/风险/关键变量
+ 什么情况下改变判断
= InvestmentThesis
```

Council 只有在受控 A/B 证明稳定增量后才保留；否则回退：

```text
strong single agent
+ independent DA / fact checker
+ deterministic synthesizer
```

### G3「拿得住」

```text
passed InvestmentThesis
→ 用户确认 HoldingContract
→ 区分价格扰动 / 预期偏差 / Thesis 破坏
→ 提醒用户按纪律复核
```

不连接券商、不自动交易，用户保留最终判断。

## 5. 当前 Git 与 PR 基线

### 5.1 Main

```text
path:   /Users/admin/Documents/trade-agent
branch: main
HEAD:   main == origin/main（精确值以 git rev-parse HEAD 为准）
upstream: origin/main
relation:
  local main == origin/main
status:
  tracked files clean; existing untracked user WIP preserved
```

### 5.2 PR #1

> Historical snapshot only; current integration is `main@0a9fb8a`.

```text
number: #1
state: open
draft: true
title: docs/g1/g2: sync 2026-08-05 mainline capability handoff
base:  75c4a138c7612555907ccecc5e93dfc5128df420
head:  2f13be9bd35d569b730addb1995534a628708396
mergeable_state: clean
review verdict: REQUEST CHANGES
```

`mergeable_state=clean` 只表示 Git 可以合并，不表示合同、工程或 Capability 已
ready；本节不作为当前集成状态来源。

PR #1 必须保持 Draft，直到所有 PR-blocking Repair ID closed 并通过整体
independent re-review。

### 5.3 当前治理 worktree

```text
path:
  /Users/admin/Documents/trade-agent/.worktrees/handoff-governance-2026-08-06
branch:
  codex/handoff-governance-2026-08-06
base:
  origin/codex/mainline-sync-2026-08-05@2f13be9
scope:
  planning governance only
```

该 worktree 不实施 runtime repair。

### 5.4 其他 worktree

| Worktree | HEAD | 状态 | 当前含义 |
|---|---:|---|---|
| `f3c-harness-mainline` | `a041314` | dirty，约 23 项 | M0 历史/未收口，不能整体合并 |
| `trade-agent-f3c-strong-model-control` | `f83bb85` | clean | 旧 stacked source only |
| `g1-provider-batch-adapter` | `a6e6699` | clean | 历史 source only |
| `g2-integration-mainline` | `f47db88` | clean / main ancestor | 已进入 main 的 fallback integration checkpoint |

## 6. 当前 OpenSpec

| Change | Tasks | CLI 状态 | 大规划真实状态 |
|---|---:|---|---|
| `g1-provider-health-and-failure-visibility` | 25/25 | archived / integrated at `main@f1ea010` | R-G1-004 closed |
| `g1-field-qualification-canonical-promotion` | 22/22 | archived / integrated at `main@1ff6678` | R-G1-001/R-G1-002 closed |
| `g1-r-g1-002-source-plan-matrix-completeness` | 14/14 | archived / integrated at `main@1ff6678` | R-G1-002 closed after independent review |
| `g1-r-g1-003-rejected-canonical-visibility` | 4/4 | archived / integrated at `main@98570a1` | R-G1-003 closed after independent re-review |
| `g2-strong-single-agent-fallback` | archived | archived; CR2 repair chain closed and governance synced at `main@0a9fb8a` after fresh independent review | R-G2-001/R-G2-002/R-G2-003 closed |
| `g2-incomplete-cache-quality-status` | archived | archived / integrated at `main@d2d29c8` | G2 1.2 closed |
| `g2-deep-investment-thesis` | 2/27 | in-progress | G2 umbrella，含 M4.5 |
| `f3c-r1-crosstalk-root-cause` | 5/17 | in-progress | M0 前置未闭 |
| `g1-4-data-source-resilience` | 0/48 | in-progress | P2 已映射到既有 D1/D6 |
| `g1-fast-personal-value-screening` | 16/16 | closed for G1 | 4.1/4.2/5.1/5.2/5.3/6.x/7.x 已闭环；G2 仅获准进入正式验收 |
| `g1-canonical-snapshot-consumer` | 10/10 | archived / integrated at `main@2777e7e` | consumer capability child closed |
| `g1-staged-screening-runtime` | complete | archived / integrated at `main@9a3a779` | staged runtime child closed |
| `g1-full-market-performance-cost` | archived | archived / integrated at `main@d0aaf9e` | M3 5.1/5.2/5.3 closed; evidence preserved |
| `g3-holding-discipline` | 0/29 | in-progress | design 可继续，runtime 锁定 |

任务勾选只表示旧 tasks 已完成。独立 review 发现合同缺口后，必须先更新原 active
change 的 spec/tasks，使 CLI 状态重新反映 repair 未完成事实。

## 7. PR #1 独立审查结论

### 7.1 审查边界

- Base：`75c4a13`
- Head：`2f13be9`
- 35 commits
- 117 files
- 约 18,539 insertions / 109 deletions
- 只读 review；
- 无真实 provider/LLM；
- 无 PR comment/merge；
- findings 已由主线程使用 `/tmp` 最小 fixture 复核。

### 7.2 Verdict

```text
P0: 0
P1: 6
P2: 2
PR #1: REQUEST CHANGES
```

### 7.3 已通过的工程基础

- health per-case subprocess、adapter load timeout、terminate/kill；
- append-only events、partial manifest、incomplete run 禁止 aggregate artifact；
- batch adapter malformed response、duplicate ticker、provider failure、conflict；
- canonical writer 对实际收到的 failed/not-qualified evidence 能写 null/sidecar；
- Council preflight 已阻断多数 empty/error-shell 输入；
- fallback 保持单次 strong-agent + deterministic synthesis；
- PR tree 未发现真实 `.env`、私钥、debate/watchlist/live raw evidence。

这些是工程 checkpoint，不是 archive readiness 或 Capability Gate。

## 8. 唯一 Repair Register

### 8.1 PR-blocking Repair

| ID | Milestone | Canonical owner | 状态 | Attempt | PR blocker |
|---|---|---|---|---:|---|
| `R-G1-001` | M1/M2 | `g1-field-qualification-canonical-promotion` | closed | 3 | 否 |
| `R-G1-002` | M1/M2 | `g1-r-g1-002-source-plan-matrix-completeness` | closed | 1 | 否 |
| `R-G1-003` | M2 | `g1-r-g1-003-rejected-canonical-visibility` | closed | 1 | 否 |
| `R-G1-004` | M1/M2 | `g1-provider-health-and-failure-visibility` | closed | 1 | 否 |
| `R-G2-001` | M0/M5 foundation | `g2-strong-single-agent-fallback` | closed | 1 | 否 |
| `R-G2-002` | M0/M5 foundation | `g2-strong-single-agent-fallback` | closed | 3 | 否 |
| `R-G2-003` | M0/M5 foundation | `g2-strong-single-agent-fallback` | closed | 1 | 否 |

独立 review 有 6 个 P1 finding。Production-path finding 跨 G1/G2 合同，为保持
单 owner 和不跨 Goal 实现，拆成 `R-G1-004` 与 `R-G2-003` 两个执行 ID；二者共享
同一 validator interface，但各自只负责自己的入口和测试。

### 8.2 Existing work links，不新建重复 Repair

| Existing ID | OpenSpec | 状态 | PR / Gate 影响 |
|---|---|---|---|
| `G1-4-D1` | `g1-4-data-source-resilience` | active 既有任务 | 不新增 ID；阻塞可信 coverage/G1 Gate |
| `G1-4-D6` | `g1-4-data-source-resilience` | active 既有任务 | 不新增 ID；阻塞 missing-data 语义/G1 Gate |

### 8.3 非功能性 PR hygiene

| ID | Owner | 状态 | 阻塞 |
|---|---|---|---|
| `R-DOC-001` | 当前 planning governance checkpoint | verified / integration pending | 不阻塞 capability；PR Ready 前关闭 |

`R-DOC-001` 对应：

- `design/growth-expectation-capitalization-prd-2026-08-04.md` EOF blank line；
- `design/tradingagents-cn-comparative-assessment-2026-08-03.md` Markdown trailing spaces。

它不得与任何 runtime repair 打包为“顺手重构”；只在 planning/docs commit 中原子
处理。

## 9. Repair 详细合同

### R-G1-001：Qualification runner provenance compatibility

**Root cause**

`provider_qualification._field_evidence()` 只在 evidence 顶层写
`market/ticker/raw_field/response_hash`，provenance 内缺失这些字段；
`validate_field_evidence()` 要求两处同时存在。

**Verified symptom**

```text
runner status=available
→ validate_field_evidence
→ status=not_evaluated
→ missing provenance:
   market, ticker, raw_field, response_hash
```

**Exit**

- runner 直接生成符合 canonical provenance contract 的 evidence；
- 真实 `QualificationRunner output → evaluator → promotion` fixture 通过；
- source evidence 不被 promotion 修改；
- independent re-review closed。

**Attempt 1 evidence (2026-08-06)**

- RED：最小 runner/evaluator/promotion fixture 在修复前返回 `blocked`，根因是
  `provenance` 缺少 `market/ticker/raw_field/response_hash`。
- Implementation：`_field_evidence()` 将四个字段与 evidence 顶层值保持一致地写入
  `provenance`；未修改 evaluator、promotion 或 canonical consumer。
- GREEN：`test_r_g1_001_provenance_compatibility.py` 及相关 provider/evaluator/
  provenance/canonical 测试通过；promotion 后 source run 文件保持不变。
- Verification：相关全量 `125 passed`，仓库完整 pytest `652 passed`，OpenSpec strict、
  compileall 与 `git diff --check` 均通过。
- Scope：不处理 `R-G1-002`、`R-G1-003`、`R-G1-004`、G1-4、canonical consumer、
  G2 或任何未登记 repair。
- Next state：`independent_review`；在独立 review 完成前不得将本 ID 标为
  `closed`，也不得 archive change 或宣称 G1/G2 Capability passed。

**Independent review follow-up / Attempt 2 evidence (2026-08-06)**

- Review verdict：`REQUEST CHANGES`，发现 response `_meta`/field metadata 可以通过
  `**meta` 覆盖 provenance 保留字段。
- RED：新增冲突 metadata fixture，修复前
  `provenance.provider_family/ticker/response_hash/retrieved_at` 与 evidence 顶层不一致。
- Implementation：`provenance` 先接收非保留 metadata，再由 runner 最后写入
  provider/method/market/ticker/raw_field/response_hash/retrieved_at/run_scoped。
- GREEN：reserved-field regression 与 runner→evaluator→promotion integration 均通过，
  且最终 `provenance.json` 与 source evidence identity/hash 一致。
- Verification：相关测试 `126 passed`，仓库完整 pytest `653 passed`，OpenSpec strict、
  compileall 与 `git diff --check` 均通过。
- Next state：重新进行 independent review；本次 follow-up 仍不关闭、不 archive。

**Independent review coverage follow-up / Attempt 3 evidence (2026-08-06)**

- Review finding：P2 测试未覆盖 `_fields.<field>` 级别的保留字段冲突，也未断言
  非保留 metadata 保留。
- RED：临时恢复 pre-fix 的 `**meta` 合并顺序后，field-level collision test 失败；
  失败值为 `field-wrong-family` 覆盖 runner 的 `baseline`。
- Test fix：增加 field-level collision fixture，并断言 `source_locator` 等非保留
  metadata 仍保留。
- Verification：R-G1-001 定向测试 `49 passed`；本次按用户要求不运行 repository-wide
  pytest；strict OpenSpec、compileall、`git diff --check` 通过。
- Closure（2026-08-10）：独立 re-review 未发现新的 R-G1-001 缺陷；在
  `main@0d0b0f4` 上，focused suite `49 passed`、完整 pytest `656 passed`、
  `openspec validate --all --strict` `28 passed, 0 failed`、compileall 与
  `git diff --check` 均通过。该结论只关闭 deterministic provenance repair，
  不代表 M1/M2/M3 或 G1/G2 Capability passed。

### R-G1-002：Source plan/hash/matrix completeness

**Root cause**

Promotion loader 只要求 `manifest.json + evidence.json` 和 evidence count；
不验证 `plan.json`、plan/ticker/evidence hash，也只遍历实际出现的 field group。

**Verified symptom**

```text
policy requires:
  last_price + previous_close
source:
  no plan.json
  only last_price
result:
  qualified
  previous_close absent from decisions
```

**Exit**

- completed source 必须有有效 frozen plan artifact；
- manifest/plan/run/ticker/evidence identity 可重算并一致；
- policy required matrix 的整个缺失 group 形成 rejected decision；
- CLI 明确绑定 probe plan version；
- truncation/tamper/missing-group tests 通过。

**Implementation / verification evidence (2026-08-10)**

- Implementation carrier：`g1-r-g1-002-source-plan-matrix-completeness`，复用本
  Repair ID，不创建新的 Repair。
- RED→GREEN：新增 plan 缺失/截断、artifact hash、manifest/plan hash cross
  identity、run/ticker/field identity、evidence tamper、planned identity 缺失、
  required matrix partial/missing、CLI plan version、合法 source run、source
  byte immutability tests。
- Implementation：completed source 强制 `manifest.json + plan.json +
  evidence.json`、artifact hashes、manifest/plan/run/identity 完整性；runner
  写入 hashes；promotion CLI 绑定 `PROBE_PLAN_VERSION`；不修改 provider
  eligibility、canonical policy 或下游 ranking。
- Verification：相关 suite `107 passed`；independent review first
  `REQUEST CHANGES` 后已修复并 fresh review `PASS`；OpenSpec strict `29 passed,
  0 failed`、compileall 与 `git diff --check` 通过。
- Full pytest 受环境依赖缺失阻塞：`495 items / 18 collection errors`
  （`akshare`、`typer`、`pandas` 未安装），不是本 child 测试 body failure。
- 未调用真实 provider/LLM，未生成 live/cache/watchlist/debate/canonical
  runtime artifacts。
- **Next state：** `R-G1-003`；本 child 已完成 independent review、归档并以
  `main@1ff6678` 集成，且不代表 G1/G2 Capability passed。

### R-G1-003：Rejected canonical visibility

**Root cause**

Promotion 只把 `decision["promoted_evidence"]` 传给 snapshot writer。

**Verified symptom**

```text
last_price qualified
previous_close source_failed
→ decision contains rejection
→ records has no previous_close:null
→ provenance has no previous_close status/reason/provenance
```

**Exit**

- snapshot writer 接收全部 in-policy evaluated evidence；
- qualified → `production_eligible` + value；
- rejected → `not_qualified` + explicit null + sidecar；
- mixed qualified/rejected integration test 通过；
- reader 不需要额外猜测 `decision.json`。

**Closure（2026-08-10）**

- child `g1-r-g1-003-rejected-canonical-visibility` 已归档并以
  `main@98570a1` 集成；
- independent re-review 未发现新的 P0/P1/P2/P3；
- focused `76 passed`、完整 pytest `699 passed`、OpenSpec strict `29 passed,
  0 failed`、compileall 与 `git diff --check` 均通过；
- 该 repair closure 不代表 G1/G2 Capability passed。

### R-G1-004：Production-path isolation

**Root cause**

Health/promotion path validator 以 repo root 拼接 `watchlist/debate`，但真实 runtime
目录位于 `value-screener/watchlist`、`value-screener/debate`。

**Verified symptom**

```text
health accepts value-screener/watchlist
promotion accepts value-screener/watchlist
```

**Exit**

- 一个 shared resolved-path validator；
- 覆盖真实 cache/watchlist/debate/ranking/canonical/diagnostic roots；
- 拒绝 exact、descendant、ancestor misuse 和 symlink escape；
- health/promotion/batch/canonical G1 入口复用；
- 不扩大到无关 filesystem sandbox 重构。

**Implementation checkpoint（2026-08-10）**

- clean target worktree/branch：
  `codex/r-g1-004-production-path-isolation-mainline`
  at `b6db756`，不复用既有脏 worktree；
- shared interface：
  `value-screener/data/lib/production_paths.py`；
- focused R-G1-004 + related provider health/qualification/promotion/canonical/batch
  tests：`157 passed`；
- RED 已确认：共享模块缺失时 focused collection 失败；
- 已验证 exact/descendant/ancestor/symlink rejection、external run-scoped acceptance、
  四个 G1 entrypoint fail-closed，以及拒绝时不调用 provider/evaluation、不创建 artifact；
- 后续独立 CR 发现遗漏历史 `data/snapshots` 与 `snapshots` production roots；已补充
  shared protected set 与回归测试；
- fresh independent re-CR：P0/P1/P2/P3 均为 0；
- 当前状态为 `closed`，owner Change 可 archive；本 repair 不代表 G1/G2 Capability
  passed。

`R-G1-004` 只负责 G1 entrypoints，并产出稳定的 shared validator interface。
G2 fallback 是否正确采用该 interface 由 `R-G2-003` 单独验收。

### R-G2-001：Explicit dossier ticker identity

**Root cause**

Council preflight 只校验已声明的 ticker/code/symbol，不要求
`core_snapshot.ticker` 存在。

**Verified symptom**

```text
explicit dossier has required facts
but no ticker/code/symbol
→ accepted for requested 600009.SH
```

**Exit**

- explicit dossier 必须有 canonical `core_snapshot.ticker`；
- optional section identity 若存在必须一致；
- missing/mismatch 在 artifact、cache、LLM 前 fail closed；
- regression tests 覆盖 Council 和 fallback。

**Closure evidence (2026-08-14)**：共享 Council/fallback preflight 已要求非空
`core_snapshot.ticker`，并递归校验顶层及 `research_dossier` optional identity；
缺失、空值和 mismatch 均在 cache、artifact、LLM 前 fail closed。Focused identity
tests、Council preflight tests 和全量 pytest 通过；该 repair 不改变 G2 capability verdict。

### R-G2-002：Fallback secret redaction

**Root cause**

Fallback 私有 `_redact_error()` 未复用 shared recursive redactor，不能处理
`api_key=...`、`token=...`、`Authorization=Bearer ...`。

**Verified symptom**

上述 secret pattern 原样进入 error string，并可能写入 `result.json`。

**Exit**

- 复用 `redact_sensitive_text()`；
- 覆盖 mapping/header/query/URL credential；
- fallback 默认 output root 明确且不污染 runtime success path；
- `fallback_runs/` repo hygiene 明确；
- tests 不包含真实 secret。

**Closure evidence (2026-08-14)**：fallback 已复用 shared `redact_sensitive_text()`；
error 与 malformed raw 的 API key、token、Bearer、URL credential、嵌套 mapping/list
不会进入 error/raw/result/manifest。未调用真实 provider/LLM。

**Closure evidence (2026-08-17)**：用户批准的第三次限定 repair 已修复普通文本上下文
中的 4–15 字符与 JWT-like Bearer/Token、`Bearer/Token format` 凭证，以及递归
`X-API-Key` header alias；同时保留 `invalid token format`、`Token budget exhausted`、
`bearer bond` 和 `Bearer authentication failed` 等完整诊断短语。fallback `result.json`
与 provider-batch snapshot/consumer 持久化回归均通过。最终 focused suite `119 passed`，
全量 `value-screener/tests` `951 passed`，OpenSpec strict `29 passed`，compileall 与
`git diff --check` 通过；fresh independent review = approve，代码与测试已合入
`main@2fbbbaa`。本 repair closure 仍仅是 engineering evidence，不代表 G2 capability
passed，也未调用真实 provider/LLM。

### R-G2-003：Fallback production-path adoption

**Root cause**

Fallback `_resolve_run_dir()` 只阻止 `run_id` 逃逸 caller-provided root，没有拒绝
真实 Council cache/watchlist/debate 等 production roots。

**Verified symptom**

```text
output_root=value-screener/watchlist
run_id=review-probe
→ accepted
→ run_dir under real watchlist
```

**Closure evidence (2026-08-14)**：fallback 已复用 shared
`validate_g1_output_root()`；cache/watchlist/debate/data/snapshots 的 exact、
descendant、ancestor 和 symlink path 均 fail closed，拒绝前无 LLM/artifact 副作用，
外部 run-scoped root 按 shared validator 规则处理。

**Dependency**

- 消费 `R-G1-004` 产出的 shared resolved-path validator interface；
- 不在 G2 change 中复制路径列表或重新实现 validator。

**Exit**

- fallback 在 artifact 创建和 LLM 前拒绝 protected roots；
- 覆盖 exact、descendant、ancestor misuse 和 symlink；
- 默认 `fallback_runs` 与 Council success path 物理隔离；
- focused fallback tests 和 independent re-review closed。

### G1-4-D1：Industry partial cache

已有 owner：`g1-4-data-source-resilience`。

现状：partial mapping 写缓存时只保存 mapping，下次 cache hit 无条件恢复为
`available`。

不得新建 repair；在既有 D1 tasks 中保留 status、covered/failed industries 和
attempted sources，或禁止 partial 作为 clean cache。

### G1-4-D6：Financials missing semantics

已有 owner：`g1-4-data-source-resilience`。

现状：`f_score=None` 已实现，但 quality 仍为 `0.0`，最终结果没有
`degraded/missing_reasons`。

不得新建 repair；继续完成既有 D6 的 factor-level `None/not_evaluable` 和结果层
degraded 聚合。

## 10. Repair 执行队列

### Queue 0：规划治理 checkpoint

```text
唯一 CURRENT master
→ stable pointer
→ 旧 master historical marker
→ 用户 review
```

本 checkpoint 不更新 repair OpenSpec、不写 runtime。

### Queue 1：G1 trust chain

严格顺序：

```text
R-G1-001 (closed)
→ R-G1-002 (closed)
→ R-G1-003
→ R-G1-004
→ focused/full tests
→ strict validation
→ independent re-review
→ health/promotion archive decision
```

这四项可以在一个 G1 rolling Handoff 中编排，但每个 ID 保持独立 RED/commit/review
证据。

### Queue 2：G2 fallback foundation

```text
R-G2-001
→ R-G2-002
→ R-G2-003
→ focused tests
→ full tests
→ strict validation
→ independent re-review
→ fallback archive decision
```

状态：原 child 已 archive，第三次限定 repair chain 已完成 focused/full 验证、strict
validation 和 fresh independent review，并以 `main@0a9fb8a` 完成治理收口。`R-G2-001`、
`R-G2-002`、`R-G2-003` 均为 `closed`；archive target 为
`openspec/changes/archive/2026-08-14-g2-strong-single-agent-fallback/`。该工程状态不代表
G2 capability passed，也不放行 G3 runtime。

### Queue 3：既有 G1-4

```text
G1-4-D1
→ G1-4-D6
→ 其余 active tasks
→ 真实 sample/provider Gate
```

不因 PR #1 review 重建 change 或重复 tasks。

### PR #1 Ready 条件

```text
R-G1-001..004 = closed
R-G2-001..003 = closed
R-DOC-001 = closed
relevant active changes strict valid
full suite pass on final head
no generated runtime artifacts
independent overall re-review = approve
```

PR Ready / merge 仍不表示 G1 或 G2 Capability passed。

## 11. M0–M7 总览

| Milestone | 当前状态 | Repair / 缺口 | 放行 |
|---|---|---|---|
| M0 G2 前置可信基础 | partial | f3c 5/17；受控 live root-cause evidence | 否 |
| M1 Provider Qualification | engineering partial | 当前 code version 的 completed live run、provider/field eligibility decision、baseline/candidate field coverage 缺失 | 否 |
| M2 Canonical Runtime | engineering partial | 真实 qualified snapshot；Stage A/B/C 的真实 provider runtime evidence | 否 |
| M3 G1 Capability Gate | passed | 300+、全市场、成本/性能、Top 20 | 是 |
| M4 G2 Dossier Quality | planned | source-aware dossier、单位/报告期/状态 | 否 |
| M4.5 Growth Diagnostic V0 | planned | contract、engine、dossier integration | 否 |
| M5 Thesis 与 A/B | foundation only | stable Thesis、同输入 A/B、盲评 | 否 |
| M6 G3 Runtime | locked | 等 G2 passed | 否 |
| M7 产品化/V1 | not started | 等各 capability passed | 否 |

## 12. M0：G2 前置可信基础

### 已有

- G2 fallback clean integration 已进入 main；
- strong single-agent fallback foundation；
- f3c/f3e 独立 worktree 历史产物。

### 缺口

- `f3c-r1-crosstalk-root-cause` 5/17；
- dirty f3c mainline closure；
- 当前代码对应的受控 live root-cause evidence；
- G2 identity/audit-chain 与 incomplete-cache child 尚未开始。

### 状态

```text
M0: not passed
```

G1 repair 前进不等于 M0 closure。

## 13. M1：Provider Qualification

### 已有

- provider qualification/provenance contract；
- 固定五只 A 股 probe plan；
- health failure-visible engineering foundation；
- historical incomplete runtime evidence。

### 缺口

- 当前 code version 的 completed live qualification；
- provider/field eligibility decision；
- baseline/candidate field coverage；
- LongPort/Longbridge qualification；
- M4.5 shadow fields。

### 状态

```text
M1: not passed
```

## 14. M2：Canonical Runtime

### 已有

- canonical snapshot writer/reader foundation；
- batch adapter foundation；
- archived health/promotion Change；canonical snapshot writer/reader foundation。

### 缺口

- 真实 qualified snapshot；
- Stage A/B/C 的真实 provider runtime evidence。

### 状态

```text
M2: not passed
```

## 15. M3：G1 Capability Gate

独立 children：

1. `g1-300-sample-validation`
2. `g1-full-market-performance-cost`
3. `g1-top20-style-review`

当前状态：

- `g1-full-market-performance-cost` 已归档并合入 `main@d0aaf9e`
- 真实受控证据覆盖沪深 5208 只，明确排除北交所
- 字段可用率 100%，未处理异常 0；总耗时与 L2 实测成本已作为观测指标保存
- 完整漏斗、降级分布、失败分布和运行配置已归档
- 4.1 已通过真实 300 只沪深分层样本与固定 universe 证据闭环：覆盖 33 个行业及 ST、小市值、负 PE、60 日过热风险类型，北交所排除
- 4.2 已通过真实样本 L1/L2 运行证据闭环：字段可用率 100%、未处理异常 0，`600008.SH` 的 L2 解析错误被单票隔离，完整 verdict 分布已保留
- 4.1/4.2 归档索引：`openspec/changes/g1-fast-personal-value-screening/evidence/g1-300-live-validation/evidence-index.md`
- 4.1/4.2 的证据只关闭规模预检前置条件；Top 20 产品 Gate 已由固定 run 的真实用户复核证据闭环
- 7.2 evidence bundle 已逐项对照 capability spec；7.3 release decision 已记录 G1=`passed`、G2=`approved_to_start_formal_acceptance`

Gate 组成：

```text
300+ 多行业样本
warm-cache 全市场真实运行
关键字段可用率 ≥95%（硬性）
未处理异常 = 0
总耗时（观测指标，15 分钟为参考阈值）
L2 成本（观测指标，¥2 为参考阈值）
Top 20 用户复核 ≥70% 值得进一步研究
```

```text
M3/G1 capability: passed
4.1/4.2: closed
5.1/5.2/5.3: closed
6.1/6.2: closed
7.1/7.2/7.3: closed
G2 formal acceptance: approved to start
G2 capability/runtime: not started
```

## 16. M4：G2 Evidence Dossier Quality

目标：

- source/status/provenance；
- report period/unit/freshness；
- facts/market expectations/user assumptions 分区；
- immutable dossier；
- degraded/insufficient/not_evaluable。

后续：

1. `g2-evidence-dossier-quality`
2. `g2-source-aware-dossier`
3. `g2-diagnostic-input-contract-foundation`

```text
M4: not started as current execution milestone
```

## 17. M4.5：Growth Expectation Diagnostic V0

顺序：

1. `g2-growth-expectation-contract`
2. `g2-growth-expectation-v0-engine`
3. `g2-growth-expectation-dossier-integration`

约束：

- deterministic，无 LLM；
- EPV proxy + 成熟期估值交叉锚；
- fixed growth/duration reverse modes；
- sensitivity、assumptions、provenance、calculation status；
- 两条 A/B 路径共享同一 diagnostic/assumption snapshot；
- 不进入 G1 ranking/hard gate。

```text
M4.5: 3.1 contract and 3.2 v0 engine closed; 3.3 dossier integration is next
```

## 18. M5：InvestmentThesis 与 A/B

必须完成：

- strong-single-agent baseline；
- Council A/B harness；
- 8–10 只固定样本；
- 同 model/dossier/diagnostic/tools/comparable budget；
- anonymous rubric + cost；
- stable InvestmentThesis。

Gate：

```text
Council 实质增量 ≥70%
用户盲评 Council 更好 ≥60%
Council 明显更差 ≤20%
审计对齐率 100%
高严重度凭空数字 0
关键事实追溯率 ≥95%
```

失败则回退 strong single-agent + independent DA/fact checker + synthesizer。

```text
M5/G2 capability: not passed
```

## 19. M6：G3 Runtime

前置：

- G2 passed；
- stable InvestmentThesis；
- versioned valuation expectation；
- 用户保留最终判断。

后续：

1. `g3-holding-domain-model`
2. `g3-contract-lifecycle`
3. `g3-monitor-signal-and-evaluator`
4. `g3-shadow-mode`

```text
M6 runtime: locked
```

## 20. M7：Gate 后产品化

只在相应 capability passed 后推进：

- funnel observability UI；
- provider/data health ops；
- Thesis history/export；
- growth diagnostic interaction；
- G3 holding review UI；
- task progress/run history。

产品壳、前端、队列或 dashboard 不能反向证明 capability。

## 21. 测试与证据基线

### 当前自动化

```text
latest full suite:
  951 passed in 55.67s

latest CR-boundary focused suite:
  119 passed in 1.63s

active OpenSpec strict validation:
  29 passed, 0 failed
  archived repair tasks 5.7–5.14 synced; R-G2-002 closure is engineering evidence
  rather than Gate closure
```

### Whitespace

```text
existing PR head 2f13be9:
  exit 2

governance checkpoint working tree against origin/main:
  passed
```

仅涉及历史 Markdown whitespace/EOF；已在当前 governance checkpoint 修复并通过
prospective range check。`R-DOC-001` 在该 checkpoint 集成到 PR head 后改为
`closed`。它不是 runtime Capability blocker，但必须在 PR Ready 前关闭。

### GitNexus

GitNexus 索引与当前 head 不同步。尝试使用 `gitnexus 1.6.6
--index-only` 刷新时，其发布包导入未声明/未构建的 `tree-sitter-swift` 而失败。

因此本次 review 不使用 stale graph，findings 以实际 diff、源码、spec 和最小
fixture reproduction 为证据。该外部工具问题不登记为项目 Repair ID。

### Live evidence

- `g1-full-market-performance-cost` 的最终 evidence 已归档并纳入
  `main@d0aaf9e`，索引为
  `openspec/changes/archive/2026-08-12-g1-full-market-performance-cost/evidence-index.md`；
- 该 full-market evidence 证明 M3 5.1、5.2、5.3，不能替代 4.1/4.2 的独立证据，也不能证明 Top 20；
- `g1-top20-style-review` 已归档，固定 run 的真实用户复核证据记录
  `20/20` 值得进一步研究，完成 M3 6.1/6.2；
- historical health runs 均不足以作为当前 promotion/G1 Gate；
- 当前 head 没有 completed live qualification/promotion；
- fixture/reference 不替代 live evidence；
- G1 7.1/7.2/7.3 已完成，release decision 记录
  `G1=passed`、`G2=approved_to_start_formal_acceptance`；
- G1 capability 已通过，但不代表 G2 capability/runtime 或下游产品化已完成。

## 22. 当前唯一允许动作

Queue 1 repair closure 已完成：`R-G1-001`、`R-G1-002`、`R-G1-003`、
`R-G1-004` 均已完成 independent review、归档并合入 `main@f1ea010`。
`g1-canonical-snapshot-consumer` 已完成 independent review、归档并合入
`main@2777e7e`，consumer capability child = closed。
`g1-staged-screening-runtime` 已完成实现、验证、归档并合入
`main@9a3a779`，staged runtime child = closed。
`g1-full-market-performance-cost` 已完成实现、独立 review、归档并合入
`main@d0aaf9e`，M3 5.1/5.2/5.3 = closed，证据已保留。
`g1-top20-style-review` 已完成实现、独立 review、归档并合入
`main@8513096`，M3 6.1/6.2 = closed，Top 20 evidence 已保留。
G1 umbrella 7.1/7.2/7.3 已完成，release decision 已记录
`G1=passed`、`G2=approved_to_start_formal_acceptance`。
G2 1.1、1.2、1.3、2.1、2.2、2.3、3.1 和 3.2 已完成并归档。f3f 的有界诊断已
停止串台根因循环；dossier data-quality 已补齐事实来源与追溯；growth expectation
contract 与 v0 engine 已完成。下一步推进 G2 3.3
`g2-growth-expectation-dossier-integration`。不得将 G2 capability/runtime 描述为已通过，
也不得提前启动 G3 runtime 或产品化。

## 23. 下一窗口启动方式

### 必读顺序

```text
1. design/capability-gate-and-execution-handoff.md
2. 该入口指向的唯一 CURRENT master
3. 当前 Queue 对应 rolling handoff
4. Repair ID 对应 OpenSpec
```

### 当前 checkpoint review 提示

```text
请只读审查 MASTER-2026-08-06：

- 是否确实只有一个 CURRENT 大规划；
- Repair ID 是否完整覆盖 PR #1 findings；
- 是否存在重复 owner、孤儿 repair 或跨 Goal 偷带；
- 两次 failed re-review → design_escalation 是否足以阻止无限 patch；
- Queue 1/2/3 是否符合 G1→G2→G3 和当前开发状态；
- PR Ready 与 Capability Gate 是否严格分开。

本轮不修改 runtime、不调用 provider/LLM、不 archive、不 merge PR。
```

## 24. 当前禁止开始

- PR #1 转 Ready 或 merge；
- 未登记 Repair ID 的 patch；
- 将 R-G1 与 R-G2 放入同一 implementation child；
- 为 G1-4-D1/D6 新建重复 repair/change；
- health/promotion/fallback archive；
- completed live provider qualification；
- final Council A/B；
- growth diagnostic engine；
- G3 runtime；
- 为让 snapshot/Gate 通过而填默认值或放宽 policy；
- 未授权 provider/LLM 重跑；
- 第三次无设计批准的同 ID repair attempt。

## 25. 大规划更新协议

每次 milestone 状态变化时：

1. 先更新 Repair Register/status/attempt/evidence；
2. 再更新 milestone 表和当前 Queue；
3. rolling 只引用 ID 和 exact execution state；
4. OpenSpec 记录 requirement/tasks；
5. code/tests/evidence 记录在对应 child；
6. capability Gate 只由独立整体 review 更新；
7. 新 dated master 必须迁移全部未关闭 ID；
8. stable pointer 始终只指向一个 CURRENT master。

任何无法在本文件定位 owner 和 exit condition 的工作都不得开始。
