## MODIFIED Requirements

### Requirement: 校准测试
校准测试 SHALL 验证各 agent 对已知股票的判断是否符合设计预期：

**巴菲特（3a 已实现）**：
- 看多：`600519.SH`（贵州茅台）→ `signal == "bullish"`
- 看空：`600900.SH`（长江电力）→ `signal != "bullish"`

**段永平（3b 新增）**：
- 看多：`600519.SH`（贵州茅台，§6.6 案例）→ `signal == "bullish"`

**芒格/冯柳**：
- TODO：校准用例待补充（开发阶段从蒸馏库提取），标 `# TODO: calibration case pending`，不阻塞 3b
- 张坤留给后续迭代（蒸馏素材和校准用例均不足）

**DA/synthesizer（3b 新增）**：
- 无 signal 断言（它们不是立场型 agent）
- DA：跑 1 只真实票（600519.SH），验证输出 schema 合法 + `extra.blind_spots` 非空
- Synthesizer：跑 1 只真实票（600519.SH），验证输出 schema 合法 + `dissent_points` 非空

校准测试 SHALL 调用 `assemble_council_features` 取真实特征数据，不 mock。

#### Scenario: 巴菲特校准通过（3a 已实现）
- **WHEN** 运行巴菲特校准测试（茅台/长江电力）
- **THEN** SHALL 输出 "Calibration PASSED" + 每个用例的 signal/conviction

#### Scenario: 段永平校准通过（3b 新增）
- **WHEN** 运行段永平校准测试（茅台）
- **THEN** SHALL 验证 `signal == "bullish"`，输出通过/失败状态

#### Scenario: DA 校准验证 schema（3b 新增）
- **WHEN** 运行 DA 校准测试（600519.SH）
- **THEN** SHALL 验证输出 schema 合法 + `extra.blind_spots` 非空，不断言 signal 值

#### Scenario: Synthesizer 校准验证 schema（3b 新增）
- **WHEN** 运行 Synthesizer 校准测试（600519.SH）
- **THEN** SHALL 验证输出 schema 合法 + `dissent_points` 非空，不断言 signal 值

#### Scenario: 校准失败（已实现）
- **WHEN** 运行校准测试且某用例立场不一致
- **THEN** 输出 "Calibration FAILED" + 失败用例详情，退出码非零

#### Scenario: 芒格/冯柳校准 TODO（3b 新增）
- **WHEN** 运行全天团校准
- **THEN** 芒格/冯柳 SHALL 标 `# TODO: calibration case pending`，不阻塞测试
