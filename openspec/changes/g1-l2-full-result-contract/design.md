## Context

G1 umbrella `g1-fast-personal-value-screening` 的 task 3.1 要求：建立并归档 L2 full-result contract child change，输出 `deep_dive`/`watch`/`skip`/`error`、`usage` 和 `failure_summary`。对应 umbrella spec「完整漏斗与失败结果」requirement（D5）：每只输入 MUST 归属四类，保留阶段/理由/降级/失败信息，shortlist MUST 由全量结果派生。

**当前真实返回链路（实证）**：

```
scout_batch(candidates, force)
  │
  ├─ process_one() × N (asyncio.gather)
  │   每只内部已标 verdict ∈ {deep_dive, watch, skip, error, degraded→watch}
  │   + 单只 usage 保留在 result["usage"]
  │   + error/degraded 原因在 result["error"]/["degraded_reason"]
  └─ raw_results = 全量结果（N 条）   ← 内部已有全量
        │
        ▼  返回点 batch.py:193-195（缺口在这）
  deep_dive = [r for r in results if verdict=="deep_dive"]
  return deep_dive[:20], usage_summary      ← watch/skip/error 被丢弃
```

关键事实：

1. `scout/batch.py::scout_batch`（`batch.py:37`）当前签名为 `-> tuple[list[dict], dict]`，返回 `(shortlist, usage_summary)`。
2. `process_one`（`batch.py:83`）内部对每只输入已生成完整 result：`deep_dive`/`watch`/`skip`/`error`/`degraded→watch` 五种 verdict 分支齐全，含 `one_liner`/`red_flags`/`green_flags`/`anti_trap_flags`/`low_confidence_anomaly`/`degraded`/`degraded_reason`/`error`/`usage`——**全量结果在内存中已存在**，只是返回点过滤掉了非 deep_dive。
3. 返回点（`batch.py:193-195`）：`deep_dive = [r for r in results if verdict=="deep_dive"]` → 只返 deep_dive，watch/skip/error 在此被丢弃。
4. `usage_summary`（`batch.py:66-81`）已累加所有 LLM 调用 + cache_hits（f1 P1 修复✓），契约成熟，不需改。
5. **无 `failure_summary`**：哪些 ticker 走 error、原因是什么、降级分布如何，当前无结构化汇总。
6. 消费方 3 处 + 测试 4 文件，mock 了二元组：
   - `cli.py:308`：`shortlist, usage_summary = scout_batch()` → `output_payload={"shortlist":..., "usage_summary":...}`，只持久化 shortlist。
   - `monitor/weekly.py:106`：`l2_results, _usage = scout_batch()`，把 deep_dive 列表当全量用；`batch.py:109-117` 从 deep_dive 列表里反推 error（`result.get("error")`），但 deep_dive 列表里**不可能**有 error 票（已被返回点过滤），`l2_failed` 实际永远为空——这是当前契约的直接 bug 证据。
   - `test_scout_batch.py`（8 测试）、`test_cli_scout.py`、`test_weekly.py`（4 处 AsyncMock）、`test_screener_stats.py:178`。

## Goals / Non-Goals

**Goals:**

- 让 `scout_batch` 返回 `(full_results, usage_summary, failure_summary)` 三元组，`full_results` 保留每只输入的 verdict 分类与可审计信息，`watch`/`skip`/`error` 不再在返回点被丢弃。
- 让 `shortlist` 由消费方从 `full_results` 派生（受既有 Top-20 Cap 约束），而非作为 `scout_batch` 的唯一返回项。
- 新增 `failure_summary`：可定位每个 error 的 ticker、原因与失败阶段，并把 `error`/`skip`/`watch`/`degraded` 分开计数，`unhandled_exceptions == 0`。
- 升级 3 个消费方（cli/weekly/4 测试文件）以适配三元组，并新增契约守护测试。
- 推进 G1 umbrella task 3.1。

**Non-Goals:**

- 不做 canonical ticker / `run_id` / ScreeningProfile version / 输入快照——属 G1-3。
- 不做 300+ 样本或全市场性能/成本 Gate——属 G1-4、G1-5。
- 不改 L1 采集边界（已闭合）。
- 不改 L2 prompt / parse / 降级判定逻辑（verdict 判定链不动，只动返回承载与汇总）。
- 不改 `call_llm_light` 的 `(content, usage)` 契约。
- 不顺手开发 G3 runtime、前端或部署。

## Decisions

### D1：岔口 B——`full_results` 在内存返回，不碰 run_id/输入快照

**选择**：岔口 B——只扩 `scout_batch` 返回契约（内存三元组），`run_id`/输入快照/ScreeningProfile version 留 G1-3。

**备选 A（带 identity）**：在 `full_results` 每条加 `run_id`/输入快照 hash/规则版本字段，让结果可定位到 run。

**为什么选 B 不选 A**：
- A 触碰 canonical run identity，违反 child Non-Goal「不做 canonical ticker/run identity」与 G1 umbrella task 3.2 的边界。
- 本 child 的 Gate 是 3.1「L2 full-result contract」——只需证明输出含四类 verdict + usage + failure_summary + shortlist 派生。identity 全链路是 3.2 独立 Gate，混进来会稀释本 child 的可验收性。
- `full_results` 在 `process_one` 内部已存在，升级返回契约是零风险的数据承载改造，不引入新的持久化或 identity 机制。

### D2：三元组返回契约 `(full_results, usage_summary, failure_summary)`

**选择**：`scout_batch` 返回三元组，`full_results` 为每只输入一条（长度 == N，含 cache hit 与 degraded），`usage_summary` 契约不变，`failure_summary` 新增。

