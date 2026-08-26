## Why

G2 的 R1 grounding、R2 新证据/修订、DA 事实回查和 R4 分歧报告校验已经存在于独立函数或规范中，但正常 Council 编排仍可能在未执行这些校验、或校验结果未进入终态的情况下写出方向性结果。这样会让 warning、skip、degraded、failed 与 clean success 混淆，削弱 Investment Thesis 的可信边界。

本 change 是 G2 4.1 的唯一 child，目标是把既有质量检查接入正常主流程并建立 fail-closed 的结果发布边界，不扩展到 G2 4.2/4.3 或正式 capability 验收。

## What Changes

- 将 R1 grounding 与 R1 环形引用检查作为正常 Council R1 后置质量步骤，并把 hard failure 与 soft warning 传播到终态。
- 将 R2 `new_evidence` / `evidence_exhausted` 检查接入每个成功 R2 输出，保留 soft warning，不把缺少信息增量误报为 clean。
- 将 DA `evidence_quality_assessment`、recommendation 合法性和 skip reason 分支接入正常质量门。
- 将 R4 `divergence_level`、高分歧 `key_disagreements` 与 `calibration_status` 校验接入 Synthesizer 完成后。
- 统一根据四类检查、运行时错误率、DA skip、dossier quality 和阶段完成情况生成 G2 run-quality terminal status；污染、失败、降级或不完整结果不得成为 clean success/cache hit。
- 扩充 CouncilResult、watchlist/quality record 传播所需的可见 reasons 与 gate evidence，但不引入 G2 4.2 的完整状态持久化。
- 为正常链路、失败/降级/跳过及污染阻断补充 RED/GREEN 行为测试；所有 LLM/provider mock 同时断言调用签名和参数形状。

## Capabilities

### New Capabilities

无。该 child 只收敛现有 G2 4.1 capability 的主流程行为。

### Modified Capabilities

- `council-debate`: 正常 Council 主流程必须执行 R1/R2/DA/R4 质量检查，并传播阶段与终态状态。
- `debate-quality-gate`: 已定义的四类质量检查必须由编排器调用，hard/soft/skip 语义必须可见且可测试。
- `g2-run-quality-status`: 只有所有必需阶段完成且最终质量门 passed 才能是 complete/cache-eligible；非 clean 结果必须保留状态与原因。

## Impact

- 主要影响 `value-screener/council/debate.py`、`verify_quality_gate.py`、必要时 `schema.py` 和 `data/lib/quality_status.py`。
- 新增或调整 `value-screener/tests/` 下 Council 主流程与质量状态行为测试。
- 新增 `openspec/changes/g2-main-flow-quality-gates/` proposal、design、delta specs 和 tasks。
- 不新增依赖，不调用真实 LLM/provider，不修改 root 既有 WIP、G1、growth expectation engine、主 prompt 或 G3。
