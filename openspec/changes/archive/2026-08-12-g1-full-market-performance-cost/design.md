## Context

G1 umbrella tasks 5.1/5.2/5.3 要求对完整可交易 A 股集合执行真实 L1+L2 证据。`g1-300-sample-validation` 已建立离线 fixture/contract foundation 并合入 main，但 fixture 不是真实全市场证据。当前 `screen_a_shares` 和 `scout_batch` 已具备完整漏斗输出（stats 含 after_hard_gates/after_factors/after_heat_filter/input_scale/industry_pe_degraded）、L2 full-result 契约（full_results/usage_summary/failure_summary），但需要明确硬性 Gate 与观测指标的边界，并将本地缓存可用性与数据新鲜度拆分。

本 child 补 performance/cost 证据采集层，并修复真实运行暴露的证据口径问题：可用率按 canonical field status 判定、缓存可用性与数据新鲜度分离、子集/全市场 coverage 明确区分。真实全市场运行还暴露了 malformed LLM JSON 导致 `one_liner` KeyError 的 L2 full-result contract 缺口，本 child 同步修复该证据可见性问题。不修改 L1 筛选规则、provider adapter 或 ScreeningProfile；L2 仅作 full-result contract repair，不改变 scout 筛选逻辑。

## Goals / Non-Goals

**Goals:**

- 编排真实 L1+L2 运行，记录总耗时和分阶段耗时；耗时 15 分钟为参考阈值，不参与硬性 Gate。
- 统计关键字段可用率（单独计算，不从 stats 派生），必须至少 95%。
- 归一 L2 成本口径：实测 token usage × 单价 + 等效全量调用推算；¥2 为参考阈值，不参与硬性 Gate。
- 暴露未处理异常计数，必须为 0。
- 输出可复核的 evidence bundle JSON，含硬 Gate 结果、观测指标、漏斗、降级分布、失败分布、成本、缓存状态、新鲜度和运行配置。
- 遵守 canonical `pledge_ratio` 语义：`record_not_found` 保持 `None + pledge_status`，由 evidence 层判定为 usable（known-zero）；`source_failed` 保持 `None + pledge_status` 并计为 missing。
- 将 `cache_warm` 与 `data_freshness` 分离：前者判断本地可计算性，后者描述 fresh/stale/missing/invalid。
- 支持 `allow_stale` 受控本地验证；该模式只读取存在且结构有效的缓存，不触发 provider。生产默认 `require_fresh` 仍按 freshness policy 刷新 stale 数据。
- `require_fresh` 与 `allow_stale` 均必须拒绝 JSON 可读但不满足 G1 维度最低结构合同的 payload；`allow_stale` 只额外放宽 TTL。

**Non-Goals:**

- 不修改 L1 筛选规则（hard_gates/factor_scores/anti_trap/heat_filter 的判定逻辑）、L2 scout 逻辑、provider adapter 或 ScreeningProfile。
- 不新增依赖。
- 不把 fixture/300-sample 结果当作本 child 的完成证据。
- 不勾选 umbrella 5.1/5.2/5.3 以外的 Gate（6.x Top 20、7.x closure），不宣称 G1 capability passed。
- 冷缓存运行不作为本 child 的 Gate 判定，但可作为缓存预热与成本基线；完整可交易集合的 warm-cache Gate 需要先有可审计的全量缓存。

## Decisions

### D1：纯证据采集层，包裹而非修改现有 pipeline

新增 `value-screener/performance/run_evidence.py`，以函数方式包裹 `screen_a_shares` + `scout_batch`，在调用前后记录耗时、在输出上计算可用率和成本。不修改 `screener/main.py`、`scout/batch.py` 的任何已有函数签名或返回结构。

选择包裹而非内嵌，是为了保证 L1/L2 的现有测试和行为不受影响，同时让 evidence module 可独立测试和演进。

### D2：关键字段可用率独立计算

可用率从 L1 `output_candidates` 的实际字段和 status 计算，不从 `stats` 派生。关键字段集合为 G1 排序所需的最小集：`ticker`、`f_score`、`adjusted_composite`、`pe_ttm`、`pb`、`pledge_ratio`。一般字段逐只检查非 None 且非空字符串；`pledge_ratio=None + pledge_status=record_not_found` 按 canonical data-minimum-contract 记为 usable，`source_failed`/`invalid_value`/无 status 仍为 missing。可用率 = usable 字段槽位数 / (候选数 × 关键字段数)。

选择独立计算而非派生 stats，是因为 stats 只记录漏斗计数，不反映字段级缺失；可用率是 Gate 的独立维度。

### D3：L2 成本口径归一

成本采集两种口径：

- 实测成本：`usage_summary.total_tokens` × ¥0.001/1k token（AD-03 基准单价）。
- 等效全量成本：`(call_count + cache_hits)` × 单只平均 token × 单价，反映无缓存时的全量成本。

