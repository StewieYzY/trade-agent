## Why

G1 M1.2 已能生成小样本筛选结果，但还没有一个与结果 identity 绑定、可离线填写、可复盘的人工复核记录。M1.3 需要回答唯一用户问题：用户是否认可 M1.2 选出的候选股票，以及每只股票的通过/排除理由；该闭环只能记录人工判断，不能把一次复核直接升级为 G1 Capability Gate 证据。

## What Changes

- 新增 G1/M1.3 `g1-small-sample-user-review` 离线复核能力，严格消费 M1.2 JSON 产物，并可选校验对应 Markdown 产物的 run identity。
- 校验 M1.2 的 schema、artifact type、mode、provenance、canonical ticker 集合、run identity 与输入摘要；对 live/provider/production、未知字段、digest/identity 不一致和受保护输出路径 fail-closed。
- 为每只 canonical ticker 生成四个复核维度：`candidate`、`inclusion_or_exclusion_reason`、`scores_and_thresholds`、`quality_and_data`；每个维度支持 `accepted`、`question`、`problem`、`not_evaluable`。
- 生成确定性的 `<run_id>-review.json` 和 `<run_id>-review.md`，保留用户原文、问题分类汇总、阈值/误选/漏选/数据不足清单和下一步建议。
- 增加离线 CLI：`small-sample-user-review --input <m1.2-result.json> --output-dir <dir>`；同一 run 相同内容可幂等重跑，不同内容拒绝覆盖。
- 保持 `capability_status` 与 `gate_status` 诚实：template 为 `not_evidence`，显式完成的人工记录可标记为 `mvp_evidence`，始终 `gate_status=not_passed`；不改变 G1 筛选规则或上层 Gate。

## Capabilities

### New Capabilities

- `g1-small-sample-user-review`: 对 M1.2 小样本筛选结果进行绑定 identity 的逐票人工复核，并生成确定性 JSON/Markdown 记录。

### Modified Capabilities

无。M1.2 的筛选产物契约只作为输入约束引用，不修改其 requirement。

## Impact

- 新增 `value-screener/council/small_sample_user_review.py` 及 focused 行为测试。
- 最小修改 `value-screener/cli.py`，增加离线复核子命令。
- 复用标准库、`data.lib.identity` 与既有生产路径保护；不新增依赖。
- 不调用 AkShare、东财、LongPort/Longbridge、其他 provider、LLM、Scout、Council 或全局缓存，不写入 `data/cache`、`watchlist`、`debate`、live evidence 或用户根目录 WIP。
