# Implementation Tasks

> repair child 按 TDD 节奏推进：每条 task 先写红测、再最小实现、再验证转绿。引用 `scout-agent` MODIFIED 24h Cache（cache hit 判定回退 TTL+profile_version，run_id 降 provenance）+ `run-identity` MODIFIED 运行隔离（execution run_id 与 cache 复用边界澄清 + legacy CLI output 不覆盖）+ `watchlist-diff` MODIFIED 增量 diff（latest/previous 按 generated_at 选定）。设计决策见 design.md D1-D5，不重复搬运。不重开 G1-3 主设计（canonical ticker SoT / UUID4 / A+ council 命名 / run-scoped 主设计不动）。

## 1. cache run_id 校验回归修复（spec: scout-agent MODIFIED 24h Cache；design D1）

> **D1 概念澄清**：run_id = execution identity（产物隔离/审计，不参与 cache hit）；profile_version = cache compatibility guard（规则变 → miss）；cache entry run_id = provenance metadata（只写只读不判）。

- [x] 1.1 写红测：`tests/test_scout_quality.py` 重写 `test_scout_cache_get_rejects_mismatched_run_identity`（G1-3 断言「不同 run_id → miss」已失效）为 `test_scout_cache_hit_across_different_runs_same_profile`——run A 写 cache（run_id=rid_a, profile_version=V），run B 同 ticker 同日同 profile_version=V 但 run_id=rid_b 调 `get(ticker, date, profile_version=V)`（不传 run_id）SHALL cache hit（返回 run A 的 verdict），MUST NOT 因 run_id 不同而 miss
- [x] 1.2 写红测：`test_scout_cache_miss_when_profile_version_changed`——cache entry profile_version=V1，当前 run profile_version=V2 → `get(..., profile_version=V2)` SHALL 返回 None（规则变了不复用旧 verdict）
- [x] 1.3 写红测：`test_scout_cache_legacy_without_profile_version_misses`——cache entry 无 profile_version 字段（legacy），当前 run 传 profile_version=V → `get` SHALL 返回 None（无法证明规则版本兼容）
- [x] 1.4 写红测：`test_scout_cache_hit_preserves_source_run_id`——cache hit 返回 run A 的 entry（run_id=rid_a），cache 文件 SHALL NOT 被改写（source run_id=rid_a 保留）；当前 run B 的产物（full_results/CLI payload）SHALL 用当前 run_id=rid_b（验证 scout_batch 调用侧不改写产物 run_id）
- [x] 1.5 实现转绿：改 `scout/quality.py::ScoutCache.get`——删除 `run_id` 参数与第 98 行的 run_id miss 校验；保留 `profile_version` 校验（第 100-102 行）；补「cache entry 缺 profile_version 且调用方传入 profile_version → miss」；`set()` 不变（仍写 run_id provenance）
- [x] 1.6 实现转绿：改 `scout/batch.py` cache.get 调用点——删 `run_id=run_id` 参数，只传 `profile_version=profile_version`；确认 cache hit 时 full_results 仍用当前 run 的 run_id（不改写）
- [x] 1.7 运行 1.1-1.4 红测确认转绿；确认现有 scout_batch cache hit 测试（`test_scout_batch_cache_hit` / `test_scout_batch_usage_summary_counts_cache_hits_separately`，mock_get 签名已用 **kwargs 兼容）不回归

## 2. legacy CLI output 不覆盖（spec: run-identity MODIFIED 运行隔离 / legacy CLI output 无 run_id 不覆盖；design D2）

- [x] 2.1 写红测：`tests/test_cli_screen.py` 新增 `test_cli_screen_output_preserves_legacy_no_run_id_file`——预先在 `--output` 路径放一个无 `run_id` 字段的旧 JSON（模拟 G1-3 前遗留 `data/l1_full.json`），跑 screen 后旧文件 SHALL 不被覆盖（内容不变），新结果 SHALL 写入 run-scoped 分流文件 `{stem}.{run_id[:8]}.json`
- [x] 2.2 写红测：`tests/test_cli_scout.py` 新增 `test_scout_output_preserves_legacy_no_run_id_file`——同上，scout 命令对无 run_id 旧 L2 文件分流不覆盖
- [x] 2.3 写红测：`test_run_scoped_output_path_legacy_corrupted`——目标路径是非 JSON 损坏文件，`_run_scoped_output_path` SHALL 分流（不静默覆盖损坏文件，保留排查证据）
- [x] 2.4 实现转绿：改 `cli.py::_run_scoped_output_path` 第 36 行——`if existing_rid and existing_rid != run_id` → `if existing_rid != run_id`（去 `existing_rid and`，无 run_id=None 或 run_id 不同都分流）
- [x] 2.5 运行 2.1-2.3 红测确认转绿；确认现有 CLI run-scoped 测试（`test_cli_screen_output_run_scoped_same_day_not_overwrite` / `test_scout_output_run_scoped_same_day_not_overwrite`）不回归

