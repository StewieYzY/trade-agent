# M1/M2：R-G1-004 Production-Path Isolation Rolling Handoff（2026-08-10）

> 类型：Repair attempt rolling handoff
> Repair ID：`R-G1-004`
> Owner Change：`g1-provider-health-and-failure-visibility`
> 状态：`independent_review`
> 分支：`codex/r-g1-004-production-path-isolation-mainline`
> Worktree：`.worktrees/r-g1-004-production-path-isolation-mainline`
> 基线：`main@b6db756`

## Scope

本窗口只处理 G1 production-path isolation。R-G2-003、canonical snapshot consumer、
staged screening runtime、G1/G2 Capability Gate、真实 provider/LLM 均不在范围内。

## Root cause

health/promotion path validator 以 repo root 拼接 `watchlist`/`debate`，但真实 runtime
目录位于 `value-screener` 下，导致 production path isolation 失效。

## Implementation

- 新增 shared interface：`value-screener/data/lib/production_paths.py`；
- 统一解析 cache、watchlist、debate、ranking、canonical snapshot、growth diagnostic
  production roots；
- 拒绝 exact root、descendant、ancestor misuse，以及 lexical/realpath 后的 symlink
  escape；
- 允许 caller-provided、run-scoped、位于外部受控 output root 下的 artifacts；
- health runner、qualification/promotion、batch adapter、canonical snapshot writer
  均在副作用前复用 validator；
- 不修改 provider eligibility、ranking、canonical field policy，不接入 LongPort/
  Longbridge，不调用真实 provider/LLM。

## Evidence

- RED：共享模块缺失时 focused tests 在 collection 阶段失败；
- focused related tests：`157 passed`；
- full pytest：`719 passed in 53.97s`；
- strict OpenSpec：`28 passed, 0 failed`；
- compileall、diff check：通过；
- 目标 worktree runtime artifacts 已清理；主 worktree 三个指定未跟踪内容保持不变。

## Remaining state

后续独立 CR 发现遗漏历史 `data/snapshots` 与 `snapshots` production roots；本次已
补充 shared protected set 与回归测试，当前等待 fresh verification 和 review。R-G1-004
暂不 closed。TOCTOU 窗口仍为剩余风险，G2 fallback 仍由 R-G2-003 消费该 interface。
Owner Change 不 archive、不 push，该 repair 不代表 G1/G2 Capability passed。
