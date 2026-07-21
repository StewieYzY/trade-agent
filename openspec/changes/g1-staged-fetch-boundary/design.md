## Context

G1 umbrella `g1-fast-personal-value-screening` 的 task 2.1、2.2 要求：证明 G1 全市场 L1 路径不默认采集 G2 dossier 维度，并用调用计数或等价证据证明 ticker 集合随漏斗逐层缩小。

**当前真实调用边界（实证）**：

```
维度         L1漏斗读取        L2读取            G2/L3 dossier读取   BatchFetcher默认采?
───────── ─────────────── ─────────────── ─────────────────── ──────────────
basic      ✅ hard_gates     ✅ get(t,"basic")  core_snapshot 间接   ✅
financials ✅ hg/factor/anti  ✅                capex_proxy          ✅
kline      ✅ heat_filter    ✅                —                    ✅
valuation  ✅ factor         ✅                —                    ✅
risk       ✅ hg/factor/main ✅                pledge               ✅
═══ G1/G2 分界 ═══════════════════════════════════════════════════
main_business ❌ 从不读取    ❌ 从不读取        ✅ _fetch (核心)      ✅(潜伏浪费)
peers      ❌ 从不读取       ❌ 从不读取         ✅ _fetch (降级)      ✅(潜伏浪费)
research   ❌ 从不读取       ❌ 从不读取         ✅ _fetch (降级)      ✅(潜伏浪费)
```

关键事实：

1. `BatchFetcher._DIM_FETCHERS`（`data/lib/batch_fetcher.py:31`）把 8 个维度 fetcher 注册在一张表里，其中 dossier 三维（`main_business`/`peers`/`research`）与 G1 量化五维混在一起。
2. `BatchFetcher.fetch_all(tickers, dimensions=None)`（`batch_fetcher.py:51`）在 `dimensions is None` 时 `dims = list(_DIM_FETCHERS.keys())` → 采全 8 维，含 dossier 三维。
3. `screener/main.py::screen_a_shares`（`main.py:47`）调用 `fetcher.fetch_all(tickers)` **不传 `dimensions`** → 等价于全市场路径默认采集 dossier 三维。
4. L1 漏斗（`hard_gates.py`/`factor_scores.py`/`anti_trap.py`/`heat_filter.py`）与 L2 `assemble_snapshot`（`scout/input_assembly.py`）对 dossier 三维的 `.get()` 调用**零命中**——这三个维度在 G1 管线里从未被消费。
5. CLI `batch` 子命令默认 dims 是 5 维（`cli.py:195` `dims = "basic,financials,kline,valuation,risk"`），但 CLI `screen` 走 `screen_a_shares()` 不传 dims——**同一仓库两条路径行为不一致**，是 boundary 缺口的直接证据。
6. 现有测试 `test_screener_stats.py` mock 了 `BatchFetcher`，但**未断言传入的 `dimensions` 参数**——L1 是否采 dossier 三维当前无测试守护。

G2/L3 路径（`council/research_dossier.py::build_research_dossier`）是独立路径，绕开 `BatchFetcher`，显式调 dossier 三维 fetcher（`_fetch_main_business`/`_fetch_peers`/`_fetch_research`），并通过 `_read_cache` 复用 L1 已采的 `financials`/`risk` cache。这条路径**不受** L1 dimensions 改动影响。

## Goals / Non-Goals

**Goals:**

- 让 `screen_a_shares()` 显式只采集 G1 量化五维白名单，从源头杜绝全市场路径默认采集 dossier 三维。
- 用行为测试守护「L1 不采 dossier 三维」这一不变量（对 `screen_a_shares` 这一个调用点）。
- 用 L1 漏斗各阶段计数（`after_hard_gates` ≤ `after_factors` ≤ `after_heat_filter` 的反向单调性，即 `final ≤ after_factors ≤ after_hard_gates ≤ total`）+ 下游 L2/L3 实际消费 ticker 集合的等价证据，证明 ticker 集合随漏斗逐层缩小。
- 推进 G1 umbrella task 2.1、2.2。

**Non-Goals:**

- 不改 `BatchFetcher.fetch_all` 的 `dimensions=None` 全采兜底契约（见决策 D2）。
- 不重构 L1 为 staged fetch（按漏斗阶段分批采集，见决策 D1）。
- 不改 L2 输出契约（deep_dive/watch/skip/error + usage + failure summary）——属 G1-2。
- 不做 canonical ticker/run identity ——属 G1-3。
- 不做 300+ 样本、全市场性能或成本 Gate——属 G1-4、G1-5。
- 不把 G2 dossier fetcher 逻辑整体重构；只建立 G1/G2 边界和可验证的调用计划。
- 不顺带改 G2/G3、前端、部署。
- 不覆盖未来新增的 L1 `fetch_all` 调用点（本 change 只守护 `screen_a_shares` 这一个）。

## Decisions

### D1：task 2.2「ticker 集合随漏斗缩小」= 证明下游消费缩小，非 staged fetch 重构

**选择**：岔口 B——证明「后续 fetch 调用」的 ticker 集合随漏斗缩小，不重构 L1 内部为按阶段分批采集。

**备选 A（staged fetch）**：把 `fetch_all` 拆成 hard_gate 前采轻维度、过 hard_gate 后采重维度（financials/kline）的两段编排。

