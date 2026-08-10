# M1/M2：G1 Canonical Snapshot Consumer Rolling Handoff（2026-08-10）

> 所属大规划：`MASTER-2026-08-06`
>
> Track：`Track A`
>
> Owner child：`g1-canonical-snapshot-consumer`

## 当前状态

- 状态：`implementation_verified / review_findings_fixed / archive_pending`
- 本窗口只建设 canonical snapshot consumer；不实现 staged screening runtime、
  300+ sample validation、全市场性能/成本 Gate、Top 20 验收或任何 R-G2 repair。
- 不调用 live provider/LLM；不宣称 G1/G2 Capability passed；不 archive、不 push。
- 主 worktree 的 3 个指定未跟踪内容保持不变，未复制、stage、移动或清理。

## Workspace

```text
branch:   codex/g1-canonical-snapshot-consumer
worktree: /Users/admin/Documents/trade-agent/.worktrees/g1-canonical-snapshot-consumer
base:     main@ee00923
```

## OpenSpec

- Change：`openspec/changes/g1-canonical-snapshot-consumer/`
- proposal/design/spec/tasks 已完成并通过 `openspec validate --all --strict`
  （29 passed, 0 failed）。
- child 明确引用 `g1-fast-personal-value-screening` umbrella，仅负责 canonical
  snapshot consumer；不修改已归档 Change，不创建 Repair ID。

## Implementation

- 新增 `value-screener/data/lib/canonical_snapshot_consumer.py`。
- 新增 `value-screener/tests/test_canonical_snapshot_consumer.py`。
- consumer 只读加载 manifest、records、provenance，校验 schema、run/plan、
  canonical ticker、ticker-set hash，以及 records/provenance field identity。
- `identity.compute_snapshot_ticker_set_hash` 作为 snapshot writer/consumer 的共同
  hash SoT，与 `compute_input_ticker_set_hash` 明确分离。
- field-level 输出保留 value、status、eligibility、reason、provenance、as_of、
  freshness；只有明确 `fresh` 的 eligible 字段可用，缺失 freshness 以及
  non-qualified、rejected、not_evaluated、source_failed、invalid_value、stale、
  degraded 始终返回显式 null。
- records/provenance 的 snapshot-consumable value 必须一致；consumer metadata
  为深层只读结构。
- 不导入 provider、LLM、CacheManager 或生产写入路径；不修改 snapshot 文件。

## RED → GREEN 与验证证据

- RED：新增 consumer tests 在模块不存在时 `20 failed`，失败原因集中为缺少
  `data.lib.canonical_snapshot_consumer`。
- focused consumer：`27 passed`。
- 相关 canonical snapshot/provenance/identity/screener：`82 passed`。
- 本次修复未运行 repository full pytest，避免扩大验证范围和生成 runtime artifacts。
- strict OpenSpec：`29 passed, 0 failed`。
- compile：`/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python
  -m compileall -q value-screener` 通过。
- `git diff --check` 通过。
- 验证后清理了本目标 worktree 由 full pytest 生成的 ignored debate/watchlist
  artifacts；未留下 live provider、LLM、cache、ranking 或 canonical runtime 产物。
- 项目不存在 `package.json`，因此没有可运行的 `npm run lint` 脚本；Python
  compileall 与 pytest 已执行。

## Review findings and fixes

- 修复 snapshot ticker hash 与项目 input identity 混用的问题：writer/consumer
  共享 snapshot hash helper，input hash 保持独立。
- 修复缺失 freshness 仍暴露 value 的问题：只有 `fresh` 才能进入 available。
- 修复 records/provenance value 漂移可被接受的问题，并补充跨边界回归测试。
- 修复 consumer manifest/provenance 的浅层只读问题，补充 nested mutation 测试。
- side-effect 测试现在显式 spy provider adapter、BatchFetcher、LLM 和 CacheManager
  边界；未调用 live provider/LLM。

## Residual risk / next scope

- 当前证据是 fixture/reference 与离线测试证据，不是真实 provider qualification
  或全市场运行证据，不能关闭 G1 Capability Gate。
- consumer API 已定义，但 staged screening runtime 尚未实现；后续 child 必须
  继续保持 consumer 与 ranking/production path 的边界。
- 现有 snapshot schema 仍没有独立的 records/provenance 文件 artifact hash；本
  child 已阻断 field value 漂移，但完整文件级篡改检测需后续明确 schema contract。
- `read_snapshot()` 仍是原始 round-trip reader，不应被误称为 G1 consumer。
- archive 需在本 handoff 之后由独立治理流程决定；本窗口不执行 archive。
