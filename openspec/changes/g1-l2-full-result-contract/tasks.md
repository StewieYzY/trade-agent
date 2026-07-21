# Implementation Tasks

> 本 child 按 TDD 节奏推进：每条 task 先写红测、再最小实现、再验证转绿、最后提交。引用 `scout-agent` delta spec（ADDED「L2 全量结果契约」requirement）。breaking change：`scout_batch` 返回从二元组升级为三元组，所有调用方与 mock 同步升级。

## 1. scout_batch 返回三元组（spec: L2 全量结果契约 — full_results + 三元组）

- [x] 1.1 写红测：`test_scout_batch.py` 新增 `test_scout_batch_returns_triple_with_full_results`——构造 3 只候选 LLM 分别返回 `deep_dive`/`watch`/`skip`，断言 `scout_batch` 返回三元组 `(full_results, usage_summary, failure_summary)`，`full_results` 长度为 3，三条均含 `verdict`（`deep_dive`/`watch`/`skip`），MUST NOT 只保留 deep_dive
- [x] 1.2 写红测：`test_scout_batch_returns_shortlist_derived_from_full_results`——断言 `shortlist`（消费方从 full_results 派生）等于 `[r for r in full_results if verdict=="deep_dive"]` 按 confidence 降序取前 20，MUST NOT 是 scout_batch 的独立返回项（scout_batch 返回三元组，第二项是 usage_summary 不是 shortlist）
- [x] 1.3 实现转绿：改 `scout/batch.py::scout_batch` 返回点为 `return results, usage_summary, failure_summary`（`results` 为全量 N 条，不再过滤 deep_dive），新增 `failure_summary` 汇总逻辑；保留单只 result 的 `usage`/`degraded`/`error` 字段不变
- [x] 1.4 运行 1.1/1.2 红测确认转绿（2 passed）

## 2. failure_summary 结构与分类计数（spec: failure_summary 可定位 + 分开计数）

- [x] 2.1 写红测：`test_scout_batch_failure_summary_locates_error_ticker`——构造 `600002` 的 LLM 调用抛 `httpx.HTTPStatusError`，断言 `failure_summary["errors"]` 含 `{"ticker":"600002","reason":<错误描述>,"stage":<失败阶段>}`，其他成功候选仍在 full_results
- [x] 2.2 写红测：`test_scout_batch_failure_summary_counts_separated`——构造一批含 1 error/2 skip/1 degraded→watch/1 deep_dive，断言 `failure_summary == {"errors":1,"skips":2,"watches":1,"degraded":1,"unhandled_exceptions":0}`（degraded 不计 errors 单独计；watches 含 degraded→watch 的票）
- [x] 2.3 写红测：`test_scout_batch_unhandled_exceptions_zero`——构造某只票触发非预期异常（mock `assemble_snapshot` 抛 `TypeError`），断言该只进 `failure_summary["errors"]`，`unhandled_exceptions == 0`，整批不中断
- [x] 2.4 实现转绿：在 `scout_batch` 内构建 `failure_summary`：遍历 `results` 按 verdict 分类计数，error 收集 `{ticker,reason,stage}`，degraded 单独计；`process_one` 兜底 `except Exception` 计入 errors（已处理，不累加 unhandled_exceptions——该字段计逃逸 gather 的异常，兜底 catch all 保证恒为 0）
- [x] 2.5 运行 2.1/2.2/2.3 红测确认转绿（3 passed）

## 3. usage_summary 契约不回归（spec: usage_summary 累加所有调用）

- [x] 3.1 写红测：`test_scout_batch_usage_summary_unchanged_after_triple_upgrade`——基于现有 `test_scout_batch_returns_tuple_with_usage_summary` 改造，断言三元组第二项 `usage_summary` 结构与值不变（call_count 累加 deep_dive/watch/skip 三次、cache_hits 单独计），证明三元组升级未破坏 usage 契约
- [x] 3.2 运行 3.1 确认现有 usage 逻辑在三元组升级后不回归（2 passed）

