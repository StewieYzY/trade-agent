# M1/M2：G1 Provider Qualification 与 Canonical Runtime Rolling Handoff（2026-08-05 r1）

> 类型：里程碑子轨 Rolling Handoff
>
> 所属大规划：`design/capability-gate-and-execution-handoff-2026-08-05.md`
>
> 历史大规划：`design/capability-gate-and-execution-handoff-2026-08-04.md`
>
> 适用范围：M1 A 股 Provider Qualification + M2 G1 Canonical Snapshot 与分层筛选 Runtime
>
> 不适用范围：M0 f3c closure、M3 G1 Capability Gate、M4/M4.5、最终 Council A/B、G3 runtime

## 1. 本文件的定位

本文件记录当前 G1 输入可信子轨的真实恢复点：

```text
M1 Provider Qualification
        ↓
M2 Canonical Snapshot / Provider Runtime
        ↓
M3 G1 真实 Capability Gate
```

它不替代完整大规划，也不重新定义 M0–M7。全局阶段、依赖关系和停止条件以
`design/capability-gate-and-execution-handoff-2026-08-05.md` 为准。

旧文件：

```text
design/m0-g2-trust-foundation-rolling-handoff-2026-08-05-r2.md
```

保留为 provider health 尚未合入 main 时的历史 checkpoint。不要继续在旧 M0
命名下追加 provider/canonical 工作。

## 2. 当前真实工作区

```text
main checkout:
  path:   /Users/admin/Documents/trade-agent
  branch: main
  runtime/integration baseline:
          bce6bc6 merge: integrate g1 field qualification canonical promotion
  remote before this docs-only closure:
          ahead of origin/main by 34 commits

removed integration worktree:
  path:   /Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter-mainline
  state:  merged, worktree removed, local branch deleted

historical provider adapter worktree:
  path:   /Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter
  branch: codex/g1-provider-batch-adapter
  HEAD:   a6e6699
  state:  clean, not an ancestor of current main, historical source only
```

本 handoff 与最新完整大规划将作为一个 docs-only closure 提交。该提交不改变
runtime/integration baseline。下一窗口必须重新核验：

```bash
git status --short --branch
git log -1 --oneline
git worktree list
openspec list --json
```

## 3. 与全局 M0 的关系

当前 M0 仍未关闭：

```text
f3c-r1-crosstalk-root-cause: 5/17 in-progress
f3c-harness-mainline:         a041314, dirty, not in main
g2 fallback integration:     f47db88, already in main
```

本 M1/M2 子轨是经确认推进的 G1 输入可信工作，不代表：

- f3c 已 closure；
- M0 已 passed；
- G2 runtime trust 已完全关闭；
- 可以开始最终 Council A/B。

M0 和 M1/M2 可以保留独立工作流，但任何 capability 放行仍遵循完整大规划。

## 4. M1：A 股 Provider Qualification 当前状态

### 4.1 已完成的工程基础

已归档：

```text
openspec/changes/archive/2026-08-04-a-share-provider-qualification
openspec/changes/archive/2026-08-04-provider-contract-and-provenance
```

已形成：

- 固定五只代表性 A 股 probe plan；
- provider/method/ticker/field evidence；
- unit/currency/as-of/report-period/provenance 合同；
- `record_not_found`、`source_failed`、`permission_denied`、
  `rate_limited`、`invalid_value`、`not_evaluated` 等状态；
- run-scoped evidence 与 raw hash；
- 不修改 production cache/ranking 的只读边界。

### 4.2 历史真实 evidence

Evidence root：

```text
/Users/admin/Documents/trade-agent-runtime-evidence/g1-provider-qualification-20260805
```

| run_id | 状态 | 当前证据含义 |
|---|---|---|
| `baseline-20260805-a` | historical | 错误 Python 环境记录，不作 provider 结论 |
| `baseline-20260805-b` | historical/partial | 旧 contract 下部分字段可用，不能作为当前 promotion 放行证据 |
| `baseline-20260805-health-a` | incomplete | bounded runtime/failure visibility |
| `baseline-20260805-health-b` | incomplete | 部分 field evidence，无 aggregate artifacts |
| `baseline-20260805-health-c` | incomplete | timeout completion，无 aggregate artifacts |
| `baseline-20260805-health-d` | incomplete | interruption evidence |

### 4.3 M1 尚缺

- 与当前 main/code version 绑定的 completed live qualification run；
- 当前 field policy 下的 provider/field qualification decision；
- AkShare/东财/同花顺/百度的当前字段差异证据；
- LongPort/Longbridge 的 A 股 runtime qualification；
- M4.5 所需 5–10 年财务、现金/债务、折旧摊销、营运资本、行业估值和
  consensus shadow coverage。

