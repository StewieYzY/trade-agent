## Why

G1 umbrella canonical spec「版本化筛选规则与运行身份」requirement（`personal-value-screening:14-23`）明确要求每次 G1 运行记录唯一 `run_id`、canonical ticker、输入数据快照标识和 `ScreeningProfile` 版本，且阈值变化 MUST 产生可区分的新版本、MUST NOT 覆盖旧版本证据。但代码层零实现（全仓 grep `run_id`/`profile_version`/`rule_version` 在源代码 0 命中）。实地证据：`watchlist/` 下同一天同一只票存在 `2026-07-13_600009.json`（549B 空壳）与 `2026-07-13_600009.SH.json`（3091B 真数据）两个文件——canonical ticker 在 5 处各自归一化（`market_router.parse_ticker` / `cli._normalize_ticker` / `CacheManager._normalize_ticker` / `council/features.py`+`debate.py` 的 `split(".")[0]` / `ScoutCache._path` 不归一），方向不一致导致 `monitor/aggregation.py:131-134` 的 `_read_l3_output` 只读到空壳 pattern、读不到真数据。G1-2 已闭合 L2 全量结果契约，但结果仍无法定位到「哪一次 run、哪一版规则、哪一份输入快照」——本 child 推进 umbrella 3.2，闭合运行身份契约。

## What Changes

- **新增统一 canonical ticker 函数作 SoT**：复用 `data/lib/market_router.py::parse_ticker` 的 `full` 字段（`600519.SH` 大写带后缀，含 BJ/HK/US，修 `cli._normalize_ticker` 把 `920xxx` 误判为 SH 的 bug），收敛现有 5 处归一化逻辑到单一 canonical 函数。**身份标识与 cache key 分离**：canonical ticker（带后缀）作身份/输出/聚合 key；L0 `CacheManager` 与 L2 `ScoutCache` 的 cache 目录仍用 `canonical.code`（纯数字），不迁 f1-deviation-fix D3 已统一的 L0 cache，不破坏既有 cache hit。
- **BREAKING**：`scout/quality.py::ScoutCache._path` 当前直接用原始 ticker 拼路径不归一，导致 `600519` 与 `600519.SH` 双目录并存。本 child 改为用 `canonical.code`（纯数字）建目录，**既有分裂的 L2 cache 目录需迁移合并**（与 f1-deviation-fix D3 的 L0 迁移同策略：空壳删、孤儿保、不丢真实数据）。
- **L1 主入口生成 run_id**：`screen_a_shares()` SHALL 生成唯一 `run_id`（`f(输入 ticker 集合 hash + 采集日 + profile_version)` 的稳定摘要），写入 L1 输出顶层；下游 `scout`/`monitor weekly` 从 L1 文件继承 run_id，不各自生成。纯 L2 单跑（无 L1 文件）SHALL fallback 生成。L3 是独立管线（AD-01，可手动输入 ticker），run_id 传播到 L1/L2 边界止，不强求 L3 继承。
- **ScreeningProfile version 显式可审计**：在 `screener/` 加 `PROFILE_VERSION` 代码常量字符串（零依赖，不引入配置文件层），规则常量（H1-H8 阈值/composite 权重/A1-A7 扣分/HF1-HF2/`G1_QUANT_DIMENSIONS`/`SCOUT_SYSTEM_PROMPT`）任一变化 MUST bump version。测试守护：对规则常量集合算 hash，hash 变了但 version 没 bump → 红测。
- **输入快照 identity**：L1 输入 ticker 集合 SHALL 生成稳定 hash（`input_ticker_set_hash`），L0 cache 的采集日/数据源维度以现有 `input_snapshot`（`scout/quality.py:100`，21 字段特征值）为载体补 `input_hash`/`profile_version`/`run_id` 绑定，使「规则未变但输入数据变了」与「输入未变但规则变了」可区分。
- **运行隔离**：同 ticker 不同 run 的结果 MUST NOT 互相覆盖——CLI `--output` 路径直接覆盖的现状改为带 run_id 的版本化命名或 manifest；`watchlist/{date}.json` 同日覆盖改为 run-scoped 命名；既有 24h L2 cache 的跨日隔离语义不变。
- **修 `monitor/aggregation.py:131-134` `_read_l3_output` pattern bug**：加 canonical ticker 双向回退（纯数字 ↔ 带后缀），让聚合能读到 `2026-07-13_600009.SH.json` 真数据而非只读空壳 `2026-07-13_600009.json`。既有 19 个 watchlist 文件保留只读作历史证据，不迁移不清空。
- 修 `council/debate.py` 内部命名口径不一致：`_debate_path`（`debate.py:236`）用 `ticker.split(".")[0]` 纯数字写 debate md，但 `_write_council_output`（`debate.py:890`）用 `result.ticker` 带后缀写 watchlist JSON——统一到 canonical ticker。

