# G1 Provider Batch Adapter Decision — 2026-08-05

## Decision

`g1-provider-batch-adapter` 的工程边界已完成：provider 必须显式注册，按 provider/method/ticker set 批量调用，先生成字段级 evidence，再交给 canonical snapshot 做 fail-closed merge。

本 change 不接入 LongPort/Longbridge SDK，不执行真实网络调用，也不改变现有 `BatchFetcher`、legacy cache、ranking 或 staged screening。LongPort/Longbridge 仍只能作为后续具备授权后的 shadow candidate；当前 unavailable provider 只产生 `not_evaluated` evidence，不静默切换来源。

## Implemented boundary

- canonical ticker set、request identity、provider family、shadow/eligibility 和 batch call statistics 均显式记录。
- 多 ticker response 拆成独立 field evidence，保留 response hash、retrieved time、unit/currency/time basis 和 provenance。
- omitted ticker、provider exception、field failure、permission/rate-limit/unsupported 等状态隔离并保留 sidecar。
- eligible provider agreement 可进入 canonical record；value/unit/currency/time/freshness 冲突 fail closed。
- shadow/not-qualified evidence 保留但不能写入 production canonical value。
- snapshot writer 继续使用 run-scoped output，不触碰 legacy cache。

## Verification

在 `/Users/admin/Documents/trade-agent/.worktrees/g1-provider-batch-adapter`：

- `python3 -m pytest -q value-screener/tests/test_provider_batch_adapter.py`：12 passed
- 既有 provider qualification、provenance、canonical snapshot 边界套件合计：39 passed
- `python3 -m compileall -q value-screener`：通过
- `git diff --check`：通过
- `openspec validate g1-provider-batch-adapter --strict`：通过

## Capability boundary

这是 provider adapter/snapshot 工程 checkpoint，不是 A 股 provider qualification 结果，也不是 G1 capability pass。真实 provider coverage、字段口径、权限、限流、成本和 network evidence 仍需后续独立 child 与明确授权后验证；G1/G2/G3 capability Gate 不因本 change 自动放行。

后续 staged screening、全市场性能/成本、LongPort/Longbridge runtime probe 和 canonical consumer migration 均保持为独立工作，不在本 change 内扩 scope。

## Post-review corrections — 2026-08-05

针对独立 review 的 6 个 P1 问题，当前 worktree 已补充修复：

- snapshot 落盘 manifest 现在保留 batch method、requested ticker set、invalid ticker、provider/method call count、provider summaries 和 freshness window。
- 混合非法 ticker 会写入 `invalid_tickers`，合法 A 股仍继续执行；非 A 股不会生成伪造的 A-share provenance。
- mapping key 与 embedded ticker 不一致、重复 canonical ticker、malformed response envelope 均 fail closed 为 `invalid_value`，不能进入 canonical value。
- stale evidence 保留 `production_eligible` 作为冲突证据，但标记 `freshness_status=stale`；fresh/stale disagreement 产生 freshness conflict，canonical value 为 null，单独 stale 也不能消费。

修复后验证：adapter focused 18 passed；provider qualification、provenance、canonical snapshot 边界套件合计 45 passed；compileall 与 `git diff --check` 通过。该修复仍不代表真实 provider qualification 或 G1 capability pass。

## Second independent-review corrections — 2026-08-05

第二次独立 review 发现的 3 个 P1 与 2 个 P2 已继续修复：

- 非法 mapping key 若能解析出 embedded ticker，会绑定到该 ticker 的 `invalid_value` evidence，不再降级成 `record_not_found`。
- mapping 中的 `None`/标量条目按 ticker 隔离，合法记录继续进入 merge，不再被整批 schema error 覆盖。
- canonical 直入口对单独 stale evidence 也生成 freshness conflict；缺少 adapter freshness timestamp 标记为 `unknown`，不能消费。
- requested fields 纳入 `BatchRequest`、`request_id`、provider summary 和落盘 manifest，避免不同字段请求身份混淆。

本轮验证：adapter + canonical focused 29 passed；完整 provider qualification、provenance、canonical snapshot 边界套件合计 50 passed；compileall 与 `git diff --check` 通过。

## Third independent-review corrections — 2026-08-05

第三次独立 review 的 3 个 P1 与 1 个 P2 已修复：

- 缺失 `retrieved_at` 即使未设置 freshness window 也标记为 `freshness_status=unknown`，不能进入 production canonical。
- 无法绑定的非法 response key 及 list malformed row 转为 response-level `invalid_value`，只影响无法绑定的请求 ticker；合法记录继续处理。
- `records` list 的 malformed row 不再中止整批。
- `_fields` 容器或单字段 metadata 类型异常按 field 生成 `invalid_value` evidence，不再触发 provider-level duplicate/failure 覆盖。

本轮验证：adapter focused 25 passed；完整 provider qualification、provenance、canonical snapshot 边界套件合计 53 passed；compileall 与 `git diff --check` 通过。

## Fourth independent-review corrections — 2026-08-05

第四次独立 review 发现的 2 个 P0/P1 与 5 个边界问题已继续修复：

- 空 mapping、空 list、空 `records` 和含 “not found” 的模糊 provider exception 不再当作 `record_not_found`；统一保留为 `source_failed`，只有成功返回且明确遗漏 ticker 才使用 `record_not_found`。
- adapter/provider error reason 统一覆盖 Bearer token、`sk-*`、API key 和 URL userinfo 脱敏，evidence 与 provider summary 均不保留明文 secret。
- 任意字段的 `available + None`、缺失或非法 `retrieved_at` 都 fail closed；当前/行情类 numeric 字段也要求显式时间基准，不能因为字段是非财务字段而绕过时间合同。
- freshness reference 在一次 batch run 内固定并写入 manifest；canonical snapshot 的 source hash 保留 freshness status，直接 snapshot 入口也会为非法 freshness 生成冲突证据。
- 归一化后的重复 canonical ticker 被记录为 `invalid_value`，不重复发起请求；method/fields 输入必须是非空字符串集合；provider method call key 纳入 provider family，避免审计碰撞。

本轮验证：adapter/canonical/provenance focused 48 passed；正确项目 venv 下 full pytest `590 passed in 47.36s`；compileall 与 `git diff --check` 通过。系统 Python 因缺少 `akshare`/`pandas`/`typer` 无法完成全量收集，该环境结果不作为通过证据。

## Fifth independent-review corrections — 2026-08-05

第五次独立 review 继续修复以下状态与安全边界：

- `source_failed`、`record_not_found` 等失败 evidence 即使没有 retrieval timestamp，也保留原始失败状态、redacted reason 和 status summary；不以 `not_evaluated` 覆盖 provider failure 语义。
- `freshness_status` 只接受 `fresh`、`stale`、`unknown`；未知值转为 `invalid_value`，并进入 freshness conflict，禁止 canonical 消费。
- 脱敏对裸 Bearer/Basic/Token 只在有授权前缀或明显 secret-like value 时处理，避免把普通诊断文本如 `invalid token format`、`bearer bond endpoint` 改写；URI userinfo 覆盖通用 scheme（包括 `ftp`）。
- `tickers` 的 `None`、字符串和不可迭代输入统一返回稳定的 `ValueError`。

本轮 focused 验证：adapter/canonical/provenance `55 passed`。full pytest、compileall、`git diff --check` 需在最终复审后重新执行。
