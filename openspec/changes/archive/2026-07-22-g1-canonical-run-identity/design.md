## Context

G1 umbrella canonical spec「版本化筛选规则与运行身份」requirement 要求每次 G1 运行记录唯一 `run_id`/canonical ticker/输入快照标识/`ScreeningProfile` 版本，但代码层零实现（全仓 grep `run_id`/`profile_version` 源代码 0 命中）。Explore 调研（`value-screener/` 全仓实读）锁定 5 维度缺口：

1. **canonical ticker 5 处归一化不一致**——`market_router.parse_ticker`（带后缀，含 BJ/HK/US，最完整但只 fetcher 内部用）/`cli._normalize_ticker`（带后缀，6/9→SH 把 `920xxx` BJ 误判 SH）/`CacheManager._normalize_ticker`（去后缀纯数字，f1-deviation-fix D3）/`council/features.py`+`debate.py` 的 `split(".")[0]`（重复 D3）/`ScoutCache._path`（不归一，致 `600519`/`600519.SH` 双目录分裂）。
2. **无 run_id**——最接近的是 `run_date`（ISO 日期，同日多次运行同值无法区分）。
3. **无 ScreeningProfile version**——规则全是代码常量，唯一 `__version__` 是模块版本不随规则 bump。
4. **input_snapshot 非带版本 identity**——`scout/quality.py:100` 是 21 字段特征值副本，无 hash/provenance/采集时间/cache 版本，不可重建。
5. **运行隔离靠 date 不靠 run_id**——CLI `--output` 直接覆盖、`watchlist/{date}.json` 同日覆盖、L0 cache 同路径 `os.replace` 覆盖。

**最硬下游证据**（实地 `ls` 确认）：`watchlist/` 下同一天同一只票并存 `2026-07-13_600009.json`（549B 空壳）与 `2026-07-13_600009.SH.json`（3091B 真数据）——根因是 `council/debate.py` 内部 `_debate_path`（debate.py:236）用纯数字写 debate md、`_write_council_output`（debate.py:890）用带后缀写 watchlist JSON，命名口径不一致；叠加 `monitor/aggregation.py:131-134` `_read_l3_output` 的 pattern 不含纯数字↔带后缀双向回退，聚合永远只读到空壳。

**约束**：AD-01（两条独立管线，run_id 跨 L1→L2 传播，L3 独立不强求继承）/ AD-03（成本闸门，identity 采集零额外 LLM 调用）/ f1-deviation-fix D3（L0 cache 纯数字 normalize 不动，canonical 与 cache key 分离）/ G1-2（L2 三元组返回契约不重开，run identity 作 full_results 元数据补充）/ f3c（ScoutCache 不归一是潜在串台风险点，G1-3 修 cache 路径 canonical 化顺带降低，但不修 f3c 的 agent 间串台根因）。

## Goals / Non-Goals

**Goals:**
- 提供唯一 canonical ticker 函数作身份标识 SoT，收敛 5 处归一化，修 `920xxx` BJ 误判 SH bug 与 `ScoutCache` 双目录分裂。
- L1 生成唯一 `run_id`（稳定摘要），L2/weekly 继承，使「输入变了」与「规则变了」可区分。
- `PROFILE_VERSION` 显式可审计代码常量 + 测试守护（规则常量 hash 变了但 version 没 bump → 红测）。
- 输入 ticker 集合 hash + cache entry 绑定 run identity，使 input snapshot 可重建性可审计。
- 运行隔离：同 ticker 不同 run 不覆盖、跨 run 可定位；既有 24h L2 cache 跨日隔离语义不变。
- 修 `_read_l3_output` pattern bug + 统一 council 命名口径，让聚合读到真数据。
- 既有 19 watchlist 文件保留只读，不迁移不清空。

