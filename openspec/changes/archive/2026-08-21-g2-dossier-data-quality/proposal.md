## Why

G2 2.x 的“可信 Investment Thesis”要求至少 95% 的关键事实和数字能定位到输入来源、
报告期或 `as_of`，且高严重度凭空数字为 0。当前 `build_research_dossier` 只拼接
`main_business`、`peers`、`research` 和 `capex_proxy` 的原始 fetcher 返回，没有
字段级 source / report_period / published_at / freshness / degradation_status 契约，
也没有任何机制阻止无来源的高严重度数字进入 clean dossier。

## What Changes

- 新增角色事实契约层，把 `main_business`、`peers`、`research`、`capex_proxy` 中
  出现的每个关键数字绑定 source、report_period、published_at、retrieved_at、
  freshness 和 degradation_status。
- 为关键事实保存并输出可复核的追溯统计口径：事实总数、可追溯数、追溯率、
  高严重度事实数、高严重度不可追溯数、stale 数和降级数。
- 缺失 source / 时间基准（report_period 或 as_of）、或来源与数字不匹配的高严重度
  事实 fail closed，禁止其进入 clean dossier。
- stale 或降级事实不得表示为 clean evidence：dossier 显式携带 `fact_contract`、
  `quality_status` 和 `quality_reasons`，下游可读取。
- `build_research_dossier` 返回结构增加 `fact_contract`、`quality_status`、
  `quality_reasons`，但不改变现有 `core_snapshot` / `research_dossier` 原始 role
  payload 形状，也不修改主 prompt、debate 编排或审计链主契约。

## Capabilities

### New Capabilities

- `dossier-fact-grounding`: dossier 角色事实的字段级来源追溯、新鲜度、降级状态、
  追溯率统计和高严重度凭空数字 fail-closed 契约。

### Modified Capabilities

- `research-dossier`: `build_research_dossier` 返回结构增加事实契约与质量状态，
  并在高严重度事实不可追溯时 fail closed。

## Impact

- 新增 `value-screener/council/fact_grounding.py`（纯 Python，零 LLM，零新依赖）。
- 修改 `value-screener/council/research_dossier.py`，在组装末尾挂事实契约并
  执行高严重度 fail-closed 校验。
- 新增/调整 `value-screener/tests/test_research_dossier.py` 和
  `value-screener/tests/test_dossier_fact_grounding.py`。
- 不修改 `council/debate.py`、`council/prompt.py`、`data/lib/audit_chain.py`、
  `data/lib/provenance.py` 或三个 fetcher；不调用真实 provider/LLM。