**为什么选 B 不选 A**：
- A 触碰 L1 编排顺序与 `fetch_all` 契约，违反 child Non-Goal「不做全市场性能」「不把 G2 dossier fetcher 逻辑整体重构」。
- handoff step 5 的证明语「hard gate/factor/heat 等漏斗阶段后，**后续 fetch 调用**的 ticker 集合真实缩小」——"后续 fetch 调用" 指下游 L2/L3 阶段的 fetch，不是 L1 内部的 `fetch_all`。L1 的 `fetch_all` 在漏斗前一次性采完，本身不随漏斗缩小，这是当前架构事实。
- B 的证据形态贴合现状：L1 漏斗输出 `after_hard_gates/after_factors/after_heat_filter` 三级计数天然单调缩小；L2 `scout_batch` 只对 L1 `candidates` 调 LLM；L3 dossier fetch 在 `council/debate.py::run_debate(ticker)` 单票入口（CLI `council --ticker`）内部经 `build_research_dossier(ticker)` 触发，批量 L3 触发发生在 `monitor/weekly.py` 的 `for ticker in l3_triggers` 循环（触发源是基于 L2 重跑后新 verdict 的 ticker 集合，非直接等于 L2 shortlist）。这些缩小关系**已经成立**，只需被显式证明/测试，不需要新编排。

**证据要求**：
- L1 内部：`screen_a_shares` 输出的 `stats` 含 `total ≥ after_hard_gates ≥ after_factors ≥ after_heat_filter` 的反向单调断言（构造能过/不能过各 gate 的样本，且需 >300 只过 hard_gates 才能激活 `[:300]` 截断证明 top-300 阶段缩小）。
- 下游 fetch：L2 `scout_batch` 实际处理的 ticker 集合 = L1 `candidates`（≤ `after_heat_filter`）；L3 dossier fetch 的 ticker 集合来自 `monitor/weekly.py` 的 `l3_triggers` 循环（基于 L2 重跑新 verdict，≤ L2 处理集合），单票 dossier fetch 在 `run_debate(ticker)`→`build_research_dossier(ticker)` 内发生。本 change 用单元测试断言 L1 漏斗单调性 + top-300 截断作为主证据，L2/L3 下游缩小用现有行为（已成立）+ 在 design/tasks 记录为等价证据说明，不新增 L2/L3 集成测试（属各自 child scope）。

### D2：只改 L1 调用点，不改 `fetch_all` 的 `dimensions=None` 兜底契约

**选择**：在 `screener/main.py::screen_a_shares` 调用 `fetch_all` 时显式传入 G1 量化五维白名单；`batch_fetcher.py::fetch_all` 的 `dimensions=None` 全采兜底**保持不变**。

**备选 B'（改契约）**：取消 `fetch_all` 的 `None` 兜底，强制传 dimensions，或在 `batch_fetcher.py` 新增 `L1_DIMENSIONS` 常量并改默认值。

**为什么只改调用点**：
- `fetch_all` 的 `None → 全采` 是 CLI `batch`（默认 5 维）与潜在未来调用方的通用兜底，改契约有回归面（需审计所有 `fetch_all` 调用点），超出 child scope。
- 本 change 的目标是用**测试**守住「L1 不采 dossier」这一条不变量，而非把不变量塞进 `fetch_all` 类型签名。G1 umbrella 把全市场采集边界的证据闭环放在 task 2.1，契约层改造不是本 Gate 的要求。
- 调用点显式传参后，「L1 不采 dossier」由 `test_screener_stats` 新增的 dimensions 断言守护；若未来新增 L1 调用点忘记传参，由其所属 child 的测试负责（符合 umbrella 分 child 治理）。

**G1 量化五维白名单定义**：`("basic", "financials", "kline", "valuation", "risk")`。放在 `screener/main.py` 作为模块级常量（如 `G1_QUANT_DIMENSIONS`），便于测试 import 断言，且不污染 `data/lib/batch_fetcher.py` 的通用层。

### D3：dimensions 白名单的来源与 dossier 三维的显式排除

G1 量化五维来自实证：L1 漏斗四个模块（hard_gates/factor_scores/anti_trap/heat_filter）与 L2 `assemble_snapshot` 实际 `.get()` 的维度集合。dossier 三维（`main_business`/`peers`/`research`）的唯一消费方是 `council/research_dossier.py`（G2/L3 路径）。本 change 不删除 dossier 三维的 fetcher 注册（L3 仍需），只在 L1 调用点排除它们。

## Risks / Trade-offs

- **[调用点纪律依赖]** 只改 `screen_a_shares` 调用点意味着「L1 不采 dossier」的不变量依赖调用点显式传参，未来新增 L1 调用点忘记传参会重新触发全采。→ **缓解**：用 `test_screener_stats` 新增 dimensions 断言守护当前调用点；在 design 记录「未来 L1 调用点需自带 dimensions 断言」作为留给后续 child 的约束。
- **[测试 mock 而非真实采集]** dimensions 断言基于 `patch("screener.main.BatchFetcher")` 的 mock，不证明真实 `fetch_all` 在 dimensions 限制下不触网采 dossier。→ **缓解**：mock 断言能精确捕获「调用点传了什么」，这正是 boundary 的契约层证据；真实采集的成本/反爬验证属 G1-5 全市场 Gate，不在本 child。
- **[下游缩小用现有行为而非新测试]** L2/L3 下游 fetch 缩小用「已成立 + 等价证据说明」，不新增集成测试。→ **缓解**：L1 漏斗单调性是主证据且有测试；L2/L3 的 ticker 缩小逻辑属各自 child（G1-2 L2 contract / G3 dossier），本 child 不越界。
- **[cache 现状不改变]** 现有 cache 中个别 ticker 只有 `basic`/`kline` 两维（手工样本），本 change 不补采缺失维度。→ **缓解**：本 change 只约束 L1 主入口的采集维度集合，不保证历史 cache 完整性；全市场 warm-cache 完整性属 G1-5。