**Non-Goals:**
- 不重开 G1-1 分层采集边界（`G1_QUANT_DIMENSIONS` 白名单不动，只给它加 profile version 绑定）。
- 不重设计 G1-2 的 `scout_batch` 三元组 / `full_results` / `failure_summary`（run identity 作元数据补充，不改返回签名）。
- 不做 300+ 多行业样本、全市场性能/成本运行、Top 20 风格校准（属 G1-4/G1-5/G1-6）。
- 不实现 G2 Council、G3 holding runtime、前端或部署。
- 不引入配置文件层承载规则（用代码常量 + 测试守护，零依赖）。
- 不迁 L0 cache 目录（D3 已统一），不迁既有 watchlist 历史文件。
- 不修 f3c 的 R1 agent 间串台根因（独立工作项）。
- 不强求 L3 继承 run_id（AD-01 独立管线边界）。

## Decisions

### D1：canonical ticker 复用 `market_router.parse_ticker().full`，新增薄封装 `canonical_ticker()` 作 SoT

**决策**：在 `value-screener/data/lib/`（或新建 `run_identity.py`）新增 `canonical_ticker(raw) -> str` 薄封装，内部调 `parse_ticker(raw).full`（已输出大写带后缀，含 BJ/HK/US）。5 处旧归一化收敛到它：
- `cli._normalize_ticker` → 改调 `canonical_ticker`（删除自补后缀逻辑，顺带修 `920xxx` BJ 误判）
- `council/features.py:24` + `debate.py:236` 的 `split(".")[0]` → cache key 场景改调 `CacheManager._normalize_ticker`（D3 已是 SoT），身份/输出场景改调 `canonical_ticker`
- `ScoutCache._path` → 改用 `canonical_ticker(raw).split(".")[0]`（即 `canonical.code`，纯数字）建目录

**身份与 cache key 分离**：`canonical_ticker` 返回带后缀（`600519.SH`）作身份/输出/聚合 key；`canonical.code`（`parse_ticker().code`，纯数字）作 cache key，与 `CacheManager._normalize_ticker`（D3）行为一致。

**替代方案**：(a) canonical 选纯数字——否决，丢交易所信息、920xxx BJ 与 SH 冲突、HK/US 无法 6 位表达。(b) 重写新解析器——否决，`parse_ticker` 已最完整（含 BJ 前缀优先判定），重写是浪费且引入新 bug 风险。复用 + 薄封装最优。

**替代方案（cache key）**：(c) cache key 也改带后缀——否决，破坏 D3 已统一的 L0 cache（需全量迁目录，f1-deviation-fix 已闭合的工作量）。分离方案让 cache key SoT 不动。

### D2：`run_id` 每次执行唯一（uuid4），与 `input_ticker_set_hash`/`profile_version` 分离；L1 生成一次 L2/weekly 继承

**决策**（apply 阶段纠正：原 D2 用「稳定摘要 sha256(input_hash|run_date|profile_version)」与 D6「同日不同 run 不覆盖」矛盾——相同输入同日两次跑会产出相同 run_id，无法区分两次 run，违背「每次运行唯一」语义）：

- **`run_id`**：每次执行**唯一**，用标准库 `uuid.uuid4()`（随机 128 位），非稳定 hash。L1 生成一次，L2/weekly 继承同一值，MUST NOT 重新生成。纯 L2 单跑（无 L1）fallback 生成 + 标 `run_id_source: "scout_fallback"`。L3 独立管线不强求继承（AD-01）。
- **`input_ticker_set_hash`**：**继续保持确定性**（`sha256(sorted(canonical_ticker_set))[:12]`），用于识别输入集合是否变化——这是独立于 run_id 的概念：run_id 定位「哪一次 run」，input_hash 描述「输入集合指纹」。两者分离：同输入两次 run → run_id 不同但 input_hash 相同。
- **`profile_version`**：继续显式版本化（D3 代码常量）。
- 「输入变了」与「规则变了」的可区分性由 `input_ticker_set_hash` + `profile_version` 两个字段提供，**不再由 run_id 承担**。run_id 只负责「定位到 run」+ D6「同日不覆盖」。

**生成点**：`screen_a_shares()` 唯一生成 `run_id = str(uuid.uuid4())`，写入返回结构顶层 `run_id`/`run_date`/`profile_version`/`input_ticker_set_hash` 四字段。