两种口径都写入 evidence bundle。两者均为观测指标；`gate_thresholds.reference_max_l2_cost_yuan=2.0` 仅作为参考阈值和展示口径，不参与硬性 Gate 判定。

如果 `call_count=0` 且只有 cache hits，则没有可观察的单只 token 基准，`equivalent_full_yuan` 必须为 `null`，不能把“无法外推”伪装成 0 元。

### D4：未处理异常从 failure_summary 取

`scout_batch` 的 `failure_summary["unhandled_exceptions"]` 已保证为 0（兜底 catch all），但这不等于没有 L2 业务错误。evidence module 直接读取该字段；`failure_summary.errors` 必须原样写入 `exceptions.error_details`，`funnel.l2_error` 必须保留。若未处理异常非 0，evidence bundle 标记硬 Gate 失败。

### D5：Evidence bundle 结构

输出 JSON envelope 包含：

- `schema_version`、`run_id`、`profile_version`、`input_ticker_set_hash`（从 L1 继承）、`input_tickers`（精确输入集合）；
- `run_date`、`cache_warm`（bool）、`data_freshness`（按维度的新鲜度详情）、`mode`（`live`/`simulated`）；
- `timing`：`total_elapsed_seconds`、`l1_elapsed_seconds`、`l2_elapsed_seconds`；
- `funnel`：`total`、`after_hard_gates`、`after_factors`、`after_heat_filter`、`l2_input`、`l2_deep_dive`、`l2_watch`、`l2_skip`、`l2_error`、`l2_degraded`；
- `field_availability`：`rate`、`checked_fields`、`total_fields`、`missing_count`；
- `cost`：`measured_yuan`、`equivalent_full_yuan`、`call_count`、`cache_hits`、`total_tokens`；
- `exceptions`：`unhandled_count`、`error_details`；
- `run_config`：`exclude_cyclicals`、`force_l2`、`semaphore_concurrency`、`l2_timeout_seconds`、`ticker_count`；
- `hard_gate_passed`：bool，仅由字段可用率和未处理异常决定；
- `observed_metrics`：真实耗时和 L2 成本观测值及其参考阈值；
- `metrics_gate_passed`：兼容字段，含义改为 `hard_gate_passed`，不再表示耗时/成本四项联合判定；
- `gate_passed`：`coverage=full_market` 且 `hard_gate_passed=true`；
- `gate_thresholds`：记录 `min_field_availability=0.95`、`max_unhandled_exceptions=0` 硬阈值，以及 `reference_max_elapsed_minutes=15`、`reference_max_l2_cost_yuan=2.0` 观测参考阈值。

### D6：pledge_ratio canonical status 保留与 evidence 可用率映射

`RiskFetcher` 已正确区分三态：`record_found`（有值）、`record_not_found`（查无记录 = known-zero）、`source_failed`（provider 失败）。canonical data-minimum-contract 要求 candidate 边界保留 `None + pledge_status`，不得用 0.0 改写 known-zero，也不得用 0.0 掩盖 provider 失败。

修复：`screen_a_shares` 输出 candidates 时保持 `pledge_ratio` 原值并补充 `pledge_status`。evidence 层在计算可用率时，`record_not_found` 计为 usable，`source_failed`/`invalid_value`/无 status 计为 missing。这不改变 `hard_gates`、factor、L2 或 monitor 的原始 risk 语义，也不会丢失 provenance。

根因数据：首次 560 只运行中，190 只 candidates 有 117 个 `pledge_ratio=None`；其中 `record_not_found` 属 canonical usable，不能简单视为 missing。修复后应以 status-aware 可用率重新报告，而不是通过改写 candidate 值让 Gate 转绿。

### D7：缓存可用性与数据新鲜度分离

`cache_warm` 只检查文件存在、JSON 可读和各 G1 维度最低结构合同，不因 TTL 过期而判定不可用。`data_freshness` 单独按维度统计 `fresh/stale/missing/invalid`、最老/最新数据年龄和使用的 freshness/TTL 配置。生产默认 `require_fresh`：缓存 stale 时按现有 provider 采集语义刷新；受控本地验证使用 `allow_stale`：只读取存在且结构有效的本地数据，不触发 provider。L2 scout cache 命中单独写入 cost，不与 `cache_warm` 混用。Evidence bundle 中保留的旧 `warm_cache`/`cache_status` 仅为向后兼容别名，不是新合同的权威字段；新代码和新消费者必须读取 `cache_warm`/`data_freshness`。

### D8：coverage 与可复现性显式记录

Evidence bundle 必须记录：

- `schema_version`；
- `coverage`: `partial_market` 或 `full_market`；
- `input_tickers`：精确输入列表，支持按 hash 复核与重放；
- `run_config.ticker_count` 与 `run_config.ticker_source`；
- `input_ticker_set_hash`；
- `evidence_notes`：子集运行、L2 scout cache 复用、L1 缓存未全暖和成本外推口径。

