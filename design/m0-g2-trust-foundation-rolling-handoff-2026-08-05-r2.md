# M0：G2 前置可信基础 Rolling Handoff（2026-08-05 r2）

本文件于 2026-08-05 按冻结决定原位更新，继续保留
`design/m0-g2-trust-foundation-rolling-handoff-2026-08-05.md` 历史版本。

## 当前真实工作区

```text
main checkout:
  path:   /Users/admin/Documents/trade-agent
  branch: main
  HEAD:   d5fc1af docs: add 2026-08-05 rolling handoff
  status: clean; ahead of origin/main by 20 commits

G1 integration checkpoint:
  path:   /Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter-mainline
  branch: codex/g1-provider-batch-adapter-mainline
  HEAD:   5e9664f docs(g1): specify provider health failure visibility
  status: dirty; frozen provider-health implementation/tests/tasks and this handoff are uncommitted
```

`main` 尚未合入 provider batch adapter 或 provider health child。当前
integration checkpoint 不是 G1 capability pass，也不是 G2 readiness。

全量测试生成的 `debate/`、`watchlist/` runtime 文件已清理；没有 cache JSON、
真实 provider raw、ranking、canonical snapshot 或 secret 待提交。

## 已提交的 G1 provider adapter checkpoint

当前分支从 `main@d5fc1af` 选择性集成：

```text
172c365 feat(g1): add explicit provider batch adapter
ba0458f fix(g1): close provider batch review findings
5c79baa fix(g1): close second provider review findings
8c6ccbf fix(g1): isolate malformed provider responses
59462c2 docs(g1): record baseline provider runtime probe
9a4730a docs(g1): record corrected provider runtime probe
4eda8f8 fix(g1): close final provider boundary review findings
1297639 fix(g1): keep qualification evidence timestamps consistent
48d2396 docs: update g1 integration rolling handoff
5e9664f docs(g1): specify provider health failure visibility
```

该 checkpoint 已覆盖：

- 显式 provider registration、A 股 ticker/field/method 输入边界；
- batch request identity、field-level evidence、status 和 provenance；
- provider/ticker/field failure isolation 与 malformed response fail-closed；
- `record_not_found`、`source_failed`、`invalid_value`、`not_evaluated`
  语义隔离；
- 顶层/nested `retrieved_at` 一致性、freshness status/conflict；
- shadow/not-qualified evidence 不进入 production canonical；
- 不修改 legacy cache、ranking、watchlist、debate 或 staged screening。

## 冻结的 provider health child

Active OpenSpec change：

```text
openspec/changes/g1-provider-health-and-failure-visibility
schema:   spec-driven
progress: 19/19
state:    isComplete=true
archive:  未执行
commit:   未执行
```

冻结范围仅包括：

- live qualification case 独立子进程执行；
- per-case timeout、terminate/kill 与 continue/stop policy；
- adapter discovery 独立 bounded timeout，默认 5 秒，不与 case timeout 耦合；
- append-only `events.ndjson`；
- 每个 terminal case 后原子更新 manifest；
- timeout、interruption、factory/provider/child failure 可见；
- failure metadata 和成功响应 metadata/raw 递归脱敏；
- isolated worker IPC payload 总大小 fail-closed；
- runtime code version、dirty state 和 diff fingerprint；
- caller output root 与最终 run directory 的 production-path 防护；
- incomplete run 不写 aggregate artifacts，也不返回 aggregate evidence/comparison。

明确不在该 child 中继续实现：

- retry/backoff、并发 scheduler 或 provider-specific timeout profile；
- provider eligibility、field promotion 或 canonical production snapshot；
- ranking、cache、G2/G3 runtime；
- LongPort/Longbridge production integration；
- 通用 Python adapter sandbox。

## 最终独立 review

最终 reviewer 基于当前 worktree 直接检查，没有复用旧 review，也没有调用真实
provider。冻结前发现并按 TDD 关闭：

1. `output_root=repo_root + run_id=watchlist` 可绕过 production path 防护；
2. adapter factory/import 在父进程同步执行，可能无界挂死且无 run-scoped manifest；
3. incomplete run 仍通过 Python 返回值暴露 aggregate evidence；
4. 成功响应 metadata 可泄露 credential，worker payload 未受总大小约束；
5. 初次修复将 adapter discovery timeout 错误耦合到 per-case timeout。

修复后 reviewer 逐项 re-review：