**传播**：`scout_batch` 从 L1 顶层读 `run_id` 继承，写进 full_results 每条 + ScoutCache entry + 四字段 payload。`monitor weekly` 从 L1 文件读 run_id 继承。纯 L2 单跑 fallback 生成 uuid4 + 标 `run_id_source`。

**替代方案**：(a) 稳定 hash run_id（原 D2）——否决，与 D6「同日不同 run 不覆盖」矛盾，无法区分同日两次 run。(b) screen/scout 各自生成——否决，两次跑两个 run_id，无法把 L2 结果定位到 L1 run。(c) run_id = timestamp——可用但 uuid4 更标准、碰撞概率为零。uuid4 + input_hash/profile_version 分离最优：run_id 唯一定位 run，input_hash/profile_version 描述输入/规则状态。

### D3：`PROFILE_VERSION` 代码常量 + 规则源码 hash 守护测试

**决策**：`screener/profile.py` 定义 `PROFILE_VERSION = "g1-2026-07-21"`。守护测试：`compute_rules_hash()` 对**规则源码文件内容**算 sha256（非序列化常量——实读发现 H1-H8 阈值/composite 权重/A1-A7 扣分/HF1-HF2 阈值大多是函数体内联字面量，非模块级常量，抽常量会违反「screener/hard_gates/factor_scores/anti_trap/heat_filter 零改动」约束）。hash 的规则文件列表硬编码在 `profile.py`：`hard_gates.py`/`factor_scores.py`/`anti_trap.py`/`heat_filter.py`/`main.py`（`G1_QUANT_DIMENSIONS` 所在）/`scout/prompt.py`（`SCOUT_SYSTEM_PROMPT`）。

落盘 `screener/.rules_hash` 文件存 `{hash, profile_version}` 两条记录。守护测试逻辑：
- 计算当前 `compute_rules_hash()` 与当前 `PROFILE_VERSION`
- 与落盘 `{hash, profile_version}` 比对：
  - 当前 hash == 落盘 hash → 规则未变，通过（不管 version）
  - 当前 hash != 落盘 hash 且当前 version != 落盘 version → 规则变了且 version 已 bump，通过
  - 当前 hash != 落盘 hash 但当前 version == 落盘 version → **规则变了但 version 没 bump → 红测**
- 测试用 monkeypatch `compute_rules_hash` 返回值模拟「规则变了」场景，不改动真源码文件（避免 fragile）。

**替代方案**：(a) 配置文件（YAML/JSON）承载规则 + version——否决，改动大、引入配置加载层、违反「不主动引入新依赖」，且 L1 阈值散在 4 模块抽取工作量超 G1-3「只推进 3.2」边界。(b) 从 git commit hash 推断 version——否决，spec 明确「MUST NOT 从代码时间戳或 git commit 推断」，运行时不可读。(c) 只加 `PROFILE_VERSION` 常量无守护——否决，开发者会忘 bump，version 形同虚设。(d) 抽规则常量为模块级再序列化——否决，违反「screener 规则模块零改动」review 约束（task 13.1），且抽取 4 模块内联字面量工作量与回归风险不成比例。源码文件 hash + 落盘比对最优（零规则代码改动 + 强制 bump + 测试可模拟）。

**trade-off**：源码文本变化（加注释、改格式）也触发 hash 变 → 保守误报，要求开发者确认是否 bump version。这正是「规则源码任何改动都该触发 version review」的保守语义，可接受。`.rules_hash` 进 git（团队共享 version 守护基准，类似 lock 文件，非临时生成物）。

### D4：`ScoutCache` 路径改 `canonical.code` + 既有分裂目录 D3 同策略安全迁移

**决策**：`ScoutCache._path(ticker, date_str)` 改为 `base / canonical_ticker(ticker).split(".")[0] / date_str / "l2_scout.json"`（即 `canonical.code` 纯数字），与 `CacheManager._normalize_ticker`（D3）对齐。cache entry 补 `run_id`/`profile_version`/`input_ticker_set_hash` 字段（继承自 L1）。

