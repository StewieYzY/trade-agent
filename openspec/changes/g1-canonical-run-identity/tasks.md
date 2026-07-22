# Implementation Tasks

> 本 child 按 TDD 节奏推进：每条 task 先写红测、再最小实现、再验证转绿、最后提交。引用 `run-identity` delta spec（5 ADDED requirement）+ `scout-agent` delta（MODIFIED 24h Cache + CLI Integration）+ `watchlist-aggregation` delta（MODIFIED 聚合 L1/L2/L3）。breaking change：`ScoutCache` 路径从原始 ticker 改为 `canonical.code`（既有分裂目录需迁移）；`watchlist/{date}.json` 同日覆盖改为 `{date}_{run_id[:8]}.json` run-scoped 命名。设计决策见 design.md D1-D7，不重复搬运。

## 1. canonical ticker SoT（spec: run-identity / Canonical Ticker 单一 SoT；design D1）

- [x] 1.1 写红测：`tests/test_identity.py` 新增 `test_canonical_ticker_pure_digit_adds_suffix`——`canonical_ticker("600519")` 返回 `"600519.SH"`，`canonical_ticker("920060")` 返回 `"920060.BJ"`（BJ 不误判 SH，修 cli._normalize_ticker 的 bug）
- [x] 1.2 写红测：`test_canonical_ticker_uppercases_suffix`——`canonical_ticker("600519.sh")` / `"600519.SH"` / `"920060.bj"` 统一返回大写 `"600519.SH"` / `"920060.BJ"`，同证券不同大小写产出相同 canonical
- [x] 1.3 写红测：`test_canonical_ticker_hk_us_compat`——`canonical_ticker("00700.HK")` 返回 `"00700.HK"`，`canonical_ticker("AAPL")` 返回 `"AAPL"`，不抛错
- [x] 1.4 写红测：`test_canonical_ticker_invalid_raises`——非法 ticker（非 6 位数字、非已知后缀、非 HK/US）抛 `ValueError` 附清晰原因，MUST NOT 静默返回原值
- [x] 1.5 写红测：`test_canonical_code_returns_pure_digit`——`canonical_code("600519.SH")` / `"600519"` 返回纯 6 位 `"600519"`，与 `CacheManager._normalize_ticker`（D3）行为一致
- [x] 1.6 实现转绿：新增 `value-screener/data/lib/identity.py`，`canonical_ticker(raw)` 薄封装调 `parse_ticker(raw).full`（复用 market_router，不重写解析器），未识别格式（`market=="A"` 且 `code==raw`）抛 `ValueError`；`canonical_code(raw)` 返回 `parse_ticker(raw).code`
- [x] 1.7 运行 1.1-1.5 红测确认转绿（5 passed）

## 2. PROFILE_VERSION + 规则常量 hash 守护（spec: run-identity / ScreeningProfile Version；design D3）

- [x] 2.1 写红测：`tests/test_profile_version.py` 新增 `test_profile_version_is_module_constant`——`screener.profile.PROFILE_VERSION` 存在且为非空字符串
- [x] 2.2 写红测：`test_rules_hash_guard_fails_when_rules_change_without_bump`——monkeypatch `compute_rules_hash` 返回新 hash（模拟规则源码变了）但不 bump PROFILE_VERSION，守护测试 SHALL 失败（红）；bump PROFILE_VERSION 后 SHALL 通过（design D3：用 monkeypatch 模拟而非改真规则源码，避免 fragile）
- [x] 2.3 写红测：`test_rules_hash_stable_across_runs`——相同规则源码文件多次计算 `compute_rules_hash()` 返回相同 hash（确定性）
- [x] 2.4 实现转绿：新增 `value-screener/screener/profile.py`，`PROFILE_VERSION = "g1-2026-07-21"` 模块常量；`compute_rules_hash()` 对规则源码文件内容（`hard_gates.py`/`factor_scores.py`/`anti_trap.py`/`heat_filter.py`/`main.py`/`scout/prompt.py`）算 sha256（design D3 更新：规则常量是函数体内联字面量非模块级，抽常量会违反「规则模块零改动」约束，改 hash 源码文件内容）；落盘 `screener/.rules_hash` 存 `{hash, profile_version}`；守护测试比对当前 hash+version 与落盘值，规则变但 version 未 bump → 红
- [x] 2.5 新增 `refresh_rules_hash` 脚本入口（`python -m screener.profile --refresh`），开发者改规则后刷新落盘 hash + 提示 bump version
- [x] 2.6 运行 2.1-2.3 红测确认转绿（3 passed）；确认落盘 `screener/.rules_hash` 进 git（非 gitignore）

