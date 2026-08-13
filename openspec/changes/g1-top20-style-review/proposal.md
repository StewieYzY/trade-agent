## Why

G1 umbrella（`g1-fast-personal-value-screening`）的产品 Gate（§6）要求：固定已通过工程 Gate 的 ScreeningProfile 与具体 run，由用户对 Top 20 逐只人工复核，至少 70% 被判断为“值得进一步研究”。前置里程碑 4.1/4.2（规模预检）与 5.1/5.2/5.3（全市场工程 Gate）已闭环：真实全市场 run `7887d515-157d-4d17-bcb5-fab54c7fbee3`（profile `g1-2026-07-21`，input hash `9d20ac29743c`，沪深 5208 只）证据归档于 `openspec/changes/archive/2026-08-12-g1-full-market-performance-cost/evidence/2026-08-12_7887d515.json`。但该 bundle 只保存聚合指标，未保存逐票候选结果；本 child 建立从该固定 run 可追溯地派生 Top 20、并承载用户逐只复核记录与 Gate 判定的最小产品能力。

## What Changes

- 新增 `g1-top20-style-review` 能力：从固定 run 的归档 evidence bundle 读取 pinned run identity（run_id、profile_version、input_ticker_set_hash、input_tickers），以确定性离线 L1 再派生（`allow_stale`，不调用 provider/LLM）复现候选排序，取前 20 作为用户复核对象。
- Pinned run 与 derivation run 的绑定校验：profile_version 与 input_ticker_set_hash 必须与 pinned run 一致，漏斗统计必须与 pinned bundle 一致；任一不一致 → `not_evaluable`，不得产生 Gate 通过结论。
- 新增用户复核记录合同：每只 Top 20 必须记录 ticker、rank、run identity、verdict/confidence 上下文、用户判断标签（`worth_further_research` / `not_worth_further_research` / `unable_to_judge_insufficient_data`）与逐只非空理由；缺票、重复、非法标签、空理由一律阻断。
- Gate 判定：20 只全部存在合法复核记录后才允许计算；`worth_research_count >= 14`（≥70%）为 `passed`，低于为 `failed`；任何缺失、身份不一致或非法输入为 `not_evaluable`。失败与不可判定 MUST NOT 被写成 capability passed。
- 新增可复核 evidence 输出：保留 pinned/derivation identity、逐只 Top 20 记录、逐只用户标签与理由、统计与 Gate verdict；运行产物写入 `value-screener/data/evidence/g1-top20-style-review/`（gitignore），最终复核副本归档到本 change `evidence/` 并登记 SHA-256。
- 新增 CLI 子命令 `top20 derive` 与 `top20 finalize`（挂在现有 typer app 下）。
- 不修改 L1 筛选规则、L2 scout、provider、ScreeningProfile 常量或任何既有 canonical spec 合同。
- 不修改 umbrella tasks.md 的 6.1/6.2 勾选（真实用户复核完成并获明确授权后才同步），不触碰 7.1/7.2/7.3，不 archive、不 merge、不 push。
- 不进入 G2/G3，不做前端，不做通用问卷系统；不使用 mock/fixture/历史 debate/watchlist 结果冒充本次用户 Gate。

## Capabilities

### New Capabilities

- `g1-top20-style-review`: 固定 run 的 Top 20 派生、用户逐只复核记录校验、70% Gate 判定与可审计 evidence 输出能力。

### Modified Capabilities

无。`g1-fast-personal-value-screening` umbrella、`quantitative-screener`、`scout-agent`、`run-identity`、`data-minimum-contract` 的 spec 只作为约束与引用，不修改其 requirement。

## Impact

- 新增 `value-screener/screener/top20_review.py`（派生、复核校验、Gate 统计、evidence 持久化的纯函数）与对应测试 `value-screener/tests/test_top20_review.py`。
- `value-screener/cli.py` 增加 `top20` 子命令组（derive/finalize），不改既有命令行为。
- 本 child 的 Gate 结论仅关闭 umbrella §6 的 6.1/6.2 证据链；6.2 `failed` 时按 umbrella 要求由新的校准 child change 处理，不在本 child 内扩大 scope。
- 本 child 完成（含用户复核通过）也不宣称 G1 capability passed；G1 通过与否仅在 umbrella closure（7.x）完成后判断。