**备选 B'（二元组 + 字典包）**：返回 `(result_bundle, )` 其中 `result_bundle = {"full_results":..., "shortlist":..., "usage_summary":..., "failure_summary":...}`。

**为什么三元组不选 B'**：
- `usage_summary` 已是成熟契约（f1 P1 修复 + cli/weekly/测试都解构它），包进字典会破坏现有解构代码且无收益。
- 三元组让 `usage_summary` 作为独立第二返回项，消费方 `l2_results, _usage = scout_batch()` 的现有解构模式最小改动（只多一个 failure_summary）。
- breaking change 不可避免（这是本 child 的目的），但用三元组而非字典包可以把 breaking 面收敛在「多一个返回项」而非「整体形状改变」。

**`full_results` 结构**：每条含 `ticker`/`verdict`/`one_liner`/`red_flags`/`green_flags`/`anti_trap_flags`/`low_confidence_anomaly`，degraded 票加 `degraded`/`degraded_reason`，error 票加 `error`/`missing_fields`，cache hit 票加 `from_cache`。保留单只 `usage`（向后兼容，已有）。

**`failure_summary` 结构**：
```python
{
    "errors": [{"ticker": str, "reason": str, "stage": str}, ...],  # 可定位失败 ticker
    "skips": int,        # verdict=="skip" 计数
    "watches": int,      # verdict=="watch" 计数（含 degraded→watch 的票）
    "degraded": int,     # degraded==True 计数（单独计，不进 errors）
    "unhandled_exceptions": 0,   # 兜底异常计数，MUST 为 0
}
```

### D3：`shortlist` 派生规则与 Top-20 Cap 的关系

`shortlist` 不再是 `scout_batch` 的返回项。消费方从 `full_results` 派生：
```python
shortlist = sorted([r for r in full_results if r["verdict"]=="deep_dive"],
                   key=lambda x: x.get("confidence",0), reverse=True)[:20]
```
受既有 `scout-agent` spec 的「Top-20 Cap」requirement 约束（≤20、按 confidence 降序），语义不变——只是承载位置从「返回项」变「消费方派生」。CLI `scout` 命令仍在 payload 写 `shortlist` 字段供 L3 消费不变。

### D4：消费方升级策略

| 消费方 | 当前 | 升级后 |
|---|---|---|
| `cli.py:308` | `shortlist, usage = scout_batch()`；payload `{shortlist, usage_summary}` | `full, usage, failures = scout_batch()`；派生 `shortlist`；payload `{full_results, shortlist, usage_summary, failure_summary}` |
| `monitor/weekly.py:106` | `l2_results, _usage = scout_batch()`，从 deep_dive 列表反推 error（实际 `l2_failed` 永远空） | `l2_results, _usage, failures = scout_batch()`；`l2_results` 消费 full_results；`l2_failed = [e["ticker"] for e in failures["errors"]]`；`l2_new_verdicts` 从 full_results 全量遍历（不再只 deep_dive） |
| 4 测试文件 | mock 二元组 | mock 三元组 + 新增契约守护测试 |

**关键修复**：`weekly.py:109-117` 当前从 deep_dive 列表里 `if result.get("error")` 反推 `l2_failed`，但 deep_dive 列表不可能含 error 票（返回点已过滤），`l2_failed` 永远为空——这是当前契约的潜伏 bug。升级后从 `failure_summary["errors"]` 直接取，bug 随契约闭合。

### D5：`degraded` 在 `failure_summary` 的归属

`degraded` 票 verdict 为 `watch`（非 `error`，见 `batch.py:121-134`），不计入 `failure_summary["errors"]`，但 SHALL 单独计入 `failure_summary["degraded"]`。

**为什么单独计 degraded 不进 errors**：
- degraded 是「数据不全但可降级处理」的软状态，不是失败——票仍进了 watch，进了 `full_results`。
- spec「将 availability、degraded、error 分开统计，未达到 95% 时不允许用 shortlist 掩盖」隐含要求三者分开可见。
- 若 degraded 计入 errors，会让 error 计数虚高，掩盖真实失败面；若不计任何字段，降级分布被 shortlist 掩盖。

`watches` 计数含 degraded→watch 的票（verdict 都是 watch），`degraded` 是其中 `degraded==True` 的子集。

## Risks / Trade-offs

- **[breaking change]** 三元组是 breaking change，所有 `scout_batch` 调用方与 mock 需同步升级。→ **缓解**：本 child 的目的就是闭合契约，用契约测试守护；不保留旧二元组（否则"派生"语义被稀释，error/skip 仍可能被旧路径丢弃）。
- **[full_results 体积]** `full_results` 约为 shortlist 的 ~10×（N 只 × red_flags/green_flags 数组）。CLI 写文件体积增大。→ **缓解**：本 child 只管契约正确；全市场吞吐与文件体积验证属 G1-5，且 `full_results` 是可审计性的必要代价（shortlist 唯一返回无法计算失败分布）。
- **[weekly.py 潜伏 bug 修复]** 升级会暴露并修复 `l2_failed` 永远空的 bug。→ **缓解**：这是契约闭合的直接收益，不是风险；新增测试守护 `l2_failed` 从 `failure_summary["errors"]` 取。
- **[测试 mock 改造量大]** 4 文件 mock 二元组需改三元组。→ **缓解**：mock 改造是机械的（多一个返回项），且本 child 新增契约测试覆盖 watch/skip 留存、failure_summary 结构、unhandled_exceptions=0，收益大于改造成本。
- **[degraded 计数归属分歧]** degraded 单独计还是进 errors 有判断空间。→ **缓解**：design D5 明确单独计 degraded、不进 errors，与 spec「分开统计」对齐；若 review 有异议在此点提出。