## 3. run_id 生成（uuid4 唯一）+ 输入集合 hash（确定性）（spec: run-identity / Run ID 生成与传播 + 输入快照 Identity；design D2 纠正版）

> **D2 纠正**：原 task 3.x 用「稳定摘要 sha256(input_hash|run_date|profile_version)」，与 D6「同日不同 run 不覆盖」矛盾。改 uuid4（每次唯一）+ input_hash 独立确定性。已勾选状态失效，重做。

- [x] 3.1 写红测：`test_generate_run_id_unique_per_call`——相同 ticker 集合 + 相同 run_date + 相同 profile_version 两次调用 `generate_run_id` 返回**不同** run_id（uuid4，每次唯一，非稳定 hash）
- [x] 3.2 写红测：`test_input_ticker_set_hash_stable_and_differs_on_input_change`——`compute_input_ticker_set_hash` 相同集合两次返回相同 hash（确定性），集合变化（增删改）→ hash 不同；不同顺序相同 hash（sorted 消除顺序）。input_hash 与 run_id 解耦：input_hash 定性「输入集合」，run_id 定位「哪次 run」
- [x] 3.3 写红测：`test_generate_run_id_is_uuid4_format`——run_id SHALL 匹配 uuid4 标准格式（`xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx`），`uuid.UUID(rid)` 不抛错
- [x] 3.4 写红测：`test_input_ticker_set_hash_canonicalizes`——同证券不同形式（600519 vs 600519.SH）→ 相同 hash（canonical 归一后 hash）
- [x] 3.5 实现转绿：改 `identity.py::generate_run_id` 为 `str(uuid.uuid4())`（不再 sha256 摘要）；`compute_input_ticker_set_hash` 保持 `sha256("|".join(sorted(canonical_ticker(t) for t in tickers)))[:12]` 确定性不变；`generate_run_id` 签名可简化（不再需要 tickers/run_date/profile_version 作 run_id 输入，但保留 input_hash 生成用 tickers）
- [x] 3.6 运行 3.1-3.4 红测确认转绿；确认 task 1.x 的 canonical 测试不回归

## 4. L1 主入口生成 run_id（uuid4）+ candidate canonical ticker（spec: run-identity / Run ID L1 生成 + Canonical Ticker 传播；design D2 纠正 + 问题2）

> **D2 纠正 + 问题2**：run_id 改 uuid4（4.2 语义变）；L1 candidate 用原始输入 ticker（常纯数字），需 canonical 化使 candidate/L2/watchlist 统一 canonical。4.x 勾选状态部分失效，4.2 重做 + 新增 4.5。

