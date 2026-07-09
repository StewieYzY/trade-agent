## ADDED Requirements

### Requirement: R2 新证据校验
质量门 SHALL 新增「R2 新证据」校验维度，确保 R2 不是复读 R1：

- 每个 agent 的 R2 `AgentOutput` SHALL 满足以下任一：`new_evidence` 非空，或 `evidence_exhausted == true`
- `new_evidence` 中引用的数字 SHALL 通过反向特征校验（复用 `verify_r1_feature_grounding` 逻辑）——新引用数字必须在 features 任一字段值中出现，否则标记为编造

> 背景：Kimi 辩论要点 3（每轮强制新数据证据防退化）。R2 若既无新证据又未声明穷尽，是复读，辩论无增量。

#### Scenario: R2 含新证据通过
- **WHEN** agent 的 R2 `new_evidence` 含 `"PB 1.2"`，且 features 中存在值为 1.2 的字段
- **THEN** 质量门 SHALL 标记该 R2 为「有新证据」，通过校验

#### Scenario: R2 声明证据穷尽通过
- **WHEN** agent 的 R2 `evidence_exhausted == true`，`new_evidence` 为空
- **THEN** 质量门 SHALL 标记该 R2 为「证据穷尽」，通过校验

#### Scenario: R2 既无新证据又未声明穷尽拦截
- **WHEN** agent 的 R2 `new_evidence` 为空且 `evidence_exhausted == false`
- **THEN** 质量门 SHALL 标记该 R2 为「复读 R1」，不通过校验，提示调 R2 prompt

#### Scenario: R2 新证据含凭空数字拦截
- **WHEN** agent 的 R2 `new_evidence` 含 `"ROE 50%"`，但 features 中无任何字段值为 50
- **THEN** 质量门 SHALL 标记该数据点为「凭空编造」，不通过校验

#### Scenario: 校验模块可单元测试
- **WHEN** 实现新证据校验逻辑
- **THEN** SHALL 将校验抽成可导入函数 `verify_r2_new_evidence(output: AgentOutput, features: dict) -> tuple[bool, list[str]]`，复用 `verify_r1_feature_grounding` 的数字提取与匹配逻辑

### Requirement: 分歧报告完整性校验
质量门 SHALL 新增「分歧报告完整性」校验维度，确保 R4 的 SynthesizerOutput 含结构化分歧信息：

- 全天团 R4 输出 SHALL 含 `divergence_level`（非 None）
- 当 `divergence_level` 为 `high` 或 `extreme` 时，`key_disagreements` SHALL 非空
- `calibration_status` SHALL 为 `"uncalibrated"`

#### Scenario: 分歧报告字段齐全通过
- **WHEN** R4 的 SynthesizerOutput 含 `divergence_level: "medium"`、`calibration_status: "uncalibrated"`
- **THEN** 质量门 SHALL 通过校验

#### Scenario: 高分歧缺 key_disagreements 拦截
- **WHEN** R4 的 `divergence_level: "high"` 但 `key_disagreements` 为空
- **THEN** 质量门 SHALL 不通过，提示 synthesizer prompt 未输出结构化分歧点

#### Scenario: 缺 divergence_level 拦截
- **WHEN** R4 的 SynthesizerOutput `divergence_level` 为 None
- **THEN** 质量门 SHALL 不通过，提示 synthesizer 未输出分歧等级

#### Scenario: 校验模块可单元测试
- **WHEN** 实现分歧报告校验逻辑
- **THEN** SHALL 将校验抽成可导入函数 `verify_divergence_report(syn_output: SynthesizerOutput) -> tuple[bool, list[str]]`

### Requirement: DA 仲裁事实回查校验
质量门 SHALL 新增「DA 仲裁事实回查」校验维度，确保 DA 的 `evidence_quality_assessment` 基于真实 features 比对而非纯主观：

- DA 输出 SHALL 含 `extra.evidence_quality_assessment`（非空 dict）
- DA 标注某 agent 为 `"inaccurate"` 时，SHALL 能在 DA 输出或比对中体现 features 实际值与 agent 引用值的差异
- DA 的 `recommendation` SHALL 引用真实存在的 agent_id（在 AGENT_REGISTRY 中）或为 `"no_clear_winner"`

#### Scenario: DA 含 evidence_quality_assessment 通过
- **WHEN** DA 输出 `extra.evidence_quality_assessment = {"buffett": "accurate", "munger": "moderate"}` 非空
- **THEN** 质量门 SHALL 通过此维度校验

#### Scenario: DA 缺 evidence_quality_assessment 拦截
- **WHEN** DA 输出 `extra.evidence_quality_assessment` 为空或缺失
- **THEN** 质量门 SHALL 不通过，提示 DA 未做事实回查（退化成纯文字评估风险）

#### Scenario: DA recommendation 引用不存在的 agent 拦截
- **WHEN** DA 输出 `extra.recommendation = "defer_to_zhangkun_consensus"`，但 "zhangkun" 不在 AGENT_REGISTRY
- **THEN** 质量门 SHALL 不通过，提示 recommendation 引用非法 agent_id

#### Scenario: 校验模块可单元测试
- **WHEN** 实现 DA 事实回查校验逻辑
- **THEN** SHALL 将校验抽成可导入函数 `verify_da_fact_check(da_output: AgentOutput, agent_ids: tuple[str, ...] | None = None) -> tuple[bool, list[str]]`
