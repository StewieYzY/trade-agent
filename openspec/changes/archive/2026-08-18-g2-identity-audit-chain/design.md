## Context

本 child 是 G2 umbrella 1.1 的工程合同，不是 G2 capability verdict。它把隐式调用
上下文提升为显式、不可变的 `AuditIdentity`，并让每个持久化 artifact 携带同一份
identity 和对上游 artifact 的 hash 引用。

## Design

### Canonical ticker

`data.lib.identity.canonical_ticker()` 是唯一来源。入口必须先 canonicalize，再把
canonical ticker 写入 context；下游不得从目录名、文件名、调用上下文猜 ticker。缺少、
非法或与 dossier/round/quality/final payload 不一致时抛出 `IdentityAuditError`，不写
成功 artifact。

### Run identity and bindings

入口通过 `create_audit_identity()` 生成一次 UUID4 `run_id`。下游只接收并校验 context，
不得静默生成新的 run_id。context 固定绑定：

- `canonical_ticker`
- `run_id`
- `profile_version`
- `input_hash`
- `dossier_snapshot`
- `prompt_version`
- `model_configuration`

`input_hash` 是 canonical dossier/input payload 的 SHA-256；`dossier_snapshot` 优先
消费显式 snapshot/version，没有时使用 dossier payload hash 作为不可变 snapshot
identity。model configuration 以 canonical JSON 保存并参与 context digest。

任何 supplied identity 必须先通过同一个 structural validator，才允许读取 dossier、
解析 output root、构造 run-scoped path、检查 cache 或发起模型调用。该 validator 校验
canonical ticker、单一相对路径叶子 run_id、非空 profile/snapshot/prompt version、
SHA-256 input hash 和 strict-JSON model configuration；任何绕过构造器的对象同样
fail closed。

### Audit chain

每个 artifact 结构为：

```json
{
  "schema_version": "g2-identity-audit-chain-v1",
  "artifact_type": "dossier|prompt|debate|quality_report|final_result",
  "identity": { "...": "same AuditIdentity fields" },
  "payload_sha256": "...",
  "parent_hashes": ["..."],
  "payload": {}
}
```

写入顺序固定为：

```text
canonical ticker
→ identity context
→ dossier artifact
→ prompt artifact
→ debate artifact
→ quality report
→ final result
```

每个 payload hash 由 deterministic JSON 计算；每个后续 artifact 必须引用前一阶段
artifact hash。manifest 保存完整 artifact type/path/hash 顺序、identity digest 和
生成时间。artifact 使用 exclusive create，已有路径不得被覆盖；同 ticker 同日重复
运行只能落在不同 `run_id` root。

writer 使用 run-level transaction：artifact 先写入 audit root 下的 private staging
run；只有五段 artifact 和 manifest 均完成验证后，才原子 promote 整个 run root。失败
时 abort staging run，不得在 published audit root 留下 partial chain。runtime output
root 与 audit root 不得相同，避免两个不同语义的 manifest 竞争同一文件。

### Fail closed

验证包括：ticker canonicality、identity 全字段相等、payload 内声明 ticker/run/profile/
snapshot/model 一致、parent hash 存在且顺序正确、payload hash 可重算、manifest 与
artifact path/hash 一致；`final_result` 内嵌的 published output/fallback result 也必须
携带并匹配完整 identity。任一失败抛出 `IdentityAuditError`，调用方不得写成功缓存或
发布 final result；失败本身可由上层记录为诊断 evidence。

prompt binding hash 覆盖完整 identity 与固定排序后的 prompt records。fallback debate
artifact 保存 redacted response、agent_id 与 normalized agent output；验证时必须使用
同一 deterministic parser 从 response 重建 output，或在 blocked response 场景验证
response/output 同时为空。仅有两个独立 hash 不构成 provenance binding。

### Council and fallback

Audited Council 入口使用同一个 `AuditIdentity`，并把 dossier/prompt/debate/quality/
final 五类 payload 交给 shared writer。fallback 入口若收到 identity context 必须复用
其 ticker/run/profile/snapshot/model；若未收到 context，则只在入口生成一次 context，
不得在 artifact 或 synthesis 阶段重新生成。两者使用相同 identity serializer、hash 和
fail-closed validator。

### Scope exclusions

本设计不实现 G2 1.2 的 incomplete cache 语义、不修 G2 1.3 的 crosstalk 根因、不做
dossier data-quality/growth diagnostic/A-B/InvestmentThesis 最终接口，也不改变 G2
umbrella 的 capability verdict 或 G3 runtime 放行状态。

## Verification

- 单测覆盖 context 生成、ticker/run/profile/snapshot mismatch、hash tampering、parent
  chain mismatch、exclusive write 和同日双 run 隔离。
- fallback focused tests 断言传入 identity 不被替换，错误在 LLM/artifact 前 fail closed。
- 单测覆盖 supplied identity 在任何路径解析前被拒绝、同 root 冲突、prompt binding
  篡改、fallback response/output rebinding，以及 transaction abort 不发布 partial audit
  run。
- `openspec validate --all --strict`、`compileall`、`git diff --check` 和项目 pytest
  作为 child engineering evidence；不代表 G2 capability passed。
