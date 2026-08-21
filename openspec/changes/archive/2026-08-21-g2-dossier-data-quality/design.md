## Context

`build_research_dossier` 已组装四个角色维度，但每个数字只存在于 raw fetcher payload，
没有来源、报告期、发布时间、新鲜度或降级状态。`data/lib/provenance.py` 解决的是
provider raw response 与 canonical snapshot 之间的资格契约，不覆盖 dossier 角色事实。
因此 G2 umbrella 2.1-2.3 需要一个独立、纯 Python 的 dossier 事实契约层，在不改动
prompt / debate / audit chain 主契约的前提下补齐角色事实证据。

## Goals / Non-Goals

**Goals:**

- 为角色事实定义字段级事实契约和关闭的取值词汇。
- 让 `build_research_dossier` 携带可读、可复核的事实契约、质量状态和原因。
- 高严重度事实缺失来源或时间基准，或来源与数字不匹配时 fail closed。
- stale / 降级事实显式可见，不伪装 clean evidence。

**Non-Goals:**

- 不修改主 prompt、debate 编排、审计链主契约或三个 fetcher。
- 不引入 growth expectation 诊断，不扩大 scope 到 2.3 之外的 G2 能力。
- 不改变 `core_snapshot` / `research_dossier` 中原始 role payload 的形状。
- 不新增依赖，不调用真实 provider/LLM。

## Decisions

### D1. 事实契约是 sidecar，不改 raw role payload

`main_business`、`peers`、`research`、`capex_proxy` 继续保留原 dict 形状，prompt
角色分发和 `_validate_council_input` 的既有消费路径不变。`fact_contract` 作为顶层
sidecar 描述从这些 payload 中提取出的每个关键事实。这样既不破坏现有 prompt/编排，
也能让下游代码显式读取来源与质量状态。

### D2. 关闭的字段级词汇

事实记录包含：

- `role`：`main_business` | `peers` | `research` | `capex_proxy`
- `fact_key`：稳定、可定位到 raw payload 的路径（如 `main_business.by_industry[0].revenue`）
- `label`：人类可读名称
- `value`：提取到的原始值
- `severity`：`high` | `medium` | `low`
- `source`：事实来源标识
- `report_period`：报告期；不适用时为 `null`
- `as_of`：时间基准的检索或快照时间；report_period 不适用时用它兜底
- `published_at`：来源发布时间；当前 fetcher 不提供时为 `null`
- `retrieved_at`：本次 dossier 组装时间
- `freshness`：`fresh` | `stale` | `unknown`
- `degradation_status`：`clean` | `degraded` | `unavailable`
- `traceable`：布尔，source 存在且 report_period/as_of 至少一个存在

未知的 severity、freshness 或 degradation_status 直接抛 `FactContractError`。

### D3. 来源与时间基准从已知 fetcher 契约确定性推导

当前 fetcher 不返回来源/检索时间元数据，因此 source 由角色类型映射：

| role | source |
|---|---|
| main_business | `eastmoney.stock_zygc_em`（有 breakdown 时）或 `ths.stock_zyjs_ths`（纯文本兜底） |
| peers | `eastmoney.stock_board_industry_cons_em` |
| research | `eastmoney.stock_research_report_em` |
| capex_proxy | `data/cache/{code}/financials.CONSTRUCT_LONG_ASSET` |

`report_period` 取 raw payload 中的报告日期（main_business 的 `report_date`、capex 的
最新 `years` 年份）；peers/research 无报告期，用 `as_of=retrieved_at` 作为时间基准。
`research.published_at` 现在由 `ResearchFetcher` 从研报 DataFrame 的
`日期/发布日期/报告日期` 列取最新值，作为来源发布时间保留在事实证据中；它不覆盖
`report_period`/`as_of` 的新鲜度判定，避免一个旧发布时间把刚检索到的当前快照误标为
stale。未来 fetcher 若直接返回来源元数据，可扩展映射而不改变契约形状。

### D4. 高严重度事实 fail closed，stale 与降级只降级不阻断

高严重度字段限定在：

- main_business：每个 breakdown entry 的 `revenue`、`revenue_ratio`、`gross_margin`
- peers：`peer_avg_pe`
- research：`consensus_eps`、`target_price`
- capex_proxy：`latest`

对任一已出现的高严重度数字，若 source 缺失、时间基准缺失、值非有限数字，或 raw
payload 声明的 `code` 与请求 ticker 不一致，`build_research_dossier` 必须 fail closed
（抛 `FactContractError`），不返回 dossier。`build_fact_contract(fail_closed=False)`
保留同一份不可追溯事实但导出 `failed=true`，供诊断消费者读取。

stale 或降级不 fail closed，而是把 `quality_status` 设为 `degraded` 并写入
`quality_reasons`；`fact_contract.clean` 为 false。这样“不可信”证据可以被诊断读取，
但不会伪装成 clean evidence。

### D5. 新鲜度由时间基准年龄决定

`freshness` 判定使用 `report_period` 的最后一天和 `as_of` 作为事实时间基准；任一已提供
且超过 `stale_after_days`（默认 730 天）即为 `stale`。两者都缺失时回退到
`retrieved_at`；时间基准缺失或非法为 `unknown`。`published_at` 只保存为来源元数据，
不参与上述年龄计算。`now`、`retrieved_at` 和 `stale_after_days` 均可注入，保证测试
确定性。

### D6. 追溯率统计口径只统计已出现的事实

分子 `traceable_fact_count`、分母 `total_fact_count` 都只统计 raw payload 中实际出现
的关键事实。未成功获取的 role 不计入分母，避免“缺失维度反而提高追溯率”；该 role
的降级会在 `degraded_fields` 和 role-level degradation 中独立记录。

### D7. dossier 质量状态由事实契约导出

`build_research_dossier` 在返回前运行事实契约：

- 存在高严重度 fail-closed 违规 → 抛出异常。
- 所有高严重度事实可追溯且 fresh/clean → `quality_status="clean"`。
- 否则（stale、降级 role、任何 degraded 事实）→ `quality_status="degraded"`，
  `quality_reasons` 列出原因。

## Risks / Trade-offs

[source 是角色级映射而非 provider 返回] → D3 只映射到已知 fetcher 渠道，不伪造
`published_at`；契约形状预留扩展，未来 fetcher 补充元数据时仅改映射表。

[report_period 缺失被误判为不可追溯] → D3 允许 `as_of` 作为时间基准；只有 source
和所有时间基准都缺失才 fail closed。

[730 天阈值过于机械] → 阈值可注入，默认仅用于区分 fresh/stale，不直接阻断，只产生
可见 degraded 状态。

## Migration Plan

- 新增模块和测试，不迁移既有 payload。
- `build_research_dossier` 只在顶层增加字段；现有调用方继续只读取
  `core_snapshot` / `research_dossier` 时行为不变。
- 若真实运行出现 fail-closed 误杀，先以事实契约原因定位 raw payload，不降低契约要求。

## Open Questions

- fetcher 未来是否直接返回 `published_at` / source metadata，并以此取代角色级映射。
