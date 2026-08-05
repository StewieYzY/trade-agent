# M0：G2 前置可信基础 Rolling Handoff

日期：2026-08-05

状态：取代 `design/m0-g2-trust-foundation-rolling-handoff-2026-08-04.md` 作为最新 M0 rolling handoff；旧文件保留。

## 1. 当前真实基线

### 主工作区

```text
workspace: /Users/admin/Documents/trade-agent
branch:    main
HEAD:      a2012ee feat(g1): add provider qualification and canonical snapshot boundaries
status:    clean before this docs-only handoff
```

main 当前没有合入 provider batch adapter child。main 上的 capability 状态仍为：

```text
G1：未通过
G2：未通过
G3：runtime 未开始，继续锁定
```

### Provider adapter worktree

```text
worktree: /Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter
branch:   codex/g1-provider-batch-adapter
HEAD:     4602de7 docs(g1): record corrected provider runtime probe
status:   clean
```

该 worktree 的实现提交链为：

```text
93094ac feat(g1): add explicit provider batch adapter
2691672 fix(g1): close provider batch review findings
6fd8bf4  fix(g1): close second provider review findings
b638568  fix(g1): isolate malformed provider responses
23c791d docs(g1): record baseline provider runtime probe
4602de7 docs(g1): record corrected provider runtime probe
```

`g1-provider-batch-adapter` 已归档至：

```text
openspec/changes/archive/2026-08-05-g1-provider-batch-adapter
```

它仍未合入 main，也不能被描述为 G1 capability pass。

## 2. 本阶段已完成

### Provider batch adapter 工程边界

已实现并反复修复：

- 显式 provider registration、canonical A-share ticker boundary；
- provider/method/ticker-set/fields request identity；
- batch call count、requested/returned/missing ticker、response hash 和 run identity；
- field-level evidence、unit/currency/time basis、status 和 provenance；
- provider/ticker/field failure isolation；
- mapping key 与 embedded ticker binding 校验；
- malformed response、非法 ticker、`None`/标量 response、字段 metadata 类型异常的 fail-closed 处理；
- stale/unknown freshness evidence 不进入 canonical；
- output_root 落盘 manifest 保留 provider batch audit 信息；
- shadow/not-qualified provider 不进入 production canonical value；
- 不修改 legacy cache、ranking、watchlist、debate 或 staged screening。

相关工程记录：

```text
/Users/admin/Documents/trade-agent/design/g1-provider-batch-adapter-decision-2026-08-05.md
```

### Verification

在 provider adapter worktree：

```text
adapter + provider qualification + provenance + canonical snapshot：
53 passed

compileall：
passed

git diff --check：
passed
```

当前没有针对 `b638568` 之后最终状态的全量 pytest 证据；全量环境仍需按项目 venv 重新核验。已有的 53 项是当前相关边界套件，不是 capability Gate。

## 3. 真实 provider runtime evidence

用户已于 2026-08-05 明确批准调用真实 provider。

### 无效诊断 run：不要作为能力证据

```text
run_id: baseline-20260805-a
interpreter: /opt/homebrew/bin/python3
结果：误用了系统 Python，报告 akshare 缺失
```

该 run 不代表项目环境中的真实 provider 结论，但原始产物保留用于解释诊断过程。

### 有效 corrected run

使用项目已有 venv：

```text
python: /Users/admin/Documents/trade-agent/value-screener/.venv/bin/python
akshare: 1.18.64
pandas: 3.0.3
typer: 0.26.8
```

运行：

```text
provider: baseline / akshare-existing-fetcher-chain
run_id: baseline-20260805-b
code_version: 23c791d977c7455a6adb1c09dac885fc45e5ed7f
tickers:
  600519.SH
  600009.SH
  000858.SZ
  300750.SZ
  601318.SH
```

run-scoped evidence：

```text
/Users/admin/Documents/trade-agent-runtime-evidence/g1-provider-qualification-20260805/baseline-20260805-b
```