已缓存子集（例如本次 560 只）只能证明输入集合上的 pipeline、异常和字段 status 口径；不能关闭完整可交易集合的全市场 Gate。耗时与成本是规模相关观测指标，不从 560 只线性外推为 5208 只 Gate 通过。首次 L2 成本还需区分真实调用与 scout cache 命中，`equivalent_full_yuan` 只是按本次单只平均 token 的参考外推。

### D9：缓存路径查询无副作用

`CacheManager._path` 的读路径查询不得创建 ticker 目录；只有 `set()` 写入时创建父目录。这样 `_check_cache_warmth` 和普通 `get/is_expired` 不会污染 `data/cache/`，缺失缓存预检可在临时目录中安全验证。失败 bundle 使用唯一 artifact id，避免同日覆盖历史失败证据。L2 evidence 的并发/超时配置从 scout/council 的共享常量读取，避免复制值漂移。

### D10：child spec delta 与 umbrella Gate 分工

本 child 的 `specs/g1-full-market-performance-cost/spec.md` 是本 change 的可验证 delta 载体；它不把 partial-market 运行冒充为 umbrella full-market Gate。umbrella `g1-fast-personal-value-screening` 仍是 G1 capability 的最终权威，只有完整可交易集合运行才能关闭 umbrella 5.2。

## Risks / Trade-offs

- **[Risk] 真实全市场运行依赖 provider 可用** → 如果 AkShare/东财 spot 不可用，运行会失败；evidence bundle 保留失败证据，标记 `gate_passed=false`，不以默认值伪造成功。
- **[Risk] cache 可用性与新鲜度混淆** → evidence bundle 同时记录 `cache_warm` 和 `data_freshness`，allow_stale 只放行结构有效的本地缓存，不改变生产 require_fresh 语义。
- **[Risk] 成本单价假设可能过时** → AD-03 基准 ¥0.001/1k token 是当前 LLM 单价假设，evidence bundle 显式记录单价假设，单价变化时只需重算。
- **[Risk] pledge_ratio status 语义跨边界** → candidate 保持 `None + pledge_status`，evidence 只在可用率统计时把 `record_not_found` 记为 usable；原始 risk、H6、factor、L2、monitor 语义不被改写。新增测试覆盖 status-aware availability 与 provenance。
- **[Risk] 全量 Gate 规模尚未证实** → 560 只子集不能关闭完整可交易集合的 Gate；bundle 的 `coverage` 和 `evidence_notes` 强制标注事实口径。全量 5542 只需单独完成缓存预热与 warm-cache 运行。
- **[Risk] L2 成本受缓存命中影响** → `measured_yuan` 记录本次真实 token 消耗；`cache_hits` 与 `equivalent_full_yuan` 单独展示，不能把 L2 cache 复用成本当成无缓存首次成本。
- **[Risk] 预检 cache root 副作用** → 预检使用纯路径拼接和已有目录检查，不调用 `CacheManager._path`。
- **[Trade-off] 包裹式设计增加一层间接** → 换取 L1/L2 逻辑零修改、现有测试零回归。
- **[Trade-off] status-aware availability 不改变 candidate 数值** → 保留 canonical provenance，Gate 统计按 status 解释字段状态。

## Migration Plan

1. 在独立 worktree 中先写 evidence module 的失败测试（RED）。
2. 添加最小实现：`run_full_market_evidence` 函数 + evidence bundle 输出。
3. 修复 `screen_a_shares` candidate 投影：保持 `pledge_ratio` 的 `None + pledge_status` canonical 语义。
4. 增加缓存温暖度预检。
5. 运行 focused pytest 使测试转绿。
6. 在共享 venv 下用已缓存子集执行一次明确标记为 `partial_market` 的 warm-cache 验证。
7. 只有完整可交易集合缓存预热完成后，才执行 `coverage=full_market` 的最终 Gate 运行。
   - universe 获取支持离线兜底：实时 akshare 重试 3 次，失败兜底已生成快照文件；证据脚本支持 `--tickers-file` 显式传入 universe（口径含快照生成时间与来源，写入 `ticker_source`），保证 basic TTL=2h 约束下「最后刷 basic → 立即运行」的编排可离线复现。
8. 保存 evidence bundle 到 `data/evidence/` 路径。
9. 运行回归测试、`openspec validate --strict`、`compileall` 和 `git diff --check`。

## Open Questions

- 本 child 的 full-market scope 固定为沪深 A 股（`.SH`/`.SZ`）；北交所 `.BJ` 不纳入本 Gate。ticker 列表来源（`stock_info_a_code_name()` 或 `stock_zh_a_spot_em()`）取决于 provider 可用性，运行时确定，并必须写入 `ticker_source`。
- cold-cache SLA 是否需要单独设 Gate，在 warm-cache Gate 通过后另行决定。
- 约 5208 只沪深 ticker 的 warm-cache 运行需要先完成一次完整冷缓存采集（预估 2+ 小时）；北交所 334 只不在本 child scope 内。当前已缓存子集只作为 partial-market pipeline evidence，不关闭 umbrella 5.2。
