## ADDED Requirements

### Requirement: Canonical Ticker 单一 SoT
系统 SHALL 提供唯一的 canonical ticker 函数作为身份标识 SoT，输出大写带后缀形式（如 `600519.SH`、`920060.BJ`、`00700.HK`、`AAPL`），复用 `data/lib/market_router.py::parse_ticker` 的 `full` 字段。所有身份标识场景（L1/L2 输出、watchlist/CLI 输出、聚合 key、debate/watchlist 文件命名）SHALL 调用该函数，MUST NOT 各自 inline `ticker.split(".")[0]` 或自补后缀推断。

> 背景：实证发现 canonical ticker 在 5 处各自归一化——`market_router.parse_ticker`（带后缀，含 BJ/HK/US，最完整但只 fetcher 内部用）、`cli._normalize_ticker`（带后缀，6/9→SH 把 `920xxx` BJ 误判为 SH）、`CacheManager._normalize_ticker`（去后缀纯数字，f1-deviation-fix D3，方向相反）、`council/features.py`+`debate.py` 的 `ticker.split(".")[0]`（去后缀，重复 D3）、`ScoutCache._path`（不归一，导致 `600519`/`600519.SH` 双目录分裂）。本 requirement 收敛到单一 canonical 函数。身份标识与 cache key 分离：canonical ticker 带后缀作身份/输出/聚合 key；L0 `CacheManager` 与 L2 `ScoutCache` 的 cache 目录仍用 `canonical.code`（纯数字），D3 的 L0 cache normalize 不动。

#### Scenario: 纯数字输入产出带后缀 canonical
- **WHEN** canonical 函数收到纯 6 位数字 `600519`
- **THEN** SHALL 返回 `600519.SH`（大写带后缀），且 `920060` SHALL 返回 `920060.BJ`（BJ 不误判为 SH）

#### Scenario: 带后缀输入原样大写
- **WHEN** canonical 函数收到 `600519.sh`、`600519.SH` 或 `920060.bj`
- **THEN** SHALL 统一返回大写形式 `600519.SH` / `920060.BJ`，同证券不同大小写输入产出相同 canonical

#### Scenario: 非 A 股 ticker 兼容
- **WHEN** canonical 函数收到 HK `00700.HK` 或 US `AAPL`
- **THEN** SHALL 返回 `00700.HK` / `AAPL`，MUST NOT 抛错

#### Scenario: 非法 ticker 清晰报错
- **WHEN** canonical 函数收到非 6 位数字、非已知后缀格式、非 HK/US 形式的非法 ticker
- **THEN** SHALL 抛 `ValueError` 并附清晰原因，MUST NOT 静默返回原值或伪造后缀

#### Scenario: cache key 与身份标识分离
- **WHEN** L0 `CacheManager` 或 L2 `ScoutCache` 写缓存时收到 canonical ticker `600519.SH`
- **THEN** cache 目录 SHALL 用 `canonical.code`（纯数字 `600519`），MUST NOT 用带后缀形式建目录；canonical ticker `600519.SH` 仅作身份/输出/聚合 key，cache key SoT 仍是 `CacheManager._normalize_ticker`（D3 不动）

---

### Requirement: Run ID 生成与 L1→L2 传播
每次 G1 L1 运行 SHALL 生成唯一 `run_id`，下游 L2 scout 与 L4 monitor weekly SHALL 从 L1 输出继承该 `run_id`，MUST NOT 各自独立生成。`run_id` SHALL 是 `f(输入 ticker 集合 hash + 采集日 + profile_version)` 的稳定摘要，使得「相同输入 + 相同日 + 相同规则」产出相同 run_id、「输入变了」或「规则变了」产出可区分的 run_id。纯 L2 单跑（无 L1 文件）SHALL fallback 生成 run_id 并标注 `run_id_source: "scout_fallback"`。L3 是独立管线（AD-01，可手动输入 ticker），run_id 传播到 L1/L2 边界止，不强求 L3 继承。

#### Scenario: L1 生成 run_id 并写入输出
- **WHEN** `screen_a_shares(tickers)` 被调用
- **THEN** 返回结构顶层 SHALL 含 `run_id`（非空字符串）、`run_date`、`profile_version`、`input_ticker_set_hash` 四字段