状态统计：

```text
available:       75
record_not_found: 50
invalid_value:   10
not_evaluated:   30
```

有效可取字段包括：

- static info：`code`、`name`、`market`；
- quote：`last_price`；
- calc indexes：`pe_ttm`、`pb`；
- historical kline：`dates`、`close`；
- income statement：`report_period`、`revenue`、`net_profit`；
- balance sheet / cash flow：`report_period`；
- historical valuation：`pe_ttm`、`pb`。

仍缺失或不合格：

- `previous_close`、`volume`、`turnover_rate`、`dividend_yield`；
- 部分资产负债表和现金流字段；
- historical valuation 的 `as_of`；
- historical kline 的 `volume`/`turnover_rate` 为 `invalid_value`；
- `industry_valuation`、`consensus` 没有 ticker-aligned baseline contract。

结论：

```text
baseline provider：真实 partial evidence
provider qualification：未通过
canonical production promotion：未放行
G1 capability Gate：未通过
```

LongPort/Longbridge 仍没有显式 SDK/凭据，因此未调用，继续保持 candidate/blocked。

## 4. 当前可以进入的下一阶段

可以进入 bounded snapshot / A-B preparation，但不能跳到 production 或 capability pass。

### 下一阶段顺序

1. 对 `baseline-20260805-b` 做 field-level qualification decision；
2. 将 `available` evidence 生成 run-scoped canonical snapshot；
3. 将 `record_not_found`、`invalid_value`、`not_evaluated` 保留在 provenance sidecar，不转成默认值；
4. 再次对最终 provider adapter commit 做独立 review；
5. 通过 review 后，在 clean integration worktree 选择性合入 main；
6. 用冻结 snapshot、冻结 prompt/input 和共享 assumption snapshot 准备 Council-vs-fallback A/B；
7. M4.5 deterministic growth expectation diagnostic 仍需先完成 contract → V0 engine → dossier integration，之后才运行最终 Council A/B。

### A/B 边界

Council 与 fallback 必须：

- 使用相同 canonical snapshot；
- 使用相同 `growth_expectation_diagnostic`；
- 使用相同 assumption snapshot；
- 记录模型、prompt、输入 hash、usage/cost、run_id 和 failure status；
- 不把 fixture、单测或 archive status 当作真实质量证据。

## 5. 明确不做

- 不因 75 个 available fields 就放行完整 baseline provider；
- 不用 `record_not_found`、`invalid_value`、`not_evaluated` 静默补默认值；
- 不把 baseline chain 的 partial evidence 描述成全字段 provider coverage；
- 不接入 LongPort/Longbridge production；
- 不将 adapter archive、commit、focused tests 或 partial runtime probe 描述为 G1/G2 passed；
- 不启动 G3 HoldingContract runtime；
- 不在 M4.5 diagnostic contract 冻结前执行最终 Council-vs-fallback A/B。

## 6. 下一次会话恢复点

先核验：

```bash
cd /Users/admin/Documents/trade-agent
git status --short --branch
git log -1 --oneline

cd /Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter
git status --short --branch
git log -5 --oneline
```

查看 corrected runtime evidence：

```bash
cat /Users/admin/Documents/trade-agent-runtime-evidence/g1-provider-qualification-20260805/baseline-20260805-b/manifest.json
```

若继续真实 provider 运行，必须使用：

```bash
/Users/admin/Documents/trade-agent/value-screener/.venv/bin/python
```

## 7. Suggested skills

- `openspec-apply-change`：继续 active OpenSpec child；
- `openspec-archive-change`：完成 change 后归档；
- `superpowers:requesting-code-review`：合入 main 前独立 review；
- `superpowers:verification-before-completion`：提交或宣称完成前验证；
- `superpowers:receiving-code-review`：处理新的 review findings；
- `superpowers:using-git-worktrees`：创建 clean integration worktree。