- [x] 4.1 写红测：`tests/test_screener_main.py` 新增 `test_screen_a_shares_returns_run_identity`——`screen_a_shares(tickers)` 返回结构顶层含 `run_id`/`run_date`/`profile_version`/`input_ticker_set_hash` 四字段，非空
- [x] 4.2 写红测：`test_screen_a_shares_run_id_unique_per_call`——相同 tickers + 相同日（mock date.today）两次调用返回**不同** run_id（uuid4 唯一，非稳定 hash）。原 `test_screen_a_shares_run_id_stable_for_same_input` 断言失效（D2 纠正）
- [x] 4.3 实现转绿：改 `screener/main.py::screen_a_shares`，返回结构加四字段（`run_id = str(uuid.uuid4())`，`input_ticker_set_hash` 调 `identity.compute_input_ticker_set_hash`，`profile_version` 调 `profile.PROFILE_VERSION`）；不改漏斗逻辑、不改 `G1_QUANT_DIMENSIONS` 白名单（G1-1 闭合不重开）
- [x] 4.4 写红测：`test_screen_a_shares_candidates_use_canonical_ticker`——输入纯数字 `600519`，返回 candidates[].ticker SHALL 是 canonical `600519.SH`（问题2：candidate ticker canonical 化，非原样透传纯数字）
- [x] 4.5 实现转绿：`screen_a_shares` 构造 candidate 时 ticker canonical 化（`canonical_ticker(ticker)`），使 L1 candidate / L2 full result / watchlist 输出统一 canonical；不改 candidate 其他字段结构
- [x] 4.6 运行 4.1/4.2/4.4 红测确认转绿；确认现有 `test_screener*.py` 不回归（既有测试若断言纯数字 candidate ticker 需同步改）

## 5. ScoutCache 路径 canonical.code + run identity 绑定（spec: scout-agent MODIFIED 24h Cache；design D4）

- [x] 5.1 写红测：`tests/test_scout_quality.py`（或 test_scout_batch）新增 `test_scout_cache_path_uses_canonical_code`——`ScoutCache._path("600519.SH", "2026-07-21")` 与 `_path("600519", "2026-07-21")` 返回相同路径 `data/cache/600519/2026-07-21/l2_scout.json`，MUST NOT 建 `600519.SH/` 目录
- [x] 5.2 写红测：`test_scout_cache_entry_binds_run_identity`——`ScoutCache.set(...)` 写入的 cache entry 含 `run_id`/`profile_version`/`input_ticker_set_hash`（继承自参数），与既有 `input_snapshot`/`verdict`/`confidence` 并存
- [x] 5.3 写红测：`test_scout_cache_existing_21_fields_preserved`——cache entry 仍含既有 21 字段 `input_snapshot`（pe_ttm/pb/roe_3y 等）+ `timestamp`，run identity 字段是补充非替换
- [x] 5.4 实现转绿：改 `scout/quality.py::ScoutCache._path` 用 `canonical_code(ticker)` 建目录；`set()` 签名加 `run_id`/`profile_version`/`input_ticker_set_hash` 参数，写入 cache_data；`get()` 返回的 entry 含这些字段
- [x] 5.5 运行 5.1-5.3 红测确认转绿；确认现有 ScoutCache 测试不回归（mock 调用方补新参数）
- [x] 5.6 写红测 + 修复 `clear(ticker=...)` canonical bug：原 `clear` 用原始 ticker 拼目录（`self.base / ticker`），传 `600519.SH` 找不到 canonical 化后的 `600519/` 目录返回 0 → 改用 `canonical_code(ticker)` 与 `_path` 对齐；红测 `test_scout_cache_clear_uses_canonical_code`
- [x] 5.7 写红测 + 实现 `get()` identity 校验：`get` 加可选 `run_id`/`profile_version` 参数，缓存 entry 含该字段但不匹配当前 run → 返回 None（视为 miss，不混用跨 run/跨规则缓存）；不传维持原 TTL-only 行为（向后兼容）；`scout_batch` 调 `cache.get` 传当前 run_id/profile_version；红测 `test_scout_cache_get_rejects_mismatched_run_identity` + `test_scout_cache_get_rejects_mismatched_profile_version`

## 6. scout_batch 继承 run_id（spec: scout-agent MODIFIED CLI Integration + run-identity / Run ID L2 继承；design D2 + Migration 5）