#### Scenario: 相同输入两次运行 run_id 一致
- **WHEN** 同一 ticker 集合、同一采集日、同一 profile_version 调用 `screen_a_shares` 两次
- **THEN** 两次返回的 `run_id` SHALL 相同（稳定摘要，非随机 uuid）

#### Scenario: 输入变化 run_id 可区分
- **WHEN** ticker 集合变化（增/删/改任一 code）但采集日与 profile_version 不变
- **THEN** `run_id` SHALL 与原 run_id 不同，且 `input_ticker_set_hash` SHALL 不同（定位到「输入数据变了」）

#### Scenario: 规则变化 run_id 可区分
- **WHEN** profile_version bump（规则常量变化）但 ticker 集合与采集日不变
- **THEN** `run_id` SHALL 与原 run_id 不同（定位到「输入未变但规则变了」），且 `profile_version` 字段不同

#### Scenario: L2 从 L1 继承 run_id
- **WHEN** `scout_batch` 处理来自 L1 输出的 candidates（candidates 携带或 L1 文件含 `run_id`）
- **THEN** L2 四字段 payload 与 ScoutCache entry SHALL 继承 L1 的 `run_id`，MUST NOT 生成新 run_id

#### Scenario: 纯 L2 单跑 fallback 生成
- **WHEN** `scout_batch` 收到的 candidates 无 `run_id`（非来自 L1，手动构造）
- **THEN** L2 SHALL fallback 生成 `run_id` 并标注 `run_id_source: "scout_fallback"`，MUST NOT 因缺 run_id 报错中断

#### Scenario: L3 独立不强求继承
- **WHEN** L3 `council --ticker` 单股深研（手动输入 ticker，非来自 L1/L2 watchlist）
- **THEN** L3 SHALL NOT 因缺 run_id 报错；L3 产出文件可不带 run_id（AD-01 独立管线边界）

---

### Requirement: ScreeningProfile Version 显式审计与 bump 约束
系统 SHALL 在 `screener/` 暴露 `PROFILE_VERSION` 代码常量字符串（如 `"g1-2026-07-21"`），作规则版本的显式可审计标识。规则常量（H1-H8 hard gate 阈值、composite 权重、A1-A7 anti-trap 扣分、HF1-HF2 heat filter、`G1_QUANT_DIMENSIONS` 采集白名单、`SCOUT_SYSTEM_PROMPT`）任一发生变化时，`PROFILE_VERSION` MUST bump 为新值。系统 MUST NOT 从代码时间戳或 git commit 推断版本——version 是运行时可读的显式字段。

> 背景：实证发现规则全是代码内常量，无 `profile_version`/`rule_version` 字段，无配置文件承载规则，唯一 `__version__` 在 `council/__init__.py` 是模块版本不随规则 bump，只能从 git commit 推断。本 requirement 用代码常量（零依赖，不引入配置文件层）+ 测试守护。

#### Scenario: PROFILE_VERSION 为模块级常量
- **WHEN** 任意调用方需要引用当前规则版本
- **THEN** `screener/` SHALL 暴露模块级常量 `PROFILE_VERSION`（非内联字面量），`screen_a_shares` 返回结构与 L2 payload SHALL 携带该常量值

#### Scenario: 规则变化必须 bump version
- **WHEN** H1-H8 阈值、composite 权重、A1-A7 扣分、HF1-HF2、`G1_QUANT_DIMENSIONS`、`SCOUT_SYSTEM_PROMPT` 任一规则常量发生变化
- **THEN** `PROFILE_VERSION` SHALL bump 为新值，MUST NOT 保持旧值

#### Scenario: version bump 守护测试
- **WHEN** 测试对规则常量集合计算 hash，且开发者改了规则常量但未 bump `PROFILE_VERSION`
- **THEN** 守护测试 SHALL 失败（红测），提示「规则变化但 PROFILE_VERSION 未 bump」

#### Scenario: 旧版本证据不被覆盖
- **WHEN** profile_version bump 后运行新一次 G1
- **THEN** 旧 profile_version 的运行产物（watchlist/cache/输出文件）SHALL 仍可读取定位，MUST NOT 被新 version 运行覆盖（运行隔离 requirement 配合）

