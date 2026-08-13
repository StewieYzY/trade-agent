## Context

G1 umbrella §6 产品 Gate 要求对固定 run 的 Top 20 做用户逐只人工复核。已通过工程 Gate 的固定 run 是 `7887d515-157d-4d17-bcb5-fab54c7fbee3`（2026-08-12，profile `g1-2026-07-21`，input hash `9d20ac29743c`，沪深 5208 只，`coverage=full_market`，`hard_gate_passed=true`），归档 bundle 为 `openspec/changes/archive/2026-08-12-g1-full-market-performance-cost/evidence/2026-08-12_7887d515.json`（SHA-256 `80334e3b…760d`，见同目录 evidence-index.md）。

**已知事实约束（决定本设计）**：

1. pinned bundle 只保存聚合指标（timing/funnel/availability/cost）与 `input_tickers`，**没有保存逐票候选与排序**。
2. Scout cache 无 2026-08-12 的 L2 逐票结果；`data/universe_full.json` 已不存在。pinned run 的输入集合只能从 bundle 的 `input_tickers`（5208 只，canonical 带后缀）恢复。
3. L1 `screen_a_shares` 在 `freshness_policy=allow_stale` 下是确定性离线计算：只读结构有效的本地缓存，不调用 provider（既有测试 `test_allow_stale_cache_reads_without_provider` 保证），不涉及 LLM。相同输入集合 + 相同规则版本 + 相同缓存 → 相同候选与排序。
4. `run_id` 按 `data/lib/identity.py` 合同是每次执行唯一的 uuid4；`profile_version` 与 `input_ticker_set_hash` 才承担「规则版本」与「输入集合」身份。因此任何再派生都会产生新的 `run_id`，必须显式记录它与 pinned run 的关系，而不是冒充 pinned run。

## Goals / Non-Goals

**Goals:**

- Top 20 的输入集合、排序、run identity 可追溯到 pinned run。
- 用户逐只复核记录结构化、可审计、不可被静默篡改语义（非法输入即阻断）。
- Gate 判定严格：≥14/20 才通过；失败/不可判定不写成通过。
- 全程离线（L1-only，allow_stale），零 provider/LLM 调用，零新增依赖。

**Non-Goals:**

- 不重跑 L2、不调用 LLM、不产生新的工程 Gate 证据。
- 不修改 umbrella 7.x closure、不进入 G2/G3、不做前端/问卷系统。
- 不修复「pinned run 未保存逐票结果」这一历史缺口（只在 evidence 中如实记录并建议后续工程 run 持久化逐票结果）。

## Decisions

### D1. Top 20 来源：pinned run 的确定性 L1 再派生

`top20 derive` 从 pinned bundle 读取 `input_tickers` 与 pinned identity，调用 `screen_a_shares(input_tickers, freshness_policy="allow_stale")` 复现候选排序。Top 20 = 派生候选列表的前 20 只（run 的 canonical 排序：hard gates → factor top-300（adjusted_composite 降序）→ heat filter 后的列表顺序，即 adjusted_composite 降序）。

不采用「重跑 L1+L2 并把新 run 当产品 run」：新 run 没有工程 Gate 证据，且 L2 verdict 是新的 LLM 输出，不属于 pinned run，会违反「固定通过工程 Gate 的 run」。

不采用「从 scout cache 读 pinned run 的 L2 verdict」：cache 中不存在该 run 的逐票结果，且 scout cache TTL=24h 已过期；伪造读取路径会引入不可审计来源。

### D2. Pinned ↔ derivation 身份绑定

evidence 记录两组身份：

- `pinned_run`: {run_id, profile_version, input_ticker_set_hash, run_date, source_evidence_path, source_evidence_sha256(可选校验)}，来自归档 bundle。
- `derivation_run`: {run_id(新 uuid4), profile_version, input_ticker_set_hash, run_date, derivation_kind="deterministic_l1_replay", freshness_policy="allow_stale"}。

绑定校验（任一失败 → `not_evaluable`，不产生 Top 20 Gate 结论）：

- derivation `profile_version` == pinned `profile_version`（规则版本未变）。
- derivation `input_ticker_set_hash` == pinned `input_ticker_set_hash`（输入集合一致；canonical 归一使顺序/写法无关）。
- derivation 漏斗统计（after_hard_gates / after_factors / after_heat_filter / candidate 数）== pinned bundle `funnel` 对应项（数据未漂移的交叉验证）。

### D3. 候选不足不凑数

若派生候选少于 20，只取实际数量；Gate 阈值按实际数量 n 的 ≥70% 判定（`worth_count * 10 >= n * 7`，精确整数比较避免浮点误差；n=20 时即 ≥14）。MUST NOT 降门槛补足 20。

### D4. 用户复核记录合同

复核文档为 JSON（schema `g1-top20-user-review.v1`），由用户填写 label 与 reason：

```json
{
  "schema_version": "g1-top20-user-review.v1",
  "pinned_run_id": "7887d515-...",
  "derivation_run_id": "...",
  "profile_version": "g1-2026-07-21",
  "input_ticker_set_hash": "9d20ac29743c",
  "reviews": [
    {"rank": 1, "ticker": "600519.SH",
     "label": "worth_further_research",
     "reason": "用户逐只理由（非空）"}
  ]
}
```

- label 枚举（三者必居其一，非法值报错）：
  - `worth_further_research`（值得进一步研究）
  - `not_worth_further_research`（不值得进一步研究）
  - `unable_to_judge_insufficient_data`（无法判断/数据不足）
