## ADDED Requirements

### Requirement: 冻结历史 R1 串台失败快照

实验 SHALL 冻结 600519.SH 与 600900.SH 历史 R1 串台失败快照，每份快照 SHALL 绑定
canonical ticker、run_id、历史输入 source hash 与快照 payload hash；任何绑定不一致
SHALL 在 LLM 调用前 fail closed。

#### Scenario: 冻结快照一致时加载成功

- **WHEN** fixture 的 canonical ticker、source hash、input snapshot 与快照 payload 均一致
- **THEN** harness SHALL 接受快照并返回冻结 envelope

#### Scenario: ticker/source hash/快照 hash/run_id 不一致时拒绝

- **WHEN** canonical ticker、source hash、快照 payload hash 或 run_id 任一被篡改或复用
- **THEN** harness SHALL 在任何 LLM 调用前 fail closed，并记录 mismatch 原因

### Requirement: fixture 回放显性串台

实验 SHALL 用历史 R1 输出回放显性串台，并调用现有 `detect_circular_reference`
确认可识别；fixture 的 signal/conviction 占位 SHALL 被显式标注，不冒充历史证据。

#### Scenario: 600519 全天团环形串台被识别

- **WHEN** 回放 buffett→munger→duan→feng_liu→buffett 的 R1 core_thesis
- **THEN** harness SHALL 标记显性串台已复现，per-agent 命中检测器

#### Scenario: 600900 单 agent 复读 munger 被识别

- **WHEN** 回放 600900 单 agent buffett 的 `munger 看好长期价值`
- **THEN** harness SHALL 标记显性串台已复现

### Requirement: dry-run 定位历史输入根因路径

实验 SHALL dry-run 验证历史 `insufficient_data` 输入在当前 `_prepare_council_input`
路径下 fail-closed，不会到达 LLM；fixture/dry-run 结论 SHALL NOT 被当作 live 复现
或 G2 capability 证据。

#### Scenario: 历史 insufficient_data 输入 fail-closed

- **WHEN** 用冻结的历史输入 error shell 走当前输入预检
- **THEN** harness SHALL 记录 `insufficient_data` fail-closed 与 `llm_reachable=false`

#### Scenario: 结论区分 fixture 与 live

- **WHEN** 生成诊断报告
- **THEN** 报告 SHALL 区分 fixture/dry-run 边界，记录 live 未授权与隐性串台残余风险，
  SHALL NOT 宣称 G2 capability passed