```text
P0: 0
P1: 0
结论: 未发现阻止冻结的新问题
```

此前旧 review 报告的三项也已在当前代码和回归测试中核验关闭：

- isolated SIGTERM 不再被 child exception boundary 吞掉；
- callable `not_evaluated` provider 不再误报 no runtime adapter；
- interruption event 使用真实 elapsed time，不再固定为 0。

## Fresh local verification

使用：

```text
/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python
```

2026-08-05 冻结验证：

```text
focused provider health/qualification/adapter/provenance/canonical:
  110 passed in 3.66s

full pytest:
  637 passed in 54.43s

compileall:
  passed

git diff --check:
  passed

openspec validate g1-provider-health-and-failure-visibility --strict:
  passed
```

项目根目录和 `value-screener/` 均没有 `package.json`，因此
`npm run lint` 不存在，无法运行。

## 真实 provider evidence

用户已批准过真实 provider 调用，但冻结后没有再次调用。历史 evidence 全部保留在：

```text
/Users/admin/Documents/trade-agent-runtime-evidence/g1-provider-qualification-20260805
```

关键 run：

| run_id | completion | completed | timeout | interrupted | not started | 结论 |
|---|---:|---:|---:|---:|---:|---|
| `baseline-20260805-b` | historical | - | - | - | - | 旧 contract 下的 partial field evidence，不能 promotion |
| `baseline-20260805-health-a` | incomplete | 35 | 15 | 0 | 0 | 早期 bounded runtime evidence |
| `baseline-20260805-health-b` | incomplete | 35 | 15 | 0 | 0 | 45 available fields，但无 aggregate artifacts |
| `baseline-20260805-health-c` | incomplete | 35 | 15 | 0 | 0 | `stop_reason=completed_with_timeout`，无 aggregate artifacts |
| `baseline-20260805-health-d` | incomplete | 30 | 0 | 1 | 19 | 用户中断，只是 interruption evidence |

`health-b`/`health-c` 的 field status counts：

```text
available:         45
record_not_found:  30
invalid_value:     10
not_evaluated:     30
source_failed:     50
```

这些 run 证明 bounded execution/failure visibility 曾作用于真实 AkShare
fetcher chain，但都不构成 full provider qualification、canonical promotion
或 G1 capability pass。

最终 P1 修复发生在这些 runtime run 之后。按冻结决定，本轮只做本地测试和最终
review，因此当前最终代码没有新的 live-provider runtime evidence；handoff
不得把历史 run 描述成当前代码的完整 runtime 验证。

## 冻结决定与剩余风险

`g1-provider-health-and-failure-visibility` 从现在起冻结：

- 不再增加行为、参数、重试、并发或 sandbox；
- 不再为本 child 调用真实 provider；
- 只允许在 commit 前处理新发现的 P0/P1；
- archive、task checked、绿测或 commit 均不代表 G1 capability pass。

已接受并显式保留的 residual risks：

- Python 3.13 真实 baseline 退出时出现 `resource_tracker` leaked semaphore
  warning；deterministic tests 未复现；
- 任意 adapter Python 代码仍可主动使用绝对路径写文件，runner 不是通用 sandbox；
- descendant process cascade termination 尚未独立验证；
- 历史 health run 与最终未提交代码不完全同版本；
- 真实 field-level provider qualification、canonical promotion 和 G1 Gate
  仍未完成。

## 下一步

当前只剩工程 checkpoint 决策：

1. 复核最终 diff 和 staging 范围；
2. 决定是否 commit 冻结的 provider health child；
3. commit 后再决定是否 archive；archive 仍不代表 G1 pass；
4. 停止扩展 health runner，转入 field-level qualification decision；
5. 由后续独立 child 消费新的、run-scoped、可审计 evidence，明确哪些字段
   满足 provenance、时间基准、跨 ticker coverage 和下游契约；
6. 只对明确合格字段生成 run-scoped canonical snapshot，其余状态保留在
   sidecar，不填默认值；
7. snapshot 冻结后，才准备 Council-vs-fallback A/B；
8. M4.5 仍按 contract → V0 engine → dossier integration 推进，最终 A/B
   两条路径共享相同 diagnostic 和 assumption snapshot。

LongPort/Longbridge 仍是 candidate/blocked。只有 field-level qualification
确认 AkShare 对关键消费字段存在无法接受的真实缺口后，才按字段缺口决定是否
增加补充 provider；当前不直接进入 production integration。