---

### Requirement: 输入快照 Identity（ticker 集合 hash + 数据/规则绑定）
系统 SHALL 为 L1 输入 ticker 集合生成稳定 `input_ticker_set_hash`（对 canonical ticker 集合排序后哈希），并 SHALL 将 `run_id`/`profile_version`/`input_ticker_set_hash` 绑定到 L2 `ScoutCache` 的 `input_snapshot`，使「规则未变但输入数据变了」与「输入未变但规则变了」可区分可审计。现有 `scout/quality.py::input_snapshot`（21 字段特征值）SHALL 保留作诊断用途，本 requirement 在其上补 identity 绑定字段，MUST NOT 替换或破坏现有 21 字段。

#### Scenario: L1 输入 ticker 集合有 hash
- **WHEN** `screen_a_shares(tickers)` 被调用
- **THEN** 返回结构 SHALL 含 `input_ticker_set_hash`，且该 hash 是对 canonical ticker 集合排序后的稳定哈希（集合相同则 hash 相同，顺序不同 hash 相同）

#### Scenario: L2 cache entry 绑定 identity
- **WHEN** `ScoutCache.set` 写入某 ticker 的 cache entry
- **THEN** cache entry SHALL 含 `run_id`、`profile_version`、`input_ticker_set_hash`（继承自 L1），与既有 `input_snapshot`（21 字段特征值）并存

#### Scenario: 数据变 vs 规则变可区分
- **WHEN** 同一 canonical ticker 在两次 run 中 `input_snapshot` 特征值不同
- **THEN** 系统 SHALL 能通过 `input_ticker_set_hash`（集合是否变）与 `profile_version`（规则是否变）区分「输入数据变了」与「规则变了」，MUST NOT 仅靠特征值差异猜测

---

### Requirement: 运行隔离（同 run 不覆盖、跨 run 可定位）
同 ticker 不同 run 的运行产物 SHALL 互相隔离，MUST NOT 因同一 ticker 或同一 output path 互相覆盖或混淆。跨 run 的历史产物 SHALL 仍可定位读取。既有 24h L2 cache 的跨日隔离语义不变。CLI `--output` 与 `watchlist/{date}.json` 的同日直接覆盖语义 SHALL 改为 run-scoped 命名或 manifest，使同日多次运行不互相覆盖。

> 背景：实证发现 CLI `--output` 直接 `write_text` 覆盖（cli.py:253/327），`watchlist/{date}.json` 同日覆盖（aggregation.py:258），L0 `data/cache/{ticker}/{dim}.json` 同路径 `os.replace` 覆盖（manager.py:101），L2 `data/cache/{ticker}/{date}/l2_scout.json` 跨日隔离但 ticker 不归一导致分裂。同一天多次运行 `run_date` 相同无法区分。

#### Scenario: 同日多次运行不互相覆盖
- **WHEN** 同一天对同一 ticker 集合多次运行 `screen` 或 `scout`
- **THEN** 每次 run 的输出 SHALL 带不同 `run_id`，产物文件 SHALL 不互相覆盖（带 run_id 命名或 manifest 索引），旧 run 产物仍可读取

#### Scenario: 跨 run 历史可定位
- **WHEN** 用户查看某 ticker 在历史某次 run 的结果
- **THEN** 系统 SHALL 能通过 `run_id` + canonical ticker 定位该次 run 的 L1/L2/watchlist 产物，MUST NOT 因后续 run 覆盖而丢失

#### Scenario: 同 ticker 不同 run 的 cache 不混淆
- **WHEN** 同一 canonical ticker 在不同 run（不同 run_id 或不同采集日）产生 L2 cache
- **THEN** cache entry SHALL 通过 `run_id`/采集日区分，MUST NOT 互相覆盖混淆；既有跨日 `{date}` 子目录隔离语义保留

#### Scenario: 旧 watchlist 文件保留只读
- **WHEN** canonical ticker 命名统一后，既有 watchlist 目录存在历史命名文件（含空壳与真数据分裂）
- **THEN** 既有文件 SHALL 保留只读作历史证据，MUST NOT 迁移或清空；新 run 用统一 canonical 命名
