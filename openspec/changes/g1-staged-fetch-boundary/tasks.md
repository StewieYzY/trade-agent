# Implementation Tasks

> 本 child 按 TDD 节奏推进：每条 task 先写红测、再最小实现、再验证转绿、最后提交。引用 `staged-fetch-boundary` 与 `quantitative-screener` 两份 delta spec。

## 1. L1 采集维度白名单（spec: L1 主入口的采集维度边界）

- [x] 1.1 在 `value-screener/screener/main.py` 新增模块级常量 `G1_QUANT_DIMENSIONS = ("basic", "financials", "kline", "valuation", "risk")`，并使 `screen_a_shares` 调用 `fetch_all` 时显式传该常量（替换现状不传 dimensions 的 `fetcher.fetch_all(tickers)`）
- [x] 1.2 写红测：`test_screener_stats` 新增断言，`patch("screener.main.BatchFetcher")` 后调用 `screen_a_shares`，断言 `fetch_all` 收到的 `dimensions` 参数恰为 `G1_QUANT_DIMENSIONS`，且不含 `"main_business"`/`"peers"`/`"research"`
- [x] 1.3 写红测：断言 `screener.main.G1_QUANT_DIMENSIONS` 暴露为模块级常量且值有序
- [x] 1.4 实现转绿：运行红测确认 1.1 实现满足 1.2/1.3 断言（8 passed）

## 2. 漏斗 ticker 集合逐层缩小（spec: ticker 集合随漏斗逐层缩小）

- [x] 2.1 写红测：构造混合样本（部分过/不过 hard_gates、部分进/不进 top 300、部分过/不过 heat_filter），断言 `stats["total"] >= stats["after_hard_gates"] >= stats["after_factors"] >= stats["after_heat_filter"]`
- [x] 2.2 在 design.md / 本 tasks 记录下游缩小等价证据说明：L2 处理集合 = L1 `candidates`（≤ `after_heat_filter`）、L3 dossier fetch 集合 = L2 shortlist（≤20）——不新增 L2/L3 集成测试（属 G1-2/G3 scope），仅以现有行为 + 文档说明作为等价证据（说明见本文件末尾「下游缩小等价证据」附录）
- [x] 2.3 运行 2.1 红测确认漏斗单调性断言通过（现有 `screen_a_shares` 行为已满足；红测一即绿，确认无回归）

## 3. 单股失败隔离不回归（spec: 单股失败隔离不回归）

- [x] 3.1 写红测：构造某 ticker 的某量化维度 `fetch_with_fallback` 返回 `{"__error__": True}` 的 mock，断言 `screen_a_shares` 不抛异常、其他 ticker 与其他维度继续处理、该 ticker 仍出现在漏斗对应阶段统计中
- [x] 3.2 运行 3.1 红测确认现有 `BatchFetcher` resume/失败隔离行为在 dimensions 白名单化后不回归（红测即绿，确认无回归）

## 4. 全量验证与 strict validation

- [x] 4.1 运行 `value-screener/.venv/bin/python -m pytest value-screener/tests/test_screener_stats.py -q`，确认新测试通过（8 passed）
- [x] 4.2 运行 `value-screener/.venv/bin/python -m pytest value-screener/tests -q`，确认全量测试不回归（422 passed，无 `debate/`/`watchlist/` 副产物污染）
- [x] 4.3 运行 `openspec validate staged-fetch-boundary --type spec --strict`——结果 ENOENT（预期：`staged-fetch-boundary` 是本 child 新建 capability，归档前 canonical `openspec/specs/staged-fetch-boundary/spec.md` 尚不存在，与 G1-0 当初一致；以 change 级 4.5 验证为准）
- [x] 4.4 运行 `openspec validate quantitative-screener --type spec --strict`，确认通过（valid）
- [x] 4.5 运行 `openspec validate g1-staged-fetch-boundary --strict`，确认 change 整体通过（valid）
- [x] 4.6 运行 `openspec validate g1-fast-personal-value-screening --strict`，确认 umbrella 不被本 child delta 破坏（valid）

## 5. 独立 review 与提交

- [x] 5.1 独立 review：核对 `screener/main.py` 改动是否恰为「传 `G1_QUANT_DIMENSIONS`」，未顺带改 `batch_fetcher.py` 契约、未触 L2/L3（diff 确认仅 3 处：常量定义 + 注释 + fetch_all 传参；batch_fetcher/scout/council 零改动）
- [x] 5.2 核对 `git diff --check` 与 staged diff 无空白/无关改动（clean）
- [x] 5.3 提交（commit message：`feat(g1): staged fetch boundary — L1 不采 dossier 维度`）（commit `079e048`，分支 `feat/g1-staged-fetch-boundary`）
- [x] 5.4 生成下一份 rolling handoff（更新 baseline、上一 child 证据、剩余风险、推进 umbrella 2.1/2.2 勾选）

## 附录：下游缩小等价证据（task 2.2）

本 child 不新增 L2/L3 集成测试（属 G1-2 L2 contract / G3 dossier scope），仅以现有行为 + 本说明作为「后续 fetch 调用的 ticker 集合随漏斗缩小」的等价证据：

| 阶段 | ticker 集合来源 | 上界 | 代码实证 |
|---|---|---|---|
| L1 `fetch_all` 输入 | `screen_a_shares(tickers)` 入参 | = `stats["total"]` | `screener/main.py` 全量一次采 |
| L1 hard_gates 后 | `after_hard_gates` | ≤ total | `main.py` `for ticker in tickers` 过 `check_hard_gates` |
| L1 factors 后（top 300） | `after_factors` | ≤ after_hard_gates | `main.py` `candidates_with_scores.sort()[:300]` |
| L1 heat_filter 后 | `after_heat_filter` | ≤ after_factors | `main.py` `for candidate in top_300: check_heat_filter` |
| L1 输出 candidates | = after_heat_filter | ≤ after_heat_filter | `main.py` 输出 `final_candidates` |
| **L2 处理集合** | L1 `candidates` | ≤ after_heat_filter | `scout/batch.py::scout_batch` `tasks = [process_one(c) for c in candidates]`，c 来自 L1 candidates |
| L2 shortlist 输出 | `deep_dive[:20]` | ≤ 20 | `scout/batch.py` `deep_dive.sort(...)[:20]` |
| **L3 dossier fetch 集合** | L2 shortlist | ≤ 20 | `council/debate.py` 入口对 L2 shortlist 逐只调 `build_research_dossier` |

L1 漏斗反向单调性由 `test_funnel_counts_monotonically_non_increasing` 守护；L2/L3 的 ticker 缩小由各自现有代码逻辑保证（L2 只迭代 L1 candidates、L3 只对 L2 shortlist 调 dossier fetcher），其契约级测试属 G1-2（L2 full-result contract）与 G3（dossier）child scope。
