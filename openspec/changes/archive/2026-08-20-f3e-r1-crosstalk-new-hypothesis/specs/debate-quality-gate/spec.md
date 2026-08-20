## ADDED Requirements

### Requirement: 输入一致性指标与检测器逃逸记录（f3e 实验性）

实验报告 SHALL 按 per-agent 记录显性串台、隐性串台、Jaccard、grounding 与输入一致性指标；ticker/dossier hash/run_id mismatch 分支 SHALL 在 LLM 调用前 fail closed，且 SHALL NOT 计入 clean success。

#### Scenario: 输入身份不一致时拒绝结论

- **WHEN** ticker、dossier/source hash 或 run_id 与实验 envelope 不一致
- **THEN** harness SHALL 在 LLM 调用前阻断并记录 mismatch 原因，报告 SHALL NOT 将该分支计为 clean success

#### Scenario: 字符串检测与语义采样分开记录

- **WHEN** 计算隐性串台候选
- **THEN** 报告 SHALL 区分 `detect_circular_reference` 字符串命中的显性串台与词表采样的隐性候选，不将采样升级为 hard gate