LongPort/Longbridge 当前继续 defer。该 defer 是执行优先级调整，不表示它们已经
qualification 完成，也不修改大规划中的 M1 放行条件。

### 4.4 M1 能力判断

```text
engineering contract: complete
historical baseline evidence: partial
current live qualification: missing
LongPort/Longbridge qualification: missing
M1 milestone: not passed
```

## 5. M2：Canonical Snapshot 与 Provider Runtime 当前状态

### 5.1 已归档

```text
openspec/changes/archive/2026-08-04-g1-canonical-snapshot-sync
openspec/changes/archive/2026-08-05-g1-provider-batch-adapter
```

### 5.2 Active complete、尚未归档

```text
g1-provider-health-and-failure-visibility:
  progress: 19/19
  state:    complete / frozen
  archive:  pending
  review:   P0=0, P1=0 at frozen checkpoint

g1-field-qualification-canonical-promotion:
  progress: 12/12
  state:    complete / merged to main
  archive:  pending
  review:   merged-main independent review pending
```

### 5.3 已实现边界

Provider adapter/health：

- 显式 provider registration；
- batch request identity；
- field-level status/provenance；
- malformed response fail closed；
- per-case timeout/interruption visibility；
- append-only events 与 partial manifest；
- incomplete run 不写 aggregate qualification artifacts；
- protected production output roots；
- secret redaction 和 bounded worker payload。

Field qualification/promotion：

- 只消费 completed qualification run；
- 版本化 field policy；
- provider/method/field group-level qualification；
- 全 policy ticker coverage；
- provenance/time/freshness/unit consistency；
- qualified evidence 才标记 `production_eligible`；
- blocked run 不生成 canonical records；
- source qualification run immutable。

实现入口：

```text
value-screener/data/lib/provider_batch_adapter.py
value-screener/scripts/provider_qualification.py
value-screener/data/lib/field_qualification.py
value-screener/scripts/promote_provider_snapshot.py
```

## 6. 当前必须先关闭的合同问题

已有 canonical snapshot spec 要求：

```text
unqualified / failed / conflicted / stale field
→ canonical value = null
→ snapshot sidecar 保留 status/reason/provenance
```

当前 promotion 只将：

```python
decision["promoted_evidence"]
```

传给 `write_snapshot()`。因此在部分 field group qualified、部分 rejected 时，
rejected evidence 只存在于 `decision.json`，可能不会进入 canonical
`provenance.json`，canonical record 也可能缺字段而不是显式 `null/status`。

这是 archive 前必须由独立 reviewer 核验的 P1 候选问题。推荐目标合同：

```text
all evaluated evidence
├── qualified     → production_eligible → canonical value
└── rejected      → not_qualified       → canonical null + provenance/status

decision.json     → 保存 group-level policy decision
provenance.json   → 保存全部 field-level evidence
records.json      → 合格值或显式 null
```

不得通过只要求消费者额外猜测 `decision.json` 来弱化 canonical snapshot 的
failure-visible 合同；如确需改变合同，必须显式修改 canonical spec 并说明迁移。

## 7. Fresh verification baseline

当前 main 合并后已记录：

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

该证据证明当前工程 checkout 的测试基线，不证明 M1/M2 capability passed，也不
替代新的 live provider evidence。

项目没有 `package.json`，因此没有可运行的 `npm run lint`。

## 8. M2 尚缺

- merged-main promotion child 独立 review；
- rejected/failed evidence canonical sidecar 合同收口；
- provider health 与 promotion 两个 active child archive；
- 新 completed live qualification evidence；
- 真实 `decision.json + canonical snapshot`；
- production canonical snapshot consumer；
- `g1-staged-screening-runtime`；
- Stage A/B/C ticker set 与 provider call count 单调下降证据。

### M2 能力判断

```text
canonical artifact foundation: complete
batch adapter foundation: complete
provider health foundation: complete / active
field promotion foundation: complete / active
real qualified snapshot: missing
consumer migration: missing
staged runtime: missing
M2 milestone: not passed
```

## 9. 下一执行顺序

### Step 1：merged-main 独立 review

只读检查：

```text
value-screener/data/lib/field_qualification.py
value-screener/scripts/promote_provider_snapshot.py
value-screener/tests/test_field_qualification.py
value-screener/data/lib/canonical_snapshot.py
openspec/changes/g1-field-qualification-canonical-promotion/
openspec/changes/archive/2026-08-04-g1-canonical-snapshot-sync/
```

优先问题：

- rejected evidence 是否进入 canonical null/status/provenance；
- source run completeness/count/hash 是否可绕过；
- duplicate/unexpected/cross-provider/freshness/time-basis conflict；
- output root/source run/production path escape；
- decision hash 是否覆盖语义输入；
- CLI policy 是否可能被误当 production 默认策略。

### Step 2：若 review 确认问题，在当前 active child 内 repair

