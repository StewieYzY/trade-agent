# f3e existing_orchestration 单独重跑报告

- run_id: `f3e-live-20260820-02`
- 输入: `600009_frozen_dossier.json`，source sha256 `f588d5bf…a00c9`，payload sha256 `556120be…678f`
- model: `deepseek-v4-pro`
- status: `complete`

| 指标 | 值 |
|---|---:|
| R1 records | 4/4 ok |
| explicit_crosstalk_rate | 0.00 |
| implicit_crosstalk_rate | 0.00 |
| grounding_unverified_rate | 1.00 |
| citation_divergence.mean_distance | 0.79 |
| input_consistency | 1.00 |
| input_assembly_mismatches | 0 |
| evidence_gaps | 0 |

## 结论

现有 `run_debate` 编排路径在补全 `roe_3y/net_margin` 后可通过预检并完成
4 个 R1 调用；audit prompt artifact 中的 R1 user message 与直接角色分发分支
完全一致，未发现 ticker/dossier/run identity 或编排状态导致的串台。

`grounding_unverified_rate=1.0` 仍是单位/派生值未归一造成的反向校验误报
（9.34亿 vs 934000000 等），不解读为所有数字均为编造，也不升级为 G2
capability 结论。
