## ADDED Requirements

### Requirement: R1 输入装配与身份绑定实验契约（f3e 实验性）

R1 新假设诊断实验 SHALL 通过独立 harness 固定 canonical ticker、run_id、dossier/source hash、system/user prompt hash、model、raw response、parsed output 与 usage；角色分发、全员共享、现有编排路径 SHALL 使用同一 prompt 与 model 版本对照，任何绑定不一致 SHALL fail closed。

#### Scenario: 角色分发与全员共享仅改 user message 装配

- **WHEN** 两个实验分支使用相同 ticker、dossier、model 和 system prompt，仅改变 user message 装配策略
- **THEN** harness SHALL 记录 per-agent user message sha256，并分别标记 `role_distribution` 与 `all_shared`

#### Scenario: 现有编排路径与直接调用对照

- **WHEN** harness 通过 `run_debate` 运行现有编排路径
- **THEN** harness SHALL 记录 R1 parsed output 与 audit prompt artifact，并对照直接调用分支的 user message hash；若 raw response 不可得，SHALL 记录 evidence gap 而非标记 clean complete
