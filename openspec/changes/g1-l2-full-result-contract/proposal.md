## Why

`scout/batch.py::scout_batch` 内部 `process_one` 已给每只输入标了 `verdict`（`deep_dive`/`watch`/`skip`/`error`/`degraded→watch`），但在返回点（`batch.py:193-195`）只保留 `verdict=="deep_dive"` 的候选，`watch`/`skip`/`error` 在此被**丢弃**；`usage_summary` 已累加所有 LLM 调用与 cache hit（f1 P1 修复✓），但**无 `failure_summary`**——哪些 ticker 走 `error`、原因是什么、降级分布如何，不可定位；`shortlist` 是当前**唯一**返回结果，而非由全量结果派生的视图。这违反 G1 umbrella spec 的「完整漏斗与失败结果」requirement（D5）：每只输入 MUST 归属 `deep_dive`/`watch`/`skip`/`error`，保留阶段/理由/降级/失败信息，shortlist MUST 由全量结果派生。本 change 闭合 L2 输出契约缺口——推进 G1 umbrella task 3.1。

## What Changes

- **BREAKING**：`scout_batch(candidates, force)` 返回值从二元组 `(shortlist, usage_summary)` 升级为三元组 `(full_results, usage_summary, failure_summary)`。
  - `full_results`：每只输入一条结果，含 `verdict`（`deep_dive`/`watch`/`skip`/`error`）、`one_liner`/`red_flags`/`green_flags`/`anti_trap_flags`/`low_confidence_anomaly`/`degraded`/`degraded_reason`/`error`/`usage`，长度 == 输入候选数 N（不再只留 deep_dive）。
  - `usage_summary`：契约不变（`call_count`/`cache_hits`/`prompt_tokens`/`completion_tokens`/`total_tokens`）。
  - `failure_summary`：新增，结构 `{"errors":[{ticker,reason,stage}], "skips":n, "watches":n, "degraded":n, "unhandled_exceptions":0}`，可定位失败 ticker 与原因，并把 availability/error/degraded 分开计数。
- `shortlist` 从 `full_results` 派生：`[r for r in full_results if verdict=="deep_dive"]` 按 `confidence` 降序取前 20（受既有 Top-20 Cap requirement 约束，不变）——不再是 `scout_batch` 的直接返回项，而是消费方从 `full_results` 派生的视图。
- 升级 3 个消费方以适配三元组：
  - `cli.py::scout`：output_payload 改为 `{"full_results":..., "shortlist":..., "usage_summary":..., "failure_summary":...}`，仍写 shortlist 供 L3 不变。
  - `monitor/weekly.py`：`l2_results` 改为消费 `full_results`；`l2_failed` 直接从 `failure_summary["errors"]` 取，不再从 deep_dive 列表里反推 error。
  - 4 个测试文件（`test_scout_batch`/`test_cli_scout`/`test_weekly`/`test_screener_stats`）的 mock 从二元组改三元组，并新增契约守护测试。

## Capabilities

### New Capabilities

无。本 change 不新建 capability，只给现有 `scout-agent` 增补返回契约 requirement。

### Modified Capabilities

- `scout-agent`: 新增「L2 全量结果契约」requirement——`scout_batch` SHALL 返回全量结果（每只输入一条 verdict 分类）、`usage_summary`（既有）和 `failure_summary`（新增）；`shortlist` SHALL 由 `full_results` 派生而非作为唯一返回；`failure_summary` SHALL 可定位失败 ticker 与原因，并把 `error`/`skip`/`watch`/`degraded` 分开计数；整批运行 SHALL 无未处理异常（`unhandled_exceptions == 0`）。既有 Top-20 Cap / Verdict Coverage Logic / L2 数据降级模式 requirement 语义不变。

## Impact

**受影响代码**：
- `value-screener/scout/batch.py` — `scout_batch` 返回三元组；`process_one` 不再丢 watch/skip/error；新增 failure_summary 汇总
- `value-screener/cli.py` — `scout` 命令 output_payload 升级
- `value-screener/monitor/weekly.py` — L2 重跑消费 full_results + failure_summary
- `value-screener/tests/test_scout_batch.py`、`tests/test_cli_scout.py`、`tests/test_weekly.py`、`tests/test_screener_stats.py` — mock 三元组 + 新增契约测试

**不受影响**：
- `scout/prompt.py` / `scout/parse.py` / `scout/input_assembly.py` / `scout/quality.py` — verdict 判定链与降级逻辑不动，只动返回承载
- `council/llm.py::call_llm_light` — usage 采集契约不变（已是 (content, usage)）
- L1 采集边界、canonical identity、ScreeningProfile、全市场性能（已闭合或属 G1-3/G1-4/G1-5）

**AD 引用**：
- **AD-10**（串行 Gate）：本 change 推进 G1 完整输出 Gate（umbrella 3.1），是 G1 通过的前置条件
- **AD-03**（成本闸门）：`failure_summary` 让 L2 成本审计可定位失败面，避免用 shortlist 掩盖 error/degraded 分布（spec「将 availability、degraded、error 分开统计，未达到 95% 时不允许用 shortlist 掩盖」）

**风险**：
- 三元组是 breaking change：所有 `scout_batch` 调用方与 mock 需同步升级。本 change 用契约测试守护，不保留旧二元组（否则"派生"语义被稀释）。
- `full_results` 体积约为 shortlist 的 ~10×（N 只 × red_flags/green_flags 数组）。CLI 写文件体积增大，但全市场吞吐与成本验证属 G1-5，本 child 只管契约正确。
- `degraded` 票 verdict 为 `watch`（非 `error`），不计入 `failure_summary["errors"]`，但 SHALL 单独计入 `failure_summary["degraded"]`，否则降级分布被 shortlist 掩盖。
