## ADDED Requirements

### Requirement: R1 新假设实验绑定输入和运行身份

实验 SHALL 为每个 group/agent 记录 canonical ticker、run_id、dossier/source hash、prompt hash、model name、usage、raw response 和 parsed output；任何绑定不一致 SHALL fail closed。

#### Scenario: 冻结输入一致时保存可复核产出

- **WHEN** group 内所有 agent 使用同一冻结 dossier、canonical ticker 和唯一 run_id
- **THEN** 实验 SHALL 保存 per-agent metadata、raw response、parsed output 和指标报告

#### Scenario: 输入身份不一致时拒绝结论

- **WHEN** ticker、dossier/source hash 或 run_id 与 group envelope 不一致
- **THEN** 实验 SHALL 标记 group incomplete，并 SHALL NOT 计入 clean success 或根因结论

### Requirement: 实验区分输入、分发和编排分支

实验 SHALL 使用相同模型和 prompt 版本，比较角色分发、全员共享 dossier、输入错配 fail-closed 与现有编排路径。

#### Scenario: 只改变角色分发

- **WHEN** 两个 group 使用相同 ticker、dossier、model 和 prompt，仅改变角色分发策略
- **THEN** 报告 SHALL 比较显性串台、隐性串台、Jaccard、凭空数字和输入 hash

#### Scenario: 错配分支 fail closed

- **WHEN** ticker、dossier 或 run_id envelope 被替换或复用
- **THEN** 实验 SHALL 记录 mismatch 原因，并 SHALL NOT 生成 clean success

### Requirement: 实验证据不得升级为 G2 capability

实验 SHALL 将结论、evidence gap 和后续建议分开记录；fixture、单次 live run 或测试通过不得单独证明 G2 capability。

#### Scenario: 证据不足时保持 active

- **WHEN** provider-frozen dossier 不完整、调用失败或结果不可复现
- **THEN** change SHALL 保持 active，并记录缺口和下一步，不得宣称 capability passed
