# M1/M2：G1 Staged Screening Runtime Rolling Handoff（2026-08-10）

> 所属大规划：`MASTER-2026-08-06`
>
> Track：`Track A`
>
> Owner child：`g1-staged-screening-runtime`

## 当前状态

- 状态：`implementation_verified / independent_review_pending / archive_pending`
- 本 child 已实现 Stage A/B/C staged runtime 与 BatchFetcher fetch telemetry。
- 不修改已归档 `g1-canonical-snapshot-consumer`；不处理 300+ sample、
  全市场性能/成本、Top 20 或任何 R-G2 repair。
- 不调用未经授权的 live provider/LLM；不宣称 M2、G1 或 G2 Capability passed；
  不 archive、不 push。

## Workspace

```text
branch:   codex/g1-staged-screening-runtime
worktree: /Users/admin/Documents/trade-agent/.worktrees/g1-staged-screening-runtime
base:     9ceae95 docs(g1): sync staged screening runtime handoff
```

## OpenSpec

- Change：`openspec/changes/g1-staged-screening-runtime/`
- proposal/design/spec/tasks 已完成。
- `openspec validate --all --strict`：`29 passed, 0 failed`。
- child 引用 `g1-fast-personal-value-screening` umbrella 与既有
  `staged-fetch-boundary`、`quantitative-screener` 边界；不修改归档 Change、
  不创建 Repair ID。

## Implementation

- 新增 `value-screener/screener/staged_runtime.py`。
- Stage A 仅请求 `basic`；Stage B 仅请求 `financials`、`risk`；Stage C 仅请求
  `valuation`、`kline`。
- Stage B 对财务年限/风险字段做 completeness 检查；Stage C 对历史估值、
  60 日收盘价和换手率序列做 completeness 检查，缺失不放行。
- canonical `last_price`/`pe_ttm` 等已表示字段的 stale/rejected/unknown status
  fail closed；Stage B/C 拒绝 malformed numeric payload，包含 NaN、inf、bool、
  非法序列和未知 dimension status。
- 每阶段只消费上一阶段输出 ticker 集合；失败 ticker 不进入下一阶段，单股失败
  不阻断整批。
- provider request 使用 canonical code，evidence 同时保留 raw/canonical identity；
  final factor/anti-trap/heat 逐 ticker 隔离异常，保留 heat failure details。
- `screen --staged --debug` 使用 staged stage counts，不再读取旧 L1 `stats`。
- `BatchFetcher` 新增可选 `FetchTelemetry`，区分 request、provider call、
  cache hit 与 source failure，不改变既有 fetch/cache 返回语义。
- canonical field adapter 保留 `value/status/reason/provenance/as_of/freshness`；
  不写 snapshot、cache、watchlist、debate 或 production output。
- 未修改 G2 dossier、Council、watchlist、monitor 或现有 L1 ranking 函数。

## RED → GREEN 与验证证据

- RED：runtime 模块不存在时测试收集失败；修正离线依赖夹具后确认是预期
  feature-missing failure。
- staged runtime/CLI focused：`29 passed`。
- 全量项目测试：`771 passed in 51.79s`。
- 项目虚拟环境 compileall：通过。
- `openspec validate --all --strict`：`29 passed, 0 failed`。
- `git diff --check`：通过。
- 使用项目共享虚拟环境
  `/Users/admin/Documents/trade-agent/value-screener/.venv/bin/pytest` 执行
  全量测试：`771 passed in 51.79s`。
- 同一虚拟环境版本：Python `3.13.3`、pytest `9.1.1`、akshare `1.18.64`、
  pandas `3.0.3`、typer `0.26.8`。
- 未生成或提交 live provider、LLM、cache、watchlist、debate 或 canonical
  production artifacts。

## Independent review

- 已修复 CR P1/P2：canonical last_price fail-closed、unknown/malformed
  status/numeric isolation、逐 ticker final scoring isolation、canonical code
  provider request、heat failure details、staged debug stats。
- `screen --staged` 已接入 CLI，但旧 `screen_a_shares()` 默认路径保持兼容；
  尚无真实 qualified canonical snapshot 或 provider runtime evidence。
- 测试与 fixture/reference 证据不能解释为 M2/G1 Capability 通过。
- 当前 child 仍需独立最终 review 后才能 archive。

## 下一步

1. 独立 reviewer 复核 diff、阶段边界、failure semantics 和无副作用证据。
2. review 通过后由治理流程决定是否 archive；本窗口不 archive、不 push。
