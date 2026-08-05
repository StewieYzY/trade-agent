## Why

当前 canonical snapshot 已具备 immutable boundary，但还没有一个批量 provider adapter 将同一批 ticker 的 provider evidence 送入 snapshot。若继续逐股调用 fetcher 或采用 first-non-empty 合并，会放大限流风险并把 provider 差异隐藏成伪成功。

## What Changes

- 新增批量 provider adapter 接口，按 provider/method/dimension 批量请求 ticker 集合。
- 统一把批量返回转换为字段级 provenance/status evidence。
- 对多 provider 同字段执行显式 merge：保留全部证据，冲突不自动覆盖或平均。
- 单 ticker、单字段或单 provider 失败不阻断其他 ticker；失败状态进入 sidecar。
- LongPort/Longbridge 只能以 shadow provider 运行，不能写入 production canonical value。
- adapter 输出接入现有 canonical snapshot writer，但不改 ranking、staged screening 或 G1 Gate。

## Capabilities

### New Capabilities

- `g1-provider-batch-adapter`: 以批量、可审计、字段级和 fail-closed 方式将 provider evidence 送入 canonical snapshot。

### Modified Capabilities

无。本 change 新增 adapter boundary，不修改现有 fetcher 或筛选 requirement。

## Impact

- 新增 `data/lib` adapter/merge 模块和 deterministic tests。
- 复用 `provider-contract-and-provenance` 与 `g1-canonical-snapshot-sync` 的 contract。
- 不新增依赖；provider SDK/credentials 通过显式注入，不写入仓库。
- 现有 `BatchFetcher` 保持兼容，后续 staged runtime 再决定是否切换消费路径。
