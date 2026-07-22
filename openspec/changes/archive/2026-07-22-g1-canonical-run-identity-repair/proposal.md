## Why

G1-3 `g1-canonical-run-identity` 已归档（2026-07-22，archive/2026-07-22-g1-canonical-run-identity/），交付了 canonical run identity 基础设施。但独立代码级复审发现 5 处真实缺陷，其中 3 处 P1 直接退化 G1「快」核心能力——尤其 `ScoutCache.get()` 的 run_id miss 校验破坏了 24h L2 cache 复用，违背 AD-03 成本闸门与 `scout-agent` Cache hit 契约。G1-3 已归档不可原地重开，需 repair child 精准修复后再合 main、再推进 G1-4。

## What Changes

- **[P1] cache run_id 校验回归修复**：`ScoutCache.get()` 删除对 `run_id` 的 miss 校验，保留 `profile_version` 校验。run_id 降级为 cache entry 的 provenance 元数据（只写、只读、不参与 hit 判定）。不同 run_id 同 profile_version 同 ticker 同日 SHALL cache hit，恢复 24h 复用语义。
- **[P1] legacy cache 无 profile_version → miss**：缺 `profile_version` 的旧 cache entry 视为 miss（无法证明规则版本兼容），避免新规则 run 静默复用规则版本不明的旧 verdict。
- **[P1] legacy CLI output 不覆盖**：`cli.py::_run_scoped_output_path` 在目标文件无 `run_id`（G1-3 前遗留产物）时也分流，不再覆盖旧无 identity 文件。
- **[P1] watchlist 按 `generated_at` 选最新**：`get_latest_watchlist`/`get_previous_watchlist` 改用聚合文件 `generated_at`（带时区 ISO 8601）排序取最新，mtime 仅作 fallback；废弃 UUID 字典序排序（run_id 无时间序）。
- **[P2] council CLI 路径提示**：`cli.py` council 成功提示改用 canonical ticker（带 `.SH` 后缀），不再 `split('.')[0]` 显示纯数字旧路径。
- **G1-3 归档状态记录**：在 repair design + 新 rolling handoff 记录 G1-3 archive tasks 14.3 已由 commit `71b4df8` 完成、14.4 rolling handoff 待用户决定。不修改已归档历史 tasks（不补写过去）。

## Capabilities

### New Capabilities
<!-- 无新增 capability，全部为既有 capability 的 requirement 精化 -->

### Modified Capabilities
- `scout-agent`: MODIFIED `24h Cache with Input Snapshot`——cache hit 判定回退到「TTL + profile_version」语义，run_id 不参与 hit 判定（仅 provenance）；legacy cache 无 profile_version → miss。
- `run-identity`: MODIFIED「运行隔离」requirement——精化 execution run_id（产物隔离/审计）与 cache 复用判定的边界，澄清 run_id 不用于 cache hit；补「不同 run_id 同 profile_version → cache hit」scenario。
- `watchlist-aggregation`: MODIFIED「聚合 L1/L2/L3」或新增排序 scenario——`get_latest_watchlist`/`get_previous_watchlist` 按 `generated_at` 选最新（非文件名字典序/mtime 主依据）。

## Impact

- 代码：`value-screener/scout/quality.py`（`ScoutCache.get`）、`value-screener/scout/batch.py`（cache.get 调用点）、`value-screener/cli.py`（`_run_scoped_output_path` + council echo）、`value-screener/monitor/diff.py`（`get_latest_watchlist`/`get_previous_watchlist`）、`value-screener/monitor/aggregation.py`（确保聚合写 `generated_at` 带时区）。
- 契约：`scout-agent` 24h Cache hit 语义恢复（AD-03 成本闸门）；`run-identity` 运行隔离契约澄清；`watchlist-aggregation` latest 选择逻辑。
- 非目标：不重开 G1-3 的 canonical ticker SoT、UUID4 run_id、A+ council 命名、run-scoped 主设计；不引入 `CacheIdentity` 类或重构 cache 目录结构；不修 f3c R1 串台根因；不做 G1-4/G1-5/G1-6。
- 不修改已归档的 `archive/2026-07-22-g1-canonical-run-identity/tasks.md`（历史不补写）。