- [x] 6.1 写红测：`tests/test_scout_batch.py` 新增 `test_scout_batch_inherits_run_id_from_l1`——candidates 携带或 L1 顶层含 `run_id`/`profile_version`/`input_ticker_set_hash`，scout_batch 的 full_results 每条 + cache entry SHALL 继承，MUST NOT 生成新 run_id
- [x] 6.2 写红测：`test_scout_batch_fallback_run_id_when_no_l1`——candidates 无 run_id（手动构造，非来自 L1），scout_batch SHALL fallback 生成 run_id 标注 `run_id_source: "scout_fallback"`，MUST NOT 报错中断
- [x] 6.3 写红测：`test_scout_batch_triple_contract_unchanged`——scout_batch 仍返回三元组 `(full_results, usage_summary, failure_summary)`，签名不变（G1-2 闭合不重开），run identity 作 full_results 每条元数据补充
- [x] 6.4 实现转绿：改 `scout/batch.py`，从 L1 candidates/顶层读 run_id（或 fallback 生成），写进每条 full_results + 传给 `ScoutCache.set`；三元组返回签名不变
- [x] 6.5 运行 6.1-6.3 红测确认转绿；确认现有 G1-2 契约测试（returns_triple/shortlist_derived/failure_locates 等）不回归

## 7. CLI screen/scout 输出 run identity（spec: scout-agent MODIFIED CLI Integration + run-identity；design D6 + Migration 6）

- [x] 7.1 写红测：`tests/test_cli_scout.py` 新增 `test_cli_scout_payload_carries_run_identity`——scout 输出四字段 payload 顶层含 `run_id`/`profile_version`/`input_ticker_set_hash`（从 L1 输入文件继承）
- [x] 7.2 写红测：`tests/test_cli_screen.py`（或扩展）新增 `test_cli_screen_payload_carries_run_identity`——screen 输出结构顶层含四字段
- [x] 7.3 写红测：`test_cli_normalize_ticker_uses_canonical`——`cli._normalize_ticker` 改调 `canonical_ticker`，`920060` 返回 `"920060.BJ"`（修 BJ 误判 SH bug），`600519.sh` 返回 `"600519.SH"`
- [x] 7.4 实现转绿：改 `cli.py::_normalize_ticker` 改调 `identity.canonical_ticker`（删除自补后缀逻辑）；`screen`/`scout` 输出 payload 顶层带 run identity 四字段（screen 从 screen_a_shares 返回取，scout 从 L1 文件顶层读）
- [x] 7.5 运行 7.1-7.3 红测确认转绿；确认现有 CLI 测试不回归
- [x] 7.6 写红测：`test_cli_screen_output_run_scoped_same_day_not_overwrite` + `test_scout_output_run_scoped_same_day_not_overwrite`——同 `--output` 路径两次运行 run_id 不同，第二次 SHALL 改写 `{stem}.{run_id[:8]}.json` 分流，旧 run 文件 SHALL 仍可读不被覆盖（对应 scout-agent MODIFIED CLI Integration / 运行隔离 `#### Scenario: Same-day multiple runs do not overwrite`；D6 apply 阶段纠正采 A 方案，原「不强制改 --output 文件名」否决）
- [x] 7.7 实现转绿：`cli.py` 加 `_run_scoped_output_path(output, run_id)` helper（目标不存在/同 run → 原路径；run_id 不同 → 分流 `{stem}.{run_id[:8]}.json`），`screen`/`scout` 输出段调用之；更新 design.md D6 记录 A 方案决策

## 8. council 命名 A+ 兼容层（spec: watchlist-aggregation MODIFIED + run-identity SoT；design D5 A+ 边界 + Migration 7）

> **A+ 兼容层**：新写入统一 canonical，旧产物保留只读 + 读取双向回退。覆盖 run_debate 入口 canonicalize / _debate_path 写 canonical / _check_cache 回退旧纯数字 / force 清 canonical+旧 / _write_council_output 只写 canonical。

