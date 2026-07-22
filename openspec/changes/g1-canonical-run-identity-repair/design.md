## Context

G1-3 `g1-canonical-run-identity` 已归档，落地了 canonical run identity 基础设施（canonical ticker SoT / UUID4 run_id / profile_version / input_ticker_set_hash / run-scoped 产物命名）。独立代码级复审发现 5 处真实缺陷，其中 P1 的 3 处退化 G1「快」核心能力。本 repair child 不重开 G1-3 主设计，仅精准修复这 5 处，并澄清一个被 G1-3 实现混淆的核心概念边界。

**当前缺陷实证（均已读代码核实）**：

1. `scout/quality.py::ScoutCache.get` 第 98 行：`if run_id is not None and cached.get("run_id") and cached.get("run_id") != run_id: return None`——不同 run_id 同 profile_version 同 ticker 同日 → cache miss → 每次 L1 新 run 都重调 L2 LLM，破坏 24h 复用（AD-03 成本闸门、`scout-agent` Cache hit 契约）。
2. `cli.py::_run_scoped_output_path` 第 36 行：`if existing_rid and existing_rid != run_id`——旧文件无 `run_id`（G1-3 前遗留，如 `data/l1_full.json`）时 `existing_rid=None`，条件为假，返回原路径覆盖旧文件。
3. `monitor/diff.py::get_latest_watchlist` 第 174 行 / `get_previous_watchlist` 第 241 行：`sorted(..., reverse=True)` 按文件名字典序，run_id 是 UUID4 无时间序，选到字典序最大的 hex 而非最后生成的 run。
4. `cli.py:462`：council 成功提示 `normalized.split('.')[0]` 显示纯数字 `debate/600519/`，但实际写 canonical 路径 `debate/600519.SH/`。
5. `archive/2026-07-22-g1-canonical-run-identity/tasks.md` 14.3 实际已由 commit `71b4df8` 完成但未回填勾选；14.4 rolling handoff 未生成。不补写历史。

## Goals / Non-Goals

**Goals:**
- 恢复 `scout-agent` 24h Cache hit 语义（不同 run_id 同 profile_version → hit），保留规则变更 miss（profile_version 不同 → miss）。
- legacy 产物不被新 run 覆盖（CLI output 无 run_id 也分流；legacy cache 无 profile_version → miss）。
- watchlist「最新」按真实生成时间（`generated_at`）选择，非 UUID 字典序。
- council CLI 路径提示与实际写入一致（canonical 带后缀）。
- 在 repair design + 新 handoff 记录 G1-3 归档状态（14.3 已完成 / 14.4 待定），不修改已归档历史 tasks。

**Non-Goals:**
- 不重开 G1-3 的 canonical ticker SoT、UUID4 run_id 生成、A+ council 命名双向回退、run-scoped 产物命名主设计。
- 不引入 `CacheIdentity` 类、不重构 cache 目录结构、不改 cache 路径 `{canonical_code}/{date}/l2_scout.json`。
- 不修 f3c R1 串台根因（独立工作项）。
- 不做 G1-4/G1-5/G1-6（300+ 样本 / 全市场性能成本 / Top 20 校准）。
- 不修改 `archive/2026-07-22-g1-canonical-run-identity/tasks.md`（历史不补写；如治理要求 archive tasks 全勾选，另做文档修复，不混入运行时修复）。

## Decisions

### D1：execution run_id 与 cache 复用判定解耦（3 概念澄清）

G1-3 实现把「execution run_id」误用作 cache hit 判定，导致回归。本 repair 澄清三个概念的边界，**不引入新类型，仅调整 `get()` 校验逻辑**：

```
run_id (execution identity)
  = UUID4，每次 L1 run 唯一，定位「哪次 run」
  = 用于运行产物隔离（watchlist/CLI output run-scoped 命名）+ 审计溯源
  = 不参与 cache hit 判定

profile_version (cache compatibility guard)
  = 规则版本字符串，规则变 MUST bump
  = 参与 cache hit 判定：profile_version 不同 → miss（规则变了不复用旧 verdict）
  = 缺失（legacy cache 无该字段）→ miss（无法证明规则版本兼容）

cache entry run_id (provenance metadata)
  = cache 写入时记录的源 run_id，只写、只读、不判
  = cache hit 时保留 cache 文件中的 source run_id，不改写 cache 文件
  = 当前 run 产物（full_results / CLI payload）仍用当前 execution run_id
```

**实现**：`ScoutCache.get()` 删除 `run_id` 参数与第 98 行 miss 校验；保留 `profile_version` 校验（第 100-102 行），并补「cache entry 缺 profile_version → miss」。`scout_batch` 调 `cache.get` 不再传 `run_id`，只传 `profile_version`。cache entry 的 `run_id` 仍是 `set()` 写入的 provenance（不动）。

**替代方案**：(a) 引入 `CacheIdentity` 类显式拆分 execution vs reusable——否决，over-engineering，`get()` 删 run_id 校验即达成同样语义，cache 目录与 entry 结构零改。(b) run_id 仍参与校验但用 input_snapshot 特征值匹配——否决，21 字段特征值匹配成本高且 TTL 已保证同日数据不变，profile_version 守护规则变更已够。

### D2：legacy CLI output 不覆盖