**迁移**：既有 `data/cache/{ticker.SH}/{date}/l2_scout.json` 分裂目录按 f1-deviation-fix D3 同策略：
- 带后缀目录为空壳（无 `l2_scout.json` 或文件无真实 verdict）→ 删
- 带后缀目录有真实数据，纯数字目录也存在且有数据 → 以纯数字为真值，带后缀数据作参考归档后删
- 带后缀目录有真实数据，无纯数字目录（孤儿）→ 移到纯数字目录再删
- **不丢真实数据**

迁移脚本放 `scripts/migrate_split_l2_cache.py`，幂等可重跑。

**替代方案**：(a) 不迁，新旧并存——否决，分裂目录是 f3c 串台风险点，且新代码用 canonical.code 后旧分裂目录成孤儿。(b) 直接 `rm -rf` 带后缀目录——否决，可能丢真实数据（违背 D3 既有安全策略）。

**apply 阶段补充（clear + get identity 校验）**：独立 review 发现两个遗漏点，均补修：(1) `clear(ticker=...)` 原用 `self.base / ticker` 拼目录（未过 canonical_code），传 `600519.SH` 找不到 canonical 化后的 `600519/` 目录 → 改用 `canonical_code(ticker)` 与 `_path` 对齐。(2) `get()` 原只校验 TTL，不校验缓存 entry 的 `run_id`/`profile_version` 是否匹配当前 run → 加可选 `run_id`/`profile_version` 参数，缓存含该字段但不匹配 → 返回 None（视为 miss，不混用跨 run/跨规则缓存），满足 `scout-agent` delta 的 `Same ticker different run's cache does not mix up`；不传参数维持原 TTL-only 行为（向后兼容）。`scout_batch` 调 `cache.get` 时传当前 run 的 `run_id`/`profile_version`（闭包内已解析，无需改 process_one 签名）。

### D5：A+ 兼容层——council 命名口径统一 canonical + 多处读取双向回退

**决策**（apply 阶段纠正：原 D5 漏了 `_check_cache`/force-unlink 的回退，且对 `monitor/diff.py::history` 的描述错误——`history()` 实读读聚合 `watchlist/{date}.json` 不读 debate md，故 debate md 双向回退与 history 无关）：

**A+ 边界（新写入统一 canonical，旧产物保留只读 + 读取双向回退）**：
- `run_debate()` 入口先 canonicalize ticker（`canonical_ticker(ticker)`），后续全用 canonical 形式。
- `_debate_path()` 新写入统一用 `debate/{canonical_ticker}/{date}.md`（带后缀，如 `debate/600519.SH/2026-07-21.md`）。
- `_check_cache()` 先读 canonical 路径，再回退旧的纯数字路径 `debate/{canonical_code}/{date}.md`（兼容既有 `debate/600519/` 历史 cache，升级后仍可命中）。
- `force=True` 同时清理 canonical 路径**与**旧纯数字路径的当日文件，避免旧内容残留（`test_force_skips_cache` 断言「旧记录残留」守护）。
- `_write_council_output()` 只写 canonical ticker 文件（`watchlist/{date}_{canonical}.json`，带后缀），无论 `result.ticker` 是纯数字还是带后缀都 canonical 化统一。
- 旧 `debate/{纯数字}/` 目录和旧 watchlist 文件保留只读，不迁移、不删除。
- `_read_l3_output()` canonical 优先、纯数字回退，并优先选择内容完整的文件（修空壳/真数据分裂）。

**D5 纠正：`monitor/diff.py::history` 不读 debate md**。实读 `diff.py:226-275`，`history()` 遍历 `watchlist/*.json` 跳过 per-ticker 文件（`f.stem.count("_") > 0` 跳过），只读聚合 `{date}.json`。故 debate md 双向回退**与 history 无关**。task 10.2 重新对照真实调用链：`history` 读聚合 watchlist，run-scoped 命名（`{date}_{run_id[:8]}.json`，D6）会让 `f.stem.count("_")` 误跳过——需同步调整 history 的 per-ticker 跳过逻辑或 glob 模式（见 D6 + task 10.2）。