- [x] 8.1 写红测：`test_debate_path_uses_canonical_ticker`——`_debate_path("600519.SH")` 与 `_debate_path("600519")` 返回相同路径 `debate/600519.SH/{date}.md`（canonical 带后缀）；`_debate_path("920060")` → `debate/920060.BJ/{date}.md`（BJ 不误判 SH）
- [x] 8.2 写红测：`test_run_debate_canonicalizes_input_ticker`——`run_debate("600519")` 与 `run_debate("600519.SH")` 最终写入**同一** canonical 路径（debate md `debate/600519.SH/` + watchlist `{date}_600519.SH.json`），无论输入纯数字还是带后缀
- [x] 8.3 写红测：`test_check_cache_falls_back_to_legacy_digit_dir`——既有 `debate/600519/{date}.md`（纯数字旧目录）SHALL 被 `_check_cache("600519.SH")` 命中（canonical 路径不存在时回退纯数字旧目录）
- [x] 8.4 写红测：`test_force_clears_both_canonical_and_legacy`——`force=True` 同时清理 canonical 路径与旧纯数字路径的当日文件，旧内容不残留
- [x] 8.5 写红测：`test_write_council_output_only_canonical`——`_write_council_output` 无论 `result.ticker` 是 `600519` 还是 `600519.SH`，只写 `watchlist/{date}_600519.SH.json`（canonical，不分裂）
- [x] 8.6 实现转绿：改 `council/debate.py`：`run_debate` 入口 `canonical = canonical_ticker(ticker)` 后续全用 canonical；`_debate_path` 写 canonical 路径；`_check_cache` 先查 canonical 路径再回退 `debate/{canonical_code}/{date}.md`；`force=True` unlink canonical + 旧纯数字当日文件；`_write_council_output` 用 `canonical_ticker(result.ticker)` 写 watchlist。改 `council/features.py:24` 的 `split(".")[0]` → `canonical_code`（cache key 场景）
- [x] 8.7 运行 8.1-8.5 红测确认转绿；改既有 council 测试（手动构造 `debate/600519/` 旧目录断言 cache 命中 → 现 _check_cache 回退仍命中，测试应转绿或调整为构造 canonical 路径）；确认现有 council 测试不回归

## 9. _read_l3_output 双向回退 + watchlist run-scoped（spec: watchlist-aggregation MODIFIED + run-identity 运行隔离；design D5+D6 + Migration 8）

- [x] 9.1 写红测：`tests/test_aggregation.py` 新增 `test_read_l3_output_canonical_fallback`——`_read_l3_output(canonical="600009.SH", date="2026-07-13")` 按序回退匹配 `2026-07-13_600009.SH.json` → `2026-07-13_600009.json`，优先返回真数据
- [x] 9.2 写红测：`test_read_l3_output_reads_real_data_not_empty_shell`——同天同票并存 `2026-07-13_600009.json`（空壳，字段全 null）与 `2026-07-13_600009.SH.json`（真数据），`_read_l3_output` SHALL 读真数据文件（内容完整性判断）
- [x] 9.3 写红测：`test_watchlist_run_scoped_naming`——聚合输出文件名 `{date}_{run_id[:8]}.json`，同日多次运行不同 run_id 不互相覆盖，旧 run 仍可读
- [x] 9.4 写红测：`test_get_latest_watchlist_glob_run_scoped`——`get_latest_watchlist` 按 `{date}_*.json` glob 取最新 run_id 文件（兼容旧 `{date}.json` 历史文件）
- [x] 9.5 实现转绿：改 `monitor/aggregation.py::_read_l3_output` pattern 加 canonical 双向回退（带后缀 → 纯数字；纯数字 → 带后缀），优先返回内容完整文件；`watchlist/{date}.json` 改 `{date}_{run_id[:8]}.json`；`get_latest_watchlist` glob 兼容新旧命名
- [x] 9.6 运行 9.1-9.4 红测确认转绿；确认现有 `test_aggregation.py`/`test_weekly.py` 不回归

## 10. monitor weekly 继承 run_id + history run-scoped 兼容（spec: run-identity / Run ID weekly 继承 + 运行隔离；design D2+D6 + Migration 9）

> **D5 纠正**：原 task 10.2 假设 `history()` 读 debate md 加双向回退——实读 `diff.py:226-275`，`history()` 读聚合 `watchlist/{date}.json` 不读 debate md。改 task 10.2 为 history 的 run-scoped 命名兼容（per-ticker 跳过逻辑不误跳 run-scoped 聚合文件）。

