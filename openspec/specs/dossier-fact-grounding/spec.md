# dossier-fact-grounding Specification

## Purpose
为 dossier 角色事实定义字段级来源追溯、时间基准、新鲜度、降级状态和高严重度凭空数字 fail-closed 契约。

## Requirements

### Requirement: 字段级事实契约词汇
系统 SHALL 为 dossier 角色事实定义关闭的字段级事实契约。每条事实记录 SHALL 至少包含
`role`、`fact_key`、`label`、`value`、`severity`、`source`、`report_period`、
`published_at`、`retrieved_at`、`freshness` 和 `degradation_status`，并派生
`traceable`。`severity` SHALL 只能为 `high`、`medium` 或 `low`；`freshness` SHALL 只能为
`fresh`、`stale` 或 `unknown`；`degradation_status` SHALL 只能为 `clean`、
`degraded` 或 `unavailable`。未知取值 MUST fail closed。

#### Scenario: 未知 severity 被拒绝
- **WHEN** 事实构造器收到不在关闭词汇中的 severity
- **THEN** 系统 MUST 抛出契约错误，不生成事实记录

#### Scenario: 每条事实保存来源与时间字段
- **WHEN** 系统从 dossier 提取一个关键事实
- **THEN** 记录 SHALL 同时保存 source、report_period、published_at、retrieved_at 和
  freshness，缺失的字段 SHALL 保存为显式 null，不静默填空

### Requirement: 角色事实提取与可复核追溯率
系统 SHALL 从 `main_business`、`peers`、`research` 和 `capex_proxy` 的可用 payload 中
提取关键事实，并输出可复核统计口径：`total_fact_count`、`traceable_fact_count`、
`traceable_ratio`、`high_severity_fact_count`、`high_severity_untraceable_count`、
`stale_fact_count` 和 `degraded_fact_count`。追溯率 SHALL 只统计 raw payload 中实际
出现的事实，未获取的 role 不计入分母，并应单独记录 role-level degradation。

#### Scenario: 追溯率统计只统计已出现事实
- **WHEN** peers 或 research 未成功获取
- **THEN** 其缺失维度 SHALL 不进入 fact 分母，但 SHALL 记录为 role degradation，
  不允许靠缺失维度抬高追溯率

#### Scenario: 可追溯事实
- **WHEN** 一条事实有 source 且 report_period 或 as_of 至少一个存在
- **THEN** 该事实 SHALL 标记 `traceable=true`

### Requirement: 高严重度事实 fail closed
高严重度事实 SHALL 至少覆盖主营营收、营收占比、毛利率、同行平均估值、研报一致预期
盈利和研报目标价、资本开支代理最新值。任一已出现的高严重度数字若 source 缺失、
report_period/as_of 缺失、值非有限数字，或 raw payload 声明的 code 与请求 ticker
不一致，系统 MUST fail closed，禁止该事实进入 clean dossier。

#### Scenario: 高严重度数字无来源
- **WHEN** dossier 中出现影响核心判断的高严重度数字，但无法定位来源或时间基准
- **THEN** 系统 MUST 抛出契约错误，不返回 clean dossier

#### Scenario: 来源与数字不匹配
- **WHEN** 高严重度数字来自一个 code 与请求 ticker 不一致的 payload
- **THEN** 系统 MUST 判定为不匹配并 fail closed

#### Scenario: 非阻断诊断模式导出 failed
- **WHEN** 调用方以 `fail_closed=False` 评估同一事实契约
- **THEN** 契约 SHALL 标记 `failed=true` 且保留高严重度不可追溯事实，MUST NOT 抛异常

### Requirement: stale 与降级不得伪装 clean evidence
stale 事实、降级 role 或任何非 clean 事实 SHALL 使事实契约的 clean 判定为 false，并
输出可见的 `quality_reasons`。系统 MUST NOT 把这些证据表示为 clean evidence。

#### Scenario: stale 事实可见
- **WHEN** 一条事实的时间基准年龄超过新鲜度阈值
- **THEN** 其 `freshness` SHALL 为 `stale`，契约 clean SHALL 为 false，reason SHALL
  保留 stale 说明

#### Scenario: 降级 role 可见
- **WHEN** peers 或 research fetch 失败
- **THEN** 该 role 的 degradation SHALL 在事实契约和 quality_reasons 中可见，
  MUST NOT 被静默吞掉