## 3. watchlist 按 generated_at 选最新（spec: watchlist-diff MODIFIED 增量 diff；design D3）

- [x] 3.1 写红测：`tests/test_monitor.py` 新增 `test_get_latest_watchlist_uses_generated_at_not_uuid_lexorder`——构造两个 run-scoped 聚合文件，让字典序小的 run_id（`aaaaaaaa`）的 `generated_at` 时间更晚（后生成），字典序大的 run_id（`zzzzzzzz`）的 generated_at 更早；`get_latest_watchlist` SHALL 返回 generated_at 更晚的（字典序小的 aaaaaaaa）文件，MUST NOT 返回字典序大的 zzzzzzzz 文件
- [x] 3.2 写红测：`test_get_previous_watchlist_returns_second_latest_by_generated_at`——3 个聚合文件 generated_at 依次递增，`get_previous_watchlist` SHALL 返回次新（第二个）；只有 1 个文件时 SHALL 返回 None
- [x] 3.3 写红测：`test_get_latest_watchlist_falls_back_to_mtime_when_no_generated_at`——旧 `{date}.json` 纯日期聚合文件无 generated_at，SHALL fallback mtime 参与排序
- [x] 3.4 实现转绿：改 `monitor/diff.py`——抽 `_select_watchlist_by_generated_at(files)` helper（读 generated_at 带时区 ISO 8601 排序，缺失/非法 fallback mtime），`get_latest_watchlist`（第 174 行）/`get_previous_watchlist`（第 241 行）调用之，废弃 `sorted(..., reverse=True)` 文件名字典序
- [x] 3.5 实现转绿：确认 `monitor/aggregation.py` 聚合写 `generated_at` 带时区（若现状是 naive datetime `datetime.now().isoformat()`，改 `datetime.now(timezone.utc).isoformat()` 或本地时区带偏移）；确保 `generated_at` 字段写入聚合 JSON 顶层
- [x] 3.6 运行 3.1-3.3 红测确认转绿；确认现有 `test_monitor.py` / `test_weekly.py` diff/聚合测试不回归

## 4. council CLI 路径提示（spec: 无 spec 变更，纯展示 bug 修复；design D4）

- [x] 4.1 写红测：`tests/test_cli_council.py` 新增 `test_cli_council_echo_uses_canonical_path`——跑 `council --ticker 600519`，stdout 的「辩论记录已写入」提示 SHALL 显示 `debate/600519.SH/{date}.md`（canonical 带后缀），MUST NOT 显示 `debate/600519/{date}.md`（纯数字旧路径）
- [x] 4.2 实现转绿：改 `cli.py:462`——`normalized.split('.')[0]` → `normalized`（canonical_ticker 输出带 `.SH` 后缀，与 `_debate_path` 实际写入路径一致）
- [x] 4.3 运行 4.1 红测确认转绿；确认现有 council CLI 测试不回归

## 5. G1-3 归档状态记录（design D5，无代码变更，纯文档）

- [x] 5.1 在本 design.md Context 段已记录 G1-3 archive tasks 14.3 由 commit `71b4df8` 完成、14.4 rolling handoff 待用户决定（已完成，事实记录，不补写历史 tasks）
- [x] 5.2 不修改 `openspec/changes/archive/2026-07-22-g1-canonical-run-identity/tasks.md`（历史不补写）；若后续治理要求 archive tasks 全勾选，单独做文档修复 commit，不混入本 repair 的运行时修复

## 6. 全量验证与 strict validation