- [x] 10.1 写红测：`tests/test_weekly.py` 新增 `test_run_weekly_inherits_run_id_from_l1`——weekly 从 L1 文件读 run_id 继承，周报含 `run_id`
- [x] 10.2 写红测：`tests/test_diff.py`（或 test_monitor）新增 `test_history_reads_run_scoped_aggregate`——`history(ticker)` 读聚合 watchlist，run-scoped 命名 `{date}_{run_id[:8]}.json`（含 `_`）SHALL 不被 per-ticker 跳过逻辑误跳（per-ticker 文件第二段是 ticker 含字母/`.SH`，run-scoped 第二段是 hex run_id 前缀，区分两者）；既有旧 `{date}.json` 仍可读
- [x] 10.3 实现转绿：改 `monitor/weekly.py` 从 L1 文件读 run_id 继承；改 `monitor/diff.py::history` 区分 per-ticker 文件（`{date}_{ticker}.json`，第二段含字母/`.`，跳过）与 run-scoped 聚合文件（`{date}_{run_id[:8]}.json`，第二段 hex，读），兼容旧 `{date}.json`
- [x] 10.4 运行 10.1-10.2 红测确认转绿；确认现有 weekly/diff 测试不回归

## 11. ScoutCache 分裂目录迁移脚本（spec: scout-agent MODIFIED 24h Cache / Existing split safely migrated；design D4 + Migration 10）

- [x] 11.1 写红测：`tests/test_migrate_split_l2_cache.py`（新建）覆盖三分支：空壳带后缀目录（无 l2_scout.json）→ 删；带后缀有真数据+纯数字也有数据 → 以纯数字为真值，带后缀归档后删；带后缀有真数据无纯数字（孤儿）→ 移到纯数字再删
- [x] 11.2 写红测：`test_migrate_idempotent`——迁移脚本幂等，二次运行无操作
- [x] 11.3 写红测：`test_migrate_dry_run`——`--dry-run` 模式只打印不执行
- [x] 11.4 实现转绿：新增 `scripts/migrate_split_l2_cache.py`，D4 三分支策略 + `--dry-run` + 幂等；不丢真实数据
- [x] 11.5 运行 11.1-11.3 红测确认转绿

## 12. 全量验证与 strict validation

- [ ] 12.1 运行定向测试：`cd value-screener && .venv/bin/python -m pytest tests/test_identity.py tests/test_profile_version.py tests/test_scout_batch.py tests/test_scout_quality.py tests/test_cli_scout.py tests/test_cli_screen.py tests/test_aggregation.py tests/test_weekly.py tests/test_migrate_split_l2_cache.py -q`，确认新测试通过
- [ ] 12.2 运行全量测试：`cd value-screener && .venv/bin/python -m pytest tests -q`，确认不回归（G1-2 baseline 435 passed，本 child 新增 ~30 测试，预期 ~465 passed，无回归）；本轮运行产生的 `debate/`/`watchlist/` 副产物清理（不进 git）
- [ ] 12.3 运行 `openspec validate g1-canonical-run-identity --strict`，确认 change 整体通过（valid）
- [ ] 12.4 运行 `openspec validate run-identity --type spec --strict`——归档前 run-identity canonical 不存在（新 capability），delta 在归档时同步进 canonical；归档后验证
- [ ] 12.5 运行 `openspec validate scout-agent --type spec --strict` + `openspec validate watchlist-aggregation --type spec --strict` + `openspec validate g1-fast-personal-value-screening --strict`，确认 canonical 与 umbrella 不被本 child delta 破坏

## 13. 独立 review 与提交