**测试覆盖（A+ 补充）**：
- 纯数字/带后缀调用 `run_debate` 最终写入同一 canonical 路径（`debate/600519.SH/` + `watchlist/{date}_600519.SH.json`）。
- 旧 cache（`debate/600519/` 旧目录）可命中（`_check_cache` 回退）。
- `force=True` 不残留旧内容（canonical + 旧纯数字路径都清）。
- canonical 空壳与旧真数据并存时 `_read_l3_output` 读真数据。
- 同日两次运行 run_id 不同（D2 uuid4）且旧产物不被覆盖（D6 run-scoped）。

**替代方案**：(a) 只修 `_read_l3_output` 不统一 council 命名——否决（方向 C），根因在 council 命名口径不一致，只修聚合层治标，新 run 还会产生分裂。(b) canonical 选纯数字统一——否决（方向 B），与 D1 决策（带后缀作身份 SoT）矛盾，丢 `.SH/.SZ/.BJ` 身份信息。(c) 迁移既有 debate md/watchlist 目录——否决，历史证据保留，加双向回退即可读。

### D6：运行隔离——run_id 唯一（D2 uuid4）+ watchlist run-scoped 命名 + history 跳过逻辑同步

**决策**：
- **apply 阶段纠正（A 方案）**：CLI `screen`/`scout` 的 `--output` 现实现 run-scoped 分流。写入前比对目标路径已有产物的 `run_id`：不存在/无可读 run_id → 原路径写（首次运行）；run_id 相同 → 原路径覆盖（同 run 重跑，合理）；run_id 不同 → 改写 `{stem}.{run_id[:8]}.json` 分流文件，旧 run 产物保留不被覆盖。输出 payload 顶层仍带 `run_id`（D2 uuid4，每次唯一）；若调用方未指定 `--output`（stdout），行为不变。**原 D6「不强制改 `--output` 文件名」被否决**——实证发现 scout-agent delta 的 `#### Scenario: Same-day multiple runs do not overwrite` 明确要求 CLI 输出 run-scoped，不实现即 spec 与实现违反；A 方案实现成本极低（一个 helper + 两处调用点），且与 watchlist `{date}_{run_id[:8]}.json` 命名一致。
- `watchlist/{date}.json` 同日覆盖 → 改为 `watchlist/{date}_{run_id[:8]}.json`（run-scoped）。同日多次运行 run_id 不同（D2 uuid4）→ 文件名不同 → **旧 run 产物不被覆盖**。聚合时读最新 run_id 的文件。既有 `{date}.json` 历史文件保留。
- L0 cache 仍同路径覆盖（D3 既有行为，TTL 区分新旧），但 cache entry 带 `run_id` 使跨 run 可溯源（cache 命中时返回的 entry 含 run_id，消费方可判断是否同 run）。
- **`monitor/diff.py::history` per-ticker 跳过逻辑同步**：`history()` 现用 `f.stem.count("_") > 0` 跳过 per-ticker 文件（diff.py:259）。run-scoped 命名 `{date}_{run_id[:8]}.json` 的 stem 含 `_` 会被误跳过 → 需同步调整：history 的 glob/跳过逻辑要区分「聚合 run-scoped 文件」（应读）与「per-ticker L3 文件 `{date}_{ticker}.json`」（应跳）。区分依据：per-ticker 文件名第二段是 ticker（含字母/`.`），run-scoped 第二段是 run_id 前缀（hex）。task 10.2 落实。

**替代方案**：(a)~~CLI `--output` 强制改 run-scoped 命名——原否决理由「破坏既有脚本固定路径约定」~~（apply 阶段推翻：A 方案仅在 run_id 不同时才分流，同 run 重跑仍走原路径，既有脚本第一次跑不受影响；spec 要求必须做）。(b) L0 cache 也改 run-scoped 目录——否决，L0 是数据层 resume 缓存（D3 已闭合），run-scoped 会破坏 cache hit 跨 run 复用，违背 AD-03 成本闸门。payload 带 run_id（D2 uuid4）+ watchlist run-scoped + CLI `--output` run-scoped 分流已够定位 + 同日不覆盖。

### D7：identity 模块位置——`value-screener/data/lib/identity.py`

