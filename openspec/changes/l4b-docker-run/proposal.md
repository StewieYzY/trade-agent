## Why

L0→L4 骨架已全部落地，但**从未端到端跑通过一只真实票**——现有 `debate/` 记录要么是单 agent 模式（R2-R4 跳过），要么四 agent 输出高度同质化，`watchlist/*.json` 的 `consensus_summary/conviction` 全为 null。要验证系统是否真的成立，必须在 Docker 里用真实 LLM 跑通一次。但当前 Docker 只剩半套：`Dockerfile` 能构建，却没有 `docker-compose.yml`（跑 L2/L3 要手拼一长串 `docker run -e ...`），也没有数据卷声明（`data/cache`、`watchlist/`、`debate/` 写在容器内，容器删了就丢）。同时 L1 在单只/小批输入下有语义退化（`compute_industry_median_pe` 样本不足返回空 dict、`top_300` 截断无意义），虽然 `council --ticker` 可绕开 L1 走最小闭环，但完整 `L1→L2→L3` 链路在单只验证时会踩到这个退化。本 change 补齐 Docker 运行时 + 修复 L1 单只语义退化 + 以两道真实实跑验证门收尾。

> 核实发现（修正原范围）：原拟"修复 L1→L2 字段接缝"基于一个错误前提——实际 L2 `scout_batch` 从 L1 candidate **只读 `ticker` 一个字段**（`scout/batch.py:128`），其余 L1 产出全被丢弃，L2 经 `assemble_snapshot(ticker)` 从 L0 缓存自取自算。因此**不存在 L2 读 L1 未产字段导致 None/报错的运行时断裂**，无需修复。L1 算力未被 L2 复用、L1/L2 同源指标口径分叉（ROE 5 年 vs 3 年、f_score 数据源不同）属于架构层问题，不在本 change 范围，留待后续 change 评估。

## What Changes

- **新增 `docker-compose.yml`**：定义 `value-screener` 服务，注入全部 LLM 环境变量（`LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL` / `LLM_MODEL_HEAVY` / `LLM_MODEL_MODERATE`，从宿主 `.env` 或环境读取），挂载三个数据卷（`./data:/app/data`、`./watchlist:/app/watchlist`、`./debate:/app/debate`），解决"容器删了产出丢"和"手拼 docker run -e"两个缺口。
- **`Dockerfile` 加 `VOLUME` 声明**：对 `/app/data`、`/app/watchlist`、`/app/debate` 三个路径声明 VOLUME，作为无 compose 时的兜底。
- **修复 L1 单只/小批语义退化**（`screener/main.py` + `data/lib/industry_mapper.py`）：
  - `compute_industry_median_pe` 在样本数不足时已返回空 dict（不崩），但 `screen_a_shares` 未据此降级提示——补 stats 字段标记 `industry_pe_degraded: true`，让下游和人能看见"行业折价锚为空"。
  - `top_300 = candidates_with_scores[:300]` 在输入 < 300 时只是少截，不崩，但 stats 里 `after_factors` 的语义在全市场 vs 单只时不同——补 `input_scale` 字段（`full_market` / `subset`）标记本次输入规模。
  - 不改 heat_filter（已核实单只自参照分位，语义完整）。
- **新增 `docker-runtime` capability** 的 spec：定义 Docker 运行时的契约（服务定义、env 注入、数据卷持久化）。
- **两道真实实跑验证门**（写入 tasks，作为 change 验收门槛）：
  1. **最小闭环门**：`docker compose run --rm value-screener council --ticker 600519`（跳过 L1，AD-01 允许 L3 手动输入），用真实 LLM 产出 `debate/600519/{date}.md` + `watchlist/{date}_600519.SH.json`，验证 L0→L3→L4 接口写出闭环。
  2. **完整链路门**：`batch` 采一小批（~20 只）→ `screen` 跑这批 → `scout` 跑 L2 → 从 deep_dive 里挑一只 → `council` 跑 L3，验证 L1→L2→L3 拼接 + L1 单只语义退化处理生效。

## Capabilities

### New Capabilities
- `docker-runtime`: Docker 容器化运行时——compose 服务定义、LLM env 注入、数据卷持久化（data/watchlist/debate 三卷）、`docker compose run` 调用 CLI 子命令的契约。

### Modified Capabilities
- `scout-agent` 相关的 L1 输出消费：无 spec 级变更（L2 只读 ticker 的行为不变，本次只是把"为何不修"这个核实结论记入 design，不改 spec）。
- L1 screener 的 stats 输出：当前无独立 `screener` capability spec（L1 行为散落在各 change 的 design 里）。本次给 `screen_a_shares` 输出新增 `industry_pe_degraded` / `input_scale` 两个 stats 字段，属于输出 schema 扩展。若 `openspec/specs/` 下无对应 capability，则作为新 requirement 纳入 `docker-runtime` 的关联说明，不单建 spec。

## Impact

- **新增文件**：`value-screener/docker-compose.yml`、`value-screener/.env.example`（LLM env 模板，不含真实 key）、`openspec/specs/docker-runtime/spec.md`。
- **修改文件**：`value-screener/Dockerfile`（加 VOLUME）、`value-screener/screener/main.py`（stats 加 `industry_pe_degraded` / `input_scale`）、`value-screener/data/lib/industry_mapper.py`（`compute_industry_median_pe` 返回值携带 `degraded` 信号，或由 main.py 据空 dict 推断）、对应测试。
- **CI/构建**：compose 文件需能 `docker compose config` 校验通过；Dockerfile 改动需能重新 build。
- **成本**：实跑验证门消耗真实 LLM token——最小闭环 ~¥0.7（单 agent R1，`council/README.md` 锚点），完整链路 ~¥2（L2 20 只 × ¥0.01/只，AD-03）+ ~¥20-60（L3 全天团单只，AD-03）。
- **不动**：L3 council、L4 monitor、watchlist JSON schema（L3→L4 接缝已核实对齐）、scout prompt、RULE 三层体系、前端。
