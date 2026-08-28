## Why

M0.1 和 M0.2 已经能够生成带身份、来源和质量状态的单股诊断与 Thesis 草稿，但还没有记录用户是否理解、认可或质疑这些内容。M0.3 需要把一次真实人工复核保存为可追溯的反馈记录，闭合 M0 单股研究 MVP 的产品反馈环，同时明确它不是 G2 Capability Gate 证据。

## What Changes

- 新增显式输入 envelope，绑定 M0.1 growth diagnostic artifact、M0.2 Thesis draft artifact 以及 canonical ticker、run_id、dossier_snapshot、profile_version 和两份 artifact digest。
- 新增人工复核记录 schema，覆盖事实、假设、成长预期诊断和 Thesis 草稿四个维度。
- 每个复核维度允许用户填写结论状态、具体反馈、问题或修正，以及无法判断的原因。
- 新增用户填写的关键问题、认可内容、residual risk 和下一步决策字段；程序不生成或替代用户决策。
- 新增确定性的 review record JSON/Markdown validator 和 renderer，只写入显式 output directory。
- 新增最小 `single-stock-user-review` CLI 入口；缺失真实 artifact 时只支持明确标记的 fixture/模板契约测试，不伪造用户已复核。
- 产物固定标记 `artifact_type=m0_single_stock_user_review`、`capability_status=mvp_evidence`、`gate_status=not_passed`；若没有真实用户反馈则记录为 `not_evidence`，并保留待用户填写状态。

## Capabilities

### New Capabilities

- `m0-single-stock-user-review`: 校验 M0.1/M0.2 artifact 身份并保存用户人工复核、反馈、残余风险和下一步决策。

### Modified Capabilities

- 无。M0.1 growth diagnostic 和 M0.2 Thesis draft 的既有 requirements 不变，本 change 只消费其产物。

## Impact

- 新增 `value-screener/council/user_review.py`，负责输入绑定、review record schema、校验和 JSON/Markdown 渲染。
- 修改 `value-screener/cli.py`，增加显式 input/output 路径的离线 review record 命令。
- 新增 `value-screener/tests/test_m0_single_stock_user_review.py`，覆盖身份绑定、四维反馈、确定性产物、状态语义、目录隔离和 CLI。
- 不新增第三方依赖，不调用 provider、LLM、Council、DA、Synthesizer，也不修改 M0.1/M0.2 运行时。