**决策**：canonical ticker / run_id 生成 / profile version / input hash 统一放 `data/lib/identity.py`（数据层 lib，与 `market_router.py`/`fin_models.py` 同层）。理由：identity 是数据层关注（ticker 解析、cache key、输入集合），放数据层 lib 最自然；`screener/` import 它生成 run_id，`scout/` import 它继承 run_id，`cli.py` import 它做 canonical 化。

`PROFILE_VERSION` 放 `screener/profile.py`（规则属 L1 screener 关注），`identity.py` import 它算 run_id。

**替代方案**：(a) 散放到各模块（screener 放 run_id、scout 放 canonical、cli 放 version）——否决，违背「单一 SoT」。(b) 新建顶层 `run_identity/` 包——否决，over-engineering，identity 是数据层横切，不需要独立包。

## Risks / Trade-offs

- **[run_id uuid4 碰撞风险]** D2 改 uuid4 后碰撞概率为零（128 位随机），无需缓解。`watchlist/{date}_{run_id[:8]}.json` 用前 8 hex 字符，碰撞概率 1/16^8 ≈ 1/4 亿，可接受；run_id 全 36 字符（uuid4 标准格式）进 payload 顶层作精确 key。
- **[规则常量 hash 守护的误报]** 开发者改了规则常量但 hash 落盘值未刷新 → 缓解：守护测试错误信息明确提示刷新命令；CI 跑该测试。反向风险：开发者 bump 了 version 但没改规则 → 测试不报（hash 未变），这是可接受的（version bump 无害）。
- **[ScoutCache 迁移丢数据]** 迁移脚本误删真实数据 → 缓解：严格按 D3 三分支策略（空壳删/孤儿移/有真值以纯数字为真值），迁移脚本 dry-run 模式 + 单测覆盖三种分支；迁移前 `data/cache/` 已在 git 跟踪可回滚。
- **[debate md 路径变更破坏既有 cache 命中]** `_debate_path` 改 canonical 带 `.SH` 后缀，既有 `debate/600519/`（纯数字旧目录）的 cache 会 miss → 缓解：`_check_cache` 加 canonical 双向回退（先 canonical 路径，回退纯数字旧路径），既有目录保留不迁、仍可命中（D5 A+ 兼容层）。`force=True` 同时清 canonical + 旧纯数字路径避免残留。注：`monitor/diff.py::history` 不读 debate md（读聚合 watchlist），故此风险与 history 无关。
- **[history 的 per-ticker 跳过逻辑误跳 run-scoped 文件]** run-scoped 命名 `{date}_{run_id[:8]}.json` 含 `_`，会被 `history` 现有 `f.stem.count("_") > 0` 跳过 → 缓解：task 10.2 调整 history 区分逻辑（per-ticker 第二段是 ticker 含字母/`.`，run-scoped 第二段是 hex run_id 前缀），D5/D6 已标注。
- **[L1 candidate ticker 仍可能是纯数字]** `screen_a_shares()` 用原始输入构造 candidate，CLI 全市场输入通常是 `600519`（纯数字），不能只验证顶层 run identity → 缓解：task 4/6/8 验证 L1 candidate、L2 full result、watchlist 输出都使用 canonical ticker（candidate 写入时 canonical 化，或消费方读取时 canonical 化）。
- **[run_id 传播到 L2 的 candidates 载体]** L1 输出 candidates 列表里每条是否带 run_id，还是只 payload 顶层带？→ 决策：只 payload 顶层带 `run_id`，scout 读 L1 文件时从顶层取一次，写进每条 full_results 与 cache entry。不在每条 candidate 重复（避免冗余）。属实现细节，tasks 落实。
- **[canonical 函数对非法 ticker 的容错]** `parse_ticker` 对未知格式返回 `TickerInfo(raw=raw, code=raw, full=raw, market="A")`（不抛错），但 spec 要求非法 ticker 抛 ValueError → 缓解：`canonical_ticker()` 薄封装在 `parse_ticker` 返回 `market="A"` 且 `code==raw`（未识别）时抛 ValueError；已知合法格式（A/HK/US）放行。需单测覆盖边界。
- **[PROFILE_VERSION 与 G1-2 的 SCOUT_SYSTEM_PROMPT 关系]** SCOUT_SYSTEM_PROMPT 是 L2 prompt，属规则常量范畴，其变化也应 bump profile version → 决策：纳入 RULES_HASH 计算的规则常量集合包含 SCOUT_SYSTEM_PROMPT。但 L2 prompt 变化是否影响 L1 排序？不影响（L2 是初筛不是排序）。trade-off：profile version 是「G1 整体规则版本」含 L2 prompt，语义上 L1/L2 共用一个 version 简单，不拆 L1_version/L2_version（避免过度设计）。