## 4. 消费方升级：CLI scout 命令（spec: shortlist 派生 + full_results 持久化）

- [x] 4.1 写红测：`test_cli_scout.py` 改造 mock 为三元组，断言 output_payload 含 `full_results`/`shortlist`/`usage_summary`/`failure_summary` 四字段；`shortlist` 为从 full_results 派生的 deep_dive[:20]
- [x] 4.2 实现转绿：改 `cli.py::scout` 解构 `full_results, usage_summary, failure_summary = asyncio.run(scout_batch(...))`，派生 shortlist，output_payload 改为四字段
- [x] 4.3 运行 4.1 红测确认转绿；确认 CLI 输出的 token usage 行不变（usage_summary 解构不变）（3 passed）

## 5. 消费方升级：monitor/weekly L2 重跑（spec: failure_summary 定位 + 修复 l2_failed 潜伏 bug）

- [x] 5.1 写红测：`test_weekly.py` 改造 4 处 AsyncMock 为三元组；新增断言：`l2_failed` 从 `failure_summary["errors"]` 的 ticker 取（而非从 deep_dive 列表反推），`l2_new_verdicts` 从 full_results 全量遍历（含 watch/skip，非只 deep_dive）
- [x] 5.2 实现转绿：改 `monitor/weekly.py:106` 解构三元组，`l2_results` 消费 full_results；`l2_failed = [e["ticker"] for e in failure_summary["errors"]]`；line 109-117 遍历 full_results 全量记录 `l2_new_verdicts`
- [x] 5.3 运行 5.1 红测确认转绿；确认修复了「l2_failed 永远空」的潜伏 bug（6 passed，含 `test_run_weekly_l2_failure_skips_l3` 的 bug 修复验证）

## 6. 测试文件 mock 升级与契约守护（spec: 全量结果含所有分类 + shortlist 派生）

- [x] 6.1 改 `test_scout_batch.py` 现有 8 测试的 mock 为三元组（`result, _usage` → `full, _usage, _fail` 或按需解构 failure_summary）；保留 top-20 cap / error_handling / insufficient_data / cache_hit / cache_write_failure / degraded 测试语义不变
- [x] 6.2 改 `test_screener_stats.py:178` 的 `result, _usage = scout_batch()` 为三元组解构（只读 ticker，影响小）
- [x] 6.3 运行改后测试确认全绿（4 文件 33 passed）

## 7. 全量验证与 strict validation

- [x] 7.1 运行 `cd /Users/admin/Documents/trade-agent/value-screener && .venv/bin/python -m pytest tests/test_scout_batch.py tests/test_cli_scout.py tests/test_weekly.py tests/test_screener_stats.py -q`，确认新测试通过（33 passed）
- [x] 7.2 运行 `cd /Users/admin/Documents/trade-agent/value-screener && .venv/bin/python -m pytest tests -q`，确认全量测试不回归（430 passed，比 G1-1 的 425 多 5 个 contract 测试，无回归）；本轮运行产生的 `debate/`/`watchlist/` 副产物已清理（3 个今日文件删除）
- [x] 7.3 运行 `openspec validate g1-l2-full-result-contract --strict`，确认 change 整体通过（valid）
- [x] 7.4 运行 `openspec validate scout-agent --type spec --strict`——**valid**（修正预期：`scout-agent` canonical spec 已存在，非新建 capability，delta 在归档前未同步但 canonical 本身 valid；归档时 ADDED requirement 同步进 canonical）
- [x] 7.5 运行 `openspec validate g1-fast-personal-value-screening --strict`，确认 umbrella 不被本 child delta 破坏（valid）

## 8. 独立 review 与提交