- [ ] 13.1 独立 review：核对 identity 模块改动是否恰为「canonical SoT + run_id + profile version + input hash」，未顺带改漏斗逻辑/verdict 判定链/prompt 内容（diff 确认 screener/hard_gates/factor_scores/anti_trap/heat_filter 零改动，只动 main.py 返回结构）
- [ ] 13.2 核对消费方升级是否覆盖全部（screener/main + scout/batch + scout/quality + cli + council/debate + council/features + monitor/aggregation + monitor/weekly + monitor/diff），无遗漏旧归一化（grep `split(".")[0]` / `_normalize_ticker` 仅剩 canonical SoT 与 D3 CacheManager 两处）
- [ ] 13.3 核对 `git diff --check` 与 staged diff 无空白/无关改动（clean）
- [ ] 13.4 提交（commit message：`feat(g1): canonical run identity — canonical ticker SoT + run_id + profile version + input snapshot`）（分支 `feat/g1-canonical-run-identity`，基于含 G1-1+G1-2 的 main）
- [ ] 13.5 勾选 `g1-fast-personal-value-screening/tasks.md` 的 3.2

## 14. 归档与 canonical 同步

- [ ] 14.1 运行 `/opsx:archive g1-canonical-run-identity`，同步 delta 到 canonical：新增 `run-identity` capability（5 ADDED requirement），`scout-agent`（MODIFIED 24h Cache + CLI Integration），`watchlist-aggregation`（MODIFIED 聚合 L1/L2/L3）
- [ ] 14.2 归档后验证：`openspec validate run-identity --type spec --strict` 通过（新 canonical 已建）；`openspec validate scout-agent --type spec --strict` + `openspec validate watchlist-aggregation --type spec --strict` + `openspec validate g1-fast-personal-value-screening --strict` 通过
- [ ] 14.3 提交归档（commit message：`chore(g1): archive g1-canonical-run-identity + sync canonical specs`）
- [ ] 14.4 生成下一份 rolling handoff（更新 baseline、上一 child 证据、剩余风险、推进 umbrella 3.2 勾选、下一 child G1-4）——handoff 由用户决定是否生成（apply 阶段不主动写）

## 附录：身份概念 → 消费方波及面

| 身份概念 | SoT 位置 | 消费方 | 升级动作 |
|---|---|---|---|
| canonical ticker | `data/lib/identity.py::canonical_ticker` | cli / council / scout / monitor | 5 处旧归一化收敛到 canonical_ticker（cache key 场景用 canonical_code，D3 CacheManager 不动） |
| canonical code（cache key） | `data/lib/identity.py::canonical_code` | ScoutCache / CacheManager / council/features | ScoutCache._path 改用 canonical_code；CacheManager D3 不动；features.py split 改调 canonical_code |
| run_id | `data/lib/identity.py::generate_run_id`（L1 生成） | screener/main / scout/batch / monitor/weekly | L1 唯一生成，L2/weekly 继承，纯 L2 单跑 fallback |
| profile_version | `screener/profile.py::PROFILE_VERSION` | screener/main / scout/batch / cli | 模块常量 + hash 守护测试，规则变 MUST bump |
| input_ticker_set_hash | `data/lib/identity.py::compute_input_ticker_set_hash` | screener/main / scout/quality | L1 生成，L2 cache entry 绑定 |

## 附录：Non-Goals 边界

- 不重开 G1-1 分层采集边界（`G1_QUANT_DIMENSIONS` 白名单不动，只给它加 profile version 绑定）。
- 不重设计 G1-2 的 `scout_batch` 三元组 / `full_results` / `failure_summary`（run identity 作元数据补充，不改返回签名）。
- 不做 300+ 多行业样本、全市场性能/成本运行、Top 20 风格校准（属 G1-4/G1-5/G1-6）。
- 不实现 G2 Council、G3 holding runtime、前端或部署。
- 不引入配置文件层承载规则（用代码常量 + 测试守护，零依赖）。
- 不迁 L0 cache 目录（D3 已统一），不迁既有 watchlist/debate 历史文件（保留只读 + 双向回退读取）。
- 不修 f3c 的 R1 agent 间串台根因（独立工作项；G1-3 修 ScoutCache 路径 canonical 化顺带降低该风险点）。
- 不强求 L3 继承 run_id（AD-01 独立管线边界，L3 单股手动跑可不带 run_id）。
