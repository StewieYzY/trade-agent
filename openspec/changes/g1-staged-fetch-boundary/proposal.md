## Why

G1 全市场 L1 路径（`screener/main.py::screen_a_shares`）调用 `BatchFetcher.fetch_all(tickers)` 时不传 `dimensions`，而 `BatchFetcher.fetch_all` 在 `dimensions=None` 时默认采集全 8 维——包括属于 G2/L3 深研的 dossier 三维（`main_business`/`peers`/`research`）。实证表明这三个维度在 L1 漏斗（hard_gates/factor_scores/anti_trap/heat_filter）和 L2 `assemble_snapshot` 中**从未被 `.get()` 读取**，纯属浪费采集与反爬风险。该潜伏缺口当前未被任何测试守护，且因全市场从未真正跑过（CLAUDE.md 已知差距 P1）而未暴露。本 change 建立 G1/G2 fetcher 边界，证明全市场 L1 路径不采集 dossier 维度，并用调用计数或等价证据证明 ticker 集合随漏斗逐层缩小——推进 G1 umbrella task 2.1、2.2。

## What Changes

- 在 L1 主入口 `screen_a_shares()` 调用 `fetch_all()` 时显式传入 G1 量化维度白名单（`basic`/`financials`/`kline`/`valuation`/`risk`），不再依赖 `dimensions=None` 的全采兜底。
- 将 G1 量化维度白名单与 dossier 维度的边界定义为一个可被测试断言的显式集合，使「L1 不采 dossier 维度」成为有测试守护的不变量，而非调用点纪律。
- 用 L1 漏斗各阶段输出计数（`after_hard_gates`/`after_factors`/`after_heat_filter`）与下游 L2/L3 实际 fetch/调用 ticker 集合的等价证据，证明 ticker 集合随漏斗逐层缩小（非 staged fetch 重构，见 design.md 决策）。
- 新增行为测试：断言 `screen_a_shares` 传给 `BatchFetcher.fetch_all` 的 `dimensions` 参数**不含** dossier 三维，并断言单股失败隔离与现有 L1 行为不回归。

## Capabilities

### New Capabilities

- `staged-fetch-boundary`: 定义 G1 量化筛选（L1/L2）与 G2 深研（L3）的数据采集维度边界。L1 全市场路径 SHALL 只采集量化维度白名单，MUST NOT 默认采集 dossier 维度；并定义 ticker 集合随漏斗缩小的可验证证据要求。

### Modified Capabilities

- `quantitative-screener`: `screen_a_shares()` 的数据采集行为从「`fetch_all(tickers)` 不传 dimensions、默认采全 8 维」改为「显式传入 G1 量化维度白名单，排除 dossier 三维」。新增 fetch 维度边界的 requirement 与 scenario。

## Impact

**受影响代码**：
- `value-screener/screener/main.py` — `screen_a_shares()` 调用 `fetch_all()` 传显式 dimensions
- `value-screener/tests/test_screener_stats.py`（或新增 fetch boundary 测试文件）— 断言传入 dimensions 不含 dossier 三维，且漏斗计数单调缩小
- `value-screener/data/lib/batch_fetcher.py` — `fetch_all` 的 `dimensions=None` 兜底契约**不改**（见 design.md 决策 D2：只改调用点，不改 fetch_all 契约），但本 change 的测试通过现有 `BatchFetcher` mock 验证调用点行为

**不受影响**：
- `value-screener/scout/batch.py` / `scout/input_assembly.py` — L2 仍 per-ticker 读已采 cache 的 5 维，L1 维度白名单化后 L2 行为不变（cache 仍有 5 维）
- `value-screener/council/research_dossier.py` — L3 dossier fetcher 是独立路径，绕开 BatchFetcher，显式调 dossier 三维；不受 L1 dimensions 改动影响
- `value-screener/data/lib/batch_fetcher.py` 的 `_DIM_FETCHERS` 注册表与 `dimensions=None` 兜底逻辑
- 不改 L2 输出契约、canonical identity、ScreeningProfile 或全市场性能

**AD 引用**：
- **AD-10**（串行 Gate）：本 change 推进 G1 分层采集边界 Gate（umbrella 2.1、2.2），是 G1 通过的前置条件
- **AD-03**（成本闸门）：L1 不采 dossier 三维直接降低全市场路径的采集量与反爬风险，支撑「不对全市场调用重度 LLM/重度采集」

**风险**：
- `fetch_all` 契约不改意味着「L1 不采 dossier」的不变量依赖调用点显式传参；若未来新增的 L1 调用点忘记传 dimensions 会重新触发全采。本 change 用测试守护 `screen_a_shares` 这一个调用点，不覆盖未来调用点（符合 child scope）。
- 现有 cache 中个别 ticker 只有 `basic`/`kline` 两维（手工样本），本 change 不改变 cache 现状，仅约束 L1 主入口的采集维度集合。