## Migration Plan

1. **新增 `data/lib/identity.py`**：`canonical_ticker()` / `canonical_code()` / `generate_run_id(tickers, run_date, profile_version)` / `compute_input_ticker_set_hash(tickers)`。复用 `market_router.parse_ticker`。
2. **新增 `screener/profile.py`**：`PROFILE_VERSION` 常量 + `compute_rules_hash()` + `refresh_rules_hash` 脚本入口。落盘 `screener/.rules_hash`。
3. **改 `screener/main.py`**：`screen_a_shares()` 返回结构加 `run_id`/`profile_version`/`input_ticker_set_hash`（`run_date` 已有）。
4. **改 `scout/quality.py`**：`ScoutCache._path` 用 `canonical_code(ticker)`；`set()` 补 run_id/profile_version/input_ticker_set_hash 字段。
5. **改 `scout/batch.py`**：从 L1 顶层读 run_id 继承（或 fallback），写进 full_results 每条 + cache entry；三元组返回签名不变。
6. **改 `cli.py`**：`_normalize_ticker` 改调 `canonical_ticker`（或删除直接调）；`screen`/`scout` 输出 payload 顶层带 run_id/profile_version/input_ticker_set_hash。
7. **改 `council/debate.py`**：`_debate_path` 用 `canonical_ticker`；`_write_council_output` 命名口径已带后缀（确认 `result.ticker` 是 canonical 形式）。
8. **改 `monitor/aggregation.py`**：`_read_l3_output` pattern 加 canonical 双向回退；`watchlist/{date}.json` 改 `{date}_{run_id[:8]}.json`。
9. **改 `monitor/weekly.py`**：从 L1 文件读 run_id 继承。
10. **迁移脚本 `scripts/migrate_split_l2_cache.py`**：D4 三分支策略，dry-run + 幂等。
11. **收敛 `council/features.py`**：`split(".")[0]` 改调 `canonical_code`（cache key 场景）。

**回滚**：所有改动在 `feat/g1-canonical-run-identity` 分支，`git checkout main` 即回滚；L0 cache 不迁（D3 不动），既有 watchlist/debate 历史文件保留，迁移脚本可逆（带后缀目录数据移到纯数字后，纯数字目录本就该存在）。

## Open Questions

- **run_id 是否需要进 L3 council 产出文件？** 当前决策不强求（AD-01 L3 独立）。但若 L3 从 L2 watchlist 触发（monitor weekly 触发 L3），L3 产出是否带触发它的 run_id 便于追溯？→ 倾向：L3 产出可选带 `triggered_by_run_id`（从 weekly 传入），但 L3 单股手动跑时不带。留 design 待确认，不阻塞 propose。
- **`watchlist/{date}_{run_id[:8]}.json` 命名是否破坏 `monitor watchlist --date` 查询？** `monitor watchlist --date 2026-07-13` 现在读 `watchlist/2026-07-13.json`，改 run-scoped 后该文件不存在 → 缓解：`get_latest_watchlist` 改为按 `{date}_*.json` glob 取最新 run_id。tasks 落实，需同步改 `monitor/diff.py`。
- **RULES_HASH 落盘文件是否进 git？** 倾向进 git（团队共享规则版本基准），但 `.rules_hash` 是生成物，是否该 gitignore？→ 决策：进 git（它是 version 守护的基准，非临时产物，类似 lock 文件）。tasks 落实。
