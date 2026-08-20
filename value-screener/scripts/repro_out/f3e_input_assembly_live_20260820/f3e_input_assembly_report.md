# f3e R1 输入装配/编排状态假设实验报告

> 输入：`600009.SH` provider-frozen dossier，source sha256 `f588d5bf911aefd90348d9a7d150280847b9af938bf5b06d8548a3afeb2a00c9`；未执行 provider refresh。
> 结论与 evidence gap 分开记录；本报告不宣称 G2 capability passed。

- 模式：`live`
- run_id：`f3e-live-20260820-01`
- profile_version：`g2-council-v1` / prompt_version：`council-prompt-v1`
- heavy model：`deepseek-v4-pro`

| branch | status | explicit | implicit | Jaccard_dist | grounding_unverified | input_consistency |
|---|---|---|---:|---:|---:|---:|
| role_distribution | complete | 0.0 | 0.0 | 0.6121677299308879 | 1.0 | 1.0 |
| all_shared | complete | 0.0 | 0.0 | 0.7183829138062547 | 1.0 | 1.0 |
| mismatch_fail_closed | fail_closed_ok | n/a | n/a | n/a | n/a | 0.0 |
| existing_orchestration | incomplete | n/a | n/a | n/a | n/a | 0.0 |

> `grounding_unverified` 为 `verify_r1_feature_grounding` 反向校验未通过率；
> 未通过多由单位/派生值未归一导致（如 9.34亿 vs 934000000、54% vs 0.540988、
> 77% vs 0.7698、年份 2023-2025 等），1.0 不代表全部数字凭空编造。
> 显性串台：`detect_circular_reference` 字符串命中（core_thesis 含其他 agent_id）；
> 隐性串台：core_thesis 词表采样候选率（其他/另一位/共识/也看好/大家/都看好），
> 属有界字符串检测，不等于语义排除，不升级为 hard gate。

## 错配 fail-closed

- `ticker_mismatch`: fail_closed — f3e envelope dossier content mismatch: payload hash does not match the frozen f3c dossier
- `dossier_hash_mismatch`: fail_closed — input_hash must equal dossier payload hash
- `run_id_mismatch`: fail_closed — f3e envelope rejected: run_id must be a relative path leaf
- `freeze_missing`: fail_closed — f3e envelope requires freeze.source_sha256
- `source_hash_mismatch`: fail_closed — f3e envelope source hash mismatch: expected f588d5bf911aefd90348d9a7d150280847b9af938bf5b06d8548a3afeb2a00c9, got 0000000000000000000000000000000000000000000000000000000000000000
- `dossier_content_tamper`: fail_closed — f3e envelope dossier content mismatch: payload hash does not match the frozen f3c dossier

## 编排路径对照

- 现有编排路径未产出可对照的 R1 user message（未运行或预检失败，见 evidence gaps）。

### evidence gaps
- run_debate did not complete: HTTPStatusError: Client error '402 Payment Required' for url 'https://api.deepseek.com/v1/chat/completions'
For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/402

## 边界

- 本 change 不修改主 prompt、不切换模型、不启动 G3。
- 输入错配、dossier 缺失或 run identity 不一致不计入 clean success。
- 找到明确根因后，另开独立 runtime/provider repair change；本报告不宣称 G2 capability passed。