- [x] 6.1 运行定向测试：`cd value-screener && .venv/bin/python -m pytest tests/test_scout_quality.py tests/test_scout_batch.py tests/test_cli_screen.py tests/test_cli_scout.py tests/test_cli_council.py tests/test_monitor.py tests/test_weekly.py -q`，确认新测试通过
- [x] 6.2 运行全量测试：`cd value-screener && .venv/bin/python -m pytest tests -q`，确认不回归（G1-3 baseline 487 passed，本 repair 新增 ~10 测试，预期 ~497 passed，无回归）；本轮运行产生的 `debate/`/`watchlist/` 副产物清理（不进 git）
- [x] 6.3 运行 `openspec validate g1-canonical-run-identity-repair --strict`，确认 change 整体通过（valid）
- [x] 6.4 运行 `openspec validate scout-agent --type spec --strict` + `openspec validate run-identity --type spec --strict` + `openspec validate watchlist-diff --type spec --strict` + `openspec validate g1-fast-personal-value-screening --strict`，确认 canonical 与 umbrella 不被本 repair delta 破坏（归档前 canonical 不含 repair 修改，归档后验证）

## 7. 独立 review 与提交

- [x] 7.1 独立 review：核对 repair 改动是否恰为 5 项 scope，未顺带改 G1-3 主设计（diff 确认 canonical ticker SoT / UUID4 / A+ council 命名 / run-scoped 主设计零改动，只动 cache hit 判定 / CLI 分流条件 / latest 选择 / echo 文本）
- [x] 7.2 核对 cache hit 语义恢复——实地复现 reviewer 的 `same_run_hit / next_run_hit` 场景：run A 写 cache，run B 同 profile_version 不同 run_id 调 get SHALL hit（不再 miss）；确认 AD-03 成本闸门恢复
- [x] 7.3 核对 `git diff --check` 与 staged diff 无空白/无关改动（clean）
- [x] 7.4 提交（commit message：`fix(g1): canonical run identity repair — cache hit 语义恢复 + legacy 不覆盖 + generated_at 排序 + council 路径提示`）（分支 `feat/g1-canonical-run-identity-repair` 或续用 `feat/g1-canonical-run-identity`，基于含 G1-3 的 main）

## 8. 归档与 canonical 同步

- [x] 8.1 运行 `/opsx:archive g1-canonical-run-identity-repair`，同步 delta 到 canonical：`scout-agent`（MODIFIED 24h Cache，补 cross-run hit / profile_version miss / legacy miss / source run_id 保留 4 scenario），`run-identity`（MODIFIED 运行隔离，澄清 cache 复用边界 + legacy CLI output 不覆盖 scenario），`watchlist-diff`（MODIFIED 增量 diff，补 generated_at 排序 + mtime fallback 2 scenario）
- [x] 8.2 归档后验证：`openspec validate scout-agent --type spec --strict` + `openspec validate run-identity --type spec --strict` + `openspec validate watchlist-diff --type spec --strict` + `openspec validate g1-fast-personal-value-screening --strict` 通过
- [x] 8.3 提交归档（commit message：`chore(g1): archive g1-canonical-run-identity-repair + sync canonical specs`）
- [ ] 8.4 生成下一份 rolling handoff（更新 baseline 含 G1-3+repair、记录 G1-3 archive 14.3/14.4 状态、剩余风险、推进 G1-4）——handoff 由用户决定是否生成（apply 阶段不主动写）

## 附录：repair 概念边界（design D1）

| 概念 | 角色 | cache hit 判定 | 产物隔离 |
|---|---|---|---|
| run_id (execution identity) | 定位某次 run + 审计溯源 | 不参与（降级 provenance） | watchlist/CLI output run-scoped 命名 |
| profile_version (compatibility guard) | 规则版本兼容性 | 参与（不同 → miss；缺失 → miss） | 不参与 |
| cache entry run_id (provenance) | 记录 verdict 源自哪次 run | 不参与（只写只读不判） | cache hit 时保留不改写 |

## 附录：Non-Goals 边界

- 不重开 G1-3 的 canonical ticker SoT、UUID4 run_id 生成、A+ council 命名双向回退、run-scoped 产物命名主设计。
- 不引入 `CacheIdentity` 类、不重构 cache 目录结构、不改 cache 路径 `{canonical_code}/{date}/l2_scout.json`。
- 不修改已归档的 `archive/2026-07-22-g1-canonical-run-identity/tasks.md`（历史不补写）。
- 不修 f3c R1 串台根因（独立工作项）。
- 不做 G1-4/G1-5/G1-6（300+ 样本 / 全市场性能成本 / Top 20 校准）。