`_run_scoped_output_path` 第 36 行 `if existing_rid and existing_rid != run_id` → 改 `if existing_rid != run_id`（去掉 `existing_rid and`）。即：目标文件无 `run_id`（None）或 run_id 不同 → 都分流。旧无 identity 文件视为「不同 run 的遗留产物」，同样不被覆盖。

**边界**：JSON 解析失败（非 JSON / 损坏）的 `existing_rid=None` 也分流——损坏文件不该被静默覆盖（保留作排查证据）。首次运行（文件不存在）仍原路径写（`not output_path.exists()` 分支不变）。

### D3：watchlist 按 `generated_at` 选最新

`get_latest_watchlist` / `get_previous_watchlist` 改用聚合文件的 `generated_at` 字段（带时区 ISO 8601，如 `2026-07-22T14:30:00+08:00`）排序取最新。规则：

1. 读候选聚合文件的 `generated_at`
2. 按 ISO 时间排序，取最新（`get_previous` 取次新）
3. 缺失或非法 `generated_at` 的旧文件 → fallback 到文件 mtime
4. 两个函数共用同一选择逻辑（抽 helper `_select_watchlist_by_generated_at`）

**`generated_at` 字段来源**：`watchlist-aggregation` canonical spec「watchlist JSON 结构」已要求 `generated_at`（ISO 8601 时间戳）。repair 确认 `monitor/aggregation.py` 聚合时写入带时区的 `generated_at`（若现状是 naive datetime，补时区）。

**替代方案**：(a) mtime 主依据——否决，`cp`/`touch`/git checkout 改 mtime，跨机器不可靠，reviewer 已否决。(b) UUID 字典序——否决，run_id 无时间序，本 bug 根因。(c) manifest 文件索引 run_id→时间——否决，over-engineering，`generated_at` 字段已在 spec 要求、已在 JSON 内，读取代价极低。

### D4：council CLI 路径提示

`cli.py:462` `normalized.split('.')[0]` → 直接用 `normalized`（`_normalize_ticker` 返回的 canonical ticker，带 `.SH`）。一行改，与 `_debate_path` 实际写入路径一致。

### D5：G1-3 归档状态记录（不补写历史）

不修改 `archive/2026-07-22-g1-canonical-run-identity/tasks.md`。在本 design 的 Context 段 + 新 rolling handoff 记录：14.3 已由 commit `71b4df8` 完成（事实），14.4 rolling handoff 待用户决定生成（task 原文「由用户决定是否生成」）。若后续治理要求 archive tasks 必须全勾选，单独做文档修复 commit，不混入运行时代码修复。

## Risks / Trade-offs

- **[run_id 降级为 provenance 后，跨 run cache 复用恢复，但审计能否溯源到原 run？]** → 缓解：cache entry 仍写 source run_id（`set()` 不变），cache hit 时返回的 entry 含 source run_id，消费方可读到「这条 verdict 来自 run X 的 cache」；当前 run 产物仍带当前 execution run_id。溯源链完整，只是 hit 判定不再用 run_id。
- **[legacy cache 无 profile_version → miss，会否导致 G1-3 前的 cache 全部失效？]** → 缓解：这正是预期——G1-3 前 cache 无规则版本标识，新规则 run 复用它们不安全（无法证明兼容）。失效后 24h 内重新调 LLM 刷新，成本可接受（AD-03 既有预算内）；且这是「规则升级后的正确失效」。
- **[`generated_at` 缺时区的旧聚合文件]** → 缓解：fallback 到 mtime；新聚合写带时区 ISO。解析时用 `datetime.fromisoformat`（Python 3.11+ 支持带时区 ISO），naive datetime 按 fallback 处理。
- **[`get_previous_watchlist` 按 generated_at 取次新，若只有 1 个聚合文件]** → 缓解：返回 None（既有行为，无 previous）。测试覆盖。
- **[修复后 G1-3 的 cache identity 测试需调整]** → `test_scout_cache_get_rejects_mismatched_run_identity` 当前断言「不同 run_id → miss」，修复后该断言失效（应改为「不同 run_id 同 profile_version → hit」）。该测试需重写为修复后的预期，属本 repair 的 tasks。

## Migration Plan

1. **`scout/quality.py`**：`get()` 删 run_id 参数与 miss 校验，保留 profile_version 校验 + 补 legacy miss；`set()` 不变（仍写 run_id provenance）。
2. **`scout/batch.py`**：`cache.get` 调用点删 `run_id=` 参数，只传 `profile_version=`。
3. **`cli.py`**：`_run_scoped_output_path` 去 `existing_rid and`；council echo 用 `normalized` 不 split。
4. **`monitor/diff.py`**：抽 `_select_watchlist_by_generated_at`，`get_latest_watchlist`/`get_previous_watchlist` 调用之。
5. **`monitor/aggregation.py`**：确认 `generated_at` 带时区写入（若 naive 补时区）。
6. **测试**：重写 `test_scout_cache_get_rejects_mismatched_run_identity` 为「不同 run_id 同 profile_version → hit」；新增 legacy CLI output / generated_at 排序 / council 路径提示 红测。
7. 无数据迁移（cache 目录结构零改，legacy cache 自然 miss 后刷新）。

## Open Questions

- 无。5 项 scope + 3 概念边界 + 测试矩阵均已与用户确认（2026-07-22）。`generated_at` 时区、legacy miss 行为、不补写历史均已拍板。