- 校验规则：Top 20 每只恰好一条记录（缺失/多余/重复均阻断）；`rank` 与 `ticker` 必须与 derivation 一致；`reason` 必须是非空字符串（去空白后）。任何违规 → 抛错/`not_evaluable`，MUST NOT 静默接受或部分计分。
- 用户复核是真实人类判断：MUST NOT 用模型输出、历史 debate/watchlist 结果、fixture 或任何自动填充代替；模板中 label/reason 初始为空，只能由用户填写。

### D5. Gate 语义（三态）

- `passed`：全部记录合法且 `worth_research_count * 10 >= n * 7`。
- `failed`：全部记录合法但 worth 比例不足。失败 evidence 必须保留，供后续校准 child change 使用；本 child 不做校准、不重跑。
- `not_evaluable`：身份绑定失败、复核记录缺失/非法、derivation 失败（如缓存被破坏导致异常）。不得输出 Gate 通过结论。

三态都写入 evidence；`gate_verdict` 字段只允许 `passed`/`failed`/`not_evaluable`。`passed` 仅表示 6.2 产品 Gate 通过，MUST NOT 被表述为 G1 capability passed。

### D6. Evidence 路径与审计

- 运行产物（gitignore 目录）：`value-screener/data/evidence/g1-top20-style-review/`
  - `top20_derivation.json`（derive 输出：pinned/derivation identity、完整候选上下文、Top 20 明细）
  - `user_review_template.json`（给用户填写的模板，逐只预填 rank/ticker/identity 上下文，label/reason 留空）
  - `top20_gate_evidence.json`（finalize 输出：全部审计字段 + Gate verdict）
- 归档复核副本：真实用户 Gate 完成后复制进 `openspec/changes/g1-top20-style-review/evidence/`，并在 `evidence-index.md` 登记 SHA-256、来源路径与解释（与既有 child 归档惯例一致）。
- evidence 必须保留：pinned/derivation identity、Top 20 逐只记录（rank/ticker/adjusted_composite/因子与 anti-trap 摘要）、用户逐只 label+reason、统计（n、worth/not_worth/unable 计数、比例）、gate_verdict 与判定依据。

### D7. 防冒充与 WIP 保护

- derive/finalize 全程不访问 LLM/provider；测试使用注入的 fake L1 输出与 tmp_path，不读写真实 `data/cache`、`debate/`、`watchlist/`。
- finalize 不接受没有逐只记录的输入；「只有汇总比例」的输入 MUST 被拒绝（无法逐只审计）。
- 本 child 不修改根目录用户 WIP（`design/g1-scale-precheck-handoff-2026-08-06.md`、`openspec/changes/g1-300-sample-validation/`、`value-screener/scripts/build_validation_sample.py`），不修改既有 runtime evidence 与 umbrella tasks.md。
- derive 只读 pinned bundle；finalize 只读 derivation 产物与用户复核文档；写入仅限本 change 的 evidence 目录。
- derive 的离线保证由缓存温暖度预检强制执行：`allow_stale` 只能复用结构有效的本地缓存，缓存缺失会退回 provider 抓取；因此 derive 在调用 `screen_a_shares` 前用 `_check_cache_warmth` 对 pinned 输入集合做预检，`cache_warm=false`（missing/invalid>0）即 exit 2 拒绝并说明恢复路径，绝不静默发起抓取。

## Risks / Trade-offs

- [Risk] pinned run 未保存逐票结果，Top 20 依赖「确定性再派生」而非原始产物 → 缓解：D2 三重绑定校验 + 漏斗交叉验证；evidence 如实标注 `derivation_kind`；建议后续工程 run 持久化逐票结果（记录为后续改进项，不在本 child 实现）。
- [Risk] 2026-08-12 之后本地缓存若被改动，再派生结果可能漂移 → 漏斗交叉验证失败即 `not_evaluable`，不静默产出 Top 20。
- [Risk] 用户复核主观性 → 固定标签枚举 + 强制逐只理由 + 记录全量保留，使主观判断可审计、可复盘。
- [Trade-off] Top 20 采用 L1 排序（adjusted_composite 降序）而非 L2 confidence 排序：pinned run 的 L2 逐票结果不可恢复，L1 排序是 pinned run 输入下唯一可确定性复现的 canonical 排序；用户复核的是筛选器排序质量，符合产品 Gate 意图。

### 已实现风险记录（2026-08-13）

首次真实 `top20 derive` 执行即暴露上述第一条风险的实际形态：pinned run `7887d515` 的 evidence bundle 只含聚合指标，未归档逐票候选；其 warm cache（26040 槽位）位于已被清理的全市场 child worktree 内（untracked `data/cache`），本机主 checkout 仅剩 73 个 code 的旧缓存，废纸篓与 Time Machine 本地快照均无残留。因此 pinned run 的 Top 20 目前无法离线确定性复现，6.1/6.2 处于 not-evaluable-blocked 状态，等待用户决定的受控恢复路径（见 tasks.md 4.5）。本 child 的派生/校验/Gate 实现与测试不受影响；该发现同时证明 D2 漏斗交叉验证的必要性——数据快照缺失时必须阻断而不是勉强产出名单。后续工程 run 应持久化逐票候选与（或）数据快照引用，作为独立改进项，不在本 child 实现。

## Migration Plan

无迁移。新增模块与新 CLI 子命令，不改既有行为。

## Open Questions

无。标签枚举、阈值（≥70%，即 ≥14/20）、evidence 路径均已在 umbrella spec 与 roadmap 中确定。