执行顺序：

```text
更新 proposal/design/spec/tasks（仅实际变化）
→ RED test
→ minimal fix
→ focused tests
→ relevant/full tests
→ strict validation
→ 独立 re-review
```

不要新建一个模糊的“canonical cleanup” change 来隐藏原 child 的合同缺口。

### Step 3：分别 archive completed child

1. `g1-provider-health-and-failure-visibility`
2. `g1-field-qualification-canonical-promotion`

每个 archive 后核验：

- canonical spec sync；
- active/archive 目录；
- `openspec list --json`；
- `git diff --check`；
- commit 边界；
- archive 不代表 G1 pass。

### Step 4：生成新的 live qualification evidence

需用户明确授权真实 provider/network 调用。使用当前 main、项目 venv、冻结
provider/ticker/method/field/policy/run ID，输出到 repo 外。

只有 `completion_status=completed` 的 run 才能进入 promotion。

### Step 5：执行真实 promotion 与独立 evidence review

验证：

- policy/source/decision identity；
- qualified/rejected group；
- canonical records 的值与 null；
- provenance sidecar；
- source run immutable；
- 无 legacy cache/ranking/watchlist/debate 写入。

没有合格 field group 时保持 blocked。

### Step 6：建立 M2 consumer 与 staged runtime

拆成独立 child：

1. `g1-canonical-snapshot-consumer`
   - consumer 读取 value + status + provenance；
   - 不以缺字段、零值或 first-non-empty 改变 ranking；
   - legacy cache 保持兼容窗口。

2. `g1-staged-screening-runtime`
   - Stage A：basic/current valuation；
   - Stage B：financials/risk；
   - Stage C：historical valuation/K-line；
   - 用 ticker set、provider call count 和 cache hit 证明采集量逐层下降。

两者不能与 M3 capability Gate 合并。

## 10. M2 之后进入 M3

M3 必须继续拆成：

1. `g1-300-sample-validation`
2. `g1-full-market-performance-cost`
3. `g1-top20-style-review`

M3 Gate：

```text
300+ 多行业样本
warm-cache 全市场 ≤15 分钟
关键字段可用率 ≥95%
L2 成本 ≤¥2
未处理异常 = 0
Top 20 用户复核 ≥70% 值得进一步研究
```

所有工程、产品和 evidence Gate 同时通过后，G1 才能标记 passed。

## 11. 与后续 G2 的依赖

```text
M1 qualification + M2 canonical runtime
        ↓
M4 dossier quality
        ↓
M4.5 growth diagnostic contract / engine / integration
        ↓
M5 strong-single-agent vs Council A/B
```

真实 canonical snapshot 冻结后，先进入 M4，不直接进入最终 A/B。

M4.5 未冻结时禁止最终 A/B；G2 未 passed 时禁止 G3 runtime。

## 12. 下一窗口的直接任务

建议新窗口首先执行：

> 对 `g1-field-qualification-canonical-promotion` 做 merged-main 独立只读
> review，重点核验 rejected/failed evidence 是否满足 canonical
> null/status/provenance 合同，并判断该 active change 是否可 archive。

推荐启动提示：

```text
请按
design/capability-gate-and-execution-handoff-2026-08-05.md
和
design/m1-m2-g1-provider-canonical-runtime-rolling-handoff-2026-08-05-r1.md
执行下一步。先对 g1-field-qualification-canonical-promotion 做独立只读
review，不修改代码、不调用真实 provider；从当前 main、OpenSpec、实际代码和测试
出发，优先检查 canonical rejected evidence 的 null/status/provenance 合同、
路径安全、identity/hash 和缺失测试。先列 P0/P1/P2，再决定是否 repair/archive。
```

## 13. 必读文件

```text
design/capability-gate-and-execution-handoff-2026-08-05.md
design/three-goal-capability-roadmap.md
design/architecture-decisions.md
design/g1-provider-batch-adapter-decision-2026-08-05.md
design/g1-field-qualification-canonical-promotion-decision-2026-08-05.md
openspec/changes/g1-provider-health-and-failure-visibility/
openspec/changes/g1-field-qualification-canonical-promotion/
openspec/changes/archive/2026-08-04-g1-canonical-snapshot-sync/
```

## 14. Suggested skills

- `openspec-explore`：核验 handoff、OpenSpec 和 capability scope。
- `superpowers:requesting-code-review`：独立 review merged-main child。
- `superpowers:receiving-code-review`：收到 findings 后严谨处理。
- `superpowers:test-driven-development`：修复合同问题时先 RED。
- `openspec-apply-change`：在当前 active child 内继续实现。
- `openspec-archive-change`：独立 review 通过后分别 archive。
- `superpowers:verification-before-completion`：任何 closure 声明前重新验证。