## Capabilities

### New Capabilities
- `run-identity`: 横切运行身份契约——canonical ticker 统一函数（SoT）、run_id 生成与 L1→L2 传播规则、ScreeningProfile version 显式审计与 bump 约束、输入快照 identity（ticker 集合 hash + 数据/规则绑定）、运行隔离（同 run 不覆盖、跨 run 可定位）。该 capability 集中承载所有身份 requirement，避免散落到各层 spec。

### Modified Capabilities
- `scout-agent`: MODIFIED「24h Cache with Input Snapshot」——ScoutCache 路径 SHALL 用 `canonical.code`（纯数字）而非原始 ticker 建目录，消除 `600519`/`600519.SH` 双目录分裂；cache entry SHALL 补 `run_id`/`profile_version`/`input_hash` 绑定。MODIFIED「CLI Integration」——scout 输出四字段 payload SHALL 继承 L1 的 `run_id` + `profile_version`，写入 run identity 元数据。
- `watchlist-aggregation`: MODIFIED「聚合 L1/L2/L3 三路产出」——`_read_l3_output` 的文件名 pattern SHALL 加 canonical ticker 双向回退（纯数字 ↔ 带后缀），修当前只匹配空壳、读不到真数据的 bug。

## Impact

**受影响代码**：
- 新增 `value-screener/run_identity/`（或 `data/lib/identity.py`）——canonical ticker 统一函数 + run_id 生成 + profile version 常量 + input hash。优先复用 `data/lib/market_router.py::parse_ticker`，不重写解析器。
- `value-screener/screener/main.py`——`screen_a_shares()` 返回结构加 `run_id`/`profile_version`/`input_ticker_set_hash`。
- `value-screener/cli.py`——`screen`/`scout` 输出加 run identity 元数据；`_normalize_ticker` 收敛到 canonical 函数（或删除改调统一函数）；输出文件命名带 run_id。
- `value-screener/scout/batch.py`/`scout/quality.py`——ScoutCache 路径用 `canonical.code`；cache entry 补 run_id/profile_version/input_hash；scout_batch 从 L1 candidates 继承 run_id（三元组返回契约不变，G1-2 闭合不重开）。
- `value-screener/monitor/weekly.py`/`monitor/aggregation.py`——weekly 从 L1 文件继承 run_id；`_read_l3_output` pattern 加双向回退。
- `value-screener/council/debate.py`——`_debate_path` 与 `_write_council_output` 命名口径统一到 canonical ticker（实现细节，design 定具体改法）。
- 既有 5 处归一化（`market_router`/`cli`/`CacheManager`/`features.py`/`debate.py`）收敛到 canonical 函数；`CacheManager._normalize_ticker`（f1-deviation-fix D3）保持作 cache key SoT 不动（身份与 cache key 分离）。

**依赖与约束**：
- AD-01（两条独立管线）：run_id 跨 L1→L2 传播，L3 独立不强求继承。
- AD-03（成本闸门）：身份元数据采集零额外 LLM 调用，不影响成本。
- f1-deviation-fix D3：L0 cache 纯数字 normalize 不动，canonical ticker 带后缀作身份层，两者分离。
- G1-2（L2 全量结果契约）：三元组返回契约不变，run_id/profile_version 作为 full_results 每条的元数据补充而非改返回签名。
- f3c（R1 串台）：`ScoutCache` 不 normalize ticker 是潜在串台风险点，G1-3 修 cache 路径 canonical 化顺带降低该风险，但不修 f3c 的 agent 间串台根因（独立工作项）。

**非破坏性保证**：
- 既有 19 个 watchlist JSON 保留只读，不迁移不清空（handoff 完成标准「旧证据仍可复核」）。
- L0 cache 目录不迁移（D3 已统一）。
- L2 ScoutCache 既有分裂目录按 D3 同策略安全迁移（空壳删/孤儿保/不丢真实数据）。
- G1-1/G1-2 既有测试不回归（canonical 函数对纯数字输入产出带后缀，对带后缀输入原样大写，行为可预测）。