- [x] 8.1 独立 review：核对 `scout/batch.py` 改动是否恰为「返回三元组 + failure_summary 汇总」，未顺带改 prompt/parse/input_assembly/quality/llm（diff 确认 verdict 判定链零改动）
- [x] 8.2 核对消费方升级是否覆盖全部 3 处（cli/weekly/4 测试文件），无遗漏二元组解构（`grep "return deep_dive\|, usage_summary)"` 仅 1 处返回点为三元组）
- [x] 8.3 核对 `git diff --check` 与 staged diff 无空白/无关改动（clean）
- [x] 8.4 提交（commit message：`feat(g1): L2 full-result contract — scout_batch 返回全量结果 + failure_summary`）（分支 `feat/g1-l2-full-result-contract`，基于含 G1-1 的 main）
- [x] 8.5 勾选 `g1-fast-personal-value-screening/tasks.md` 的 3.1

## 9. 归档与 canonical 同步

- [ ] 9.1 运行 `/opsx:archive g1-l2-full-result-contract`，同步 `scout-agent` delta（ADDED「L2 全量结果契约」requirement）到 `openspec/specs/scout-agent/spec.md`
- [ ] 9.2 归档后验证：`openspec validate scout-agent --type spec --strict` 通过（canonical 已同步）；`openspec validate g1-fast-personal-value-screening --strict` 通过
- [ ] 9.3 提交归档（commit message：`chore(g1): archive g1-l2-full-result-contract + sync canonical specs`）
- [ ] 9.4 生成下一份 rolling handoff（更新 baseline、上一 child 证据、剩余风险、推进 umbrella 3.1 勾选、下一 child G1-3）

## 附录：消费方波及面与潜伏 bug 修复说明

本 child 的 breaking change（二元组 → 三元组）波及 3 处运行时消费方 + 4 个测试文件：

| 消费方 | 位置 | 升级动作 | 潜伏 bug 修复 |
|---|---|---|---|
| CLI scout | `cli.py:308` | 解构三元组，payload 加 full_results+failure_summary，shortlist 派生 | 无（CLI 本就只写 shortlist，加 full_results 是纯增） |
| monitor/weekly | `weekly.py:106` | 解构三元组，l2_results 消费 full_results | **是**：`l2_failed` 当前从 deep_dive 列表反推 error，但 error 票已被返回点过滤 → `l2_failed` 永远空；升级后从 `failure_summary["errors"]` 取 |
| test_scout_batch | 8 测试 | mock 二元组 → 三元组 | 无 |
| test_cli_scout | 1 处 | mock 二元组 → 三元组 | 无 |
| test_weekly | 4 处 AsyncMock | mock 二元组 → 三元组 | 配合 weekly.py 的 l2_failed 修复断言 |
| test_screener_stats | 1 处 (`:178`) | mock 二元组 → 三元组 | 无（只读 ticker） |

**潜伏 bug 根因**：`weekly.py:109-117` 当前逻辑为 `for result in l2_results: if result.get("error"): l2_failed.append(ticker)`，但 `l2_results` 是 deep_dive 列表（`scout_batch` 返回点已过滤非 deep_dive），error 票 verdict 为 `error` 不可能出现在 deep_dive 列表里 → `l2_failed` 永远为空。这不是本 child 引入的 bug，是上一轮二元组契约的潜伏缺陷，随三元组契约闭合一并修复（task 5.3 守护）。

## 附录：Non-Goals 边界

- 不做 canonical ticker / run_id / ScreeningProfile version / 输入快照——属 G1-3（`g1-canonical-run-identity`）。
- 不做 300+ 样本或全市场性能/成本 Gate——属 G1-4、G1-5。
- 不改 L1 采集边界（已闭合）。
- 不改 L2 prompt / parse / 降级判定逻辑——verdict 判定链不动，只动返回承载与汇总。
- 不改 `call_llm_light` 的 `(content, usage)` 契约。
- 不顺手开发 G3 runtime、前端或部署。
