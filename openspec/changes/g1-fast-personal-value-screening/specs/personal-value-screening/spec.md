## ADDED Requirements

### Requirement: 个人价值风格筛选能力边界
系统 SHALL 将 G1 定义为：按版本化的用户个人价值投资规则，从当前可交易 A 股范围形成可解释、可复核、值得进入 G2 的候选池。系统 MUST NOT 将 G1 结果表达为短期涨跌预测、收益承诺或直接买入指令。

#### Scenario: 候选被解释为研究对象
- **WHEN** 某股票进入 G1 shortlist
- **THEN** 输出 SHALL 表达其“符合当前个人价值风格且值得进一步研究”，并 MUST NOT 表达为“未来必涨”或“应立即买入”

#### Scenario: 候选不足时不凑数
- **WHEN** 满足当前规则的股票少于目标展示数量
- **THEN** 系统 SHALL 返回实际满足数量，并 MUST NOT 通过临时降低门槛补足名单

### Requirement: 版本化筛选规则与运行身份
每次 G1 运行 SHALL 记录唯一 `run_id`、canonical ticker、输入数据快照标识和 `ScreeningProfile` 版本。规则或阈值变化 MUST 产生可区分的新版本。

#### Scenario: 相同规则运行可追溯
- **WHEN** 用户查看任一候选或排除结果
- **THEN** 系统 SHALL 能定位该结果使用的 `run_id`、ticker、输入快照和 ScreeningProfile 版本

#### Scenario: 阈值变化形成新版本
- **WHEN** hard exclusion、权重或 L2 threshold 任一发生变化
- **THEN** 后续运行 SHALL 使用新的 ScreeningProfile 版本，且 MUST NOT 覆盖旧版本证据

### Requirement: 数值与量纲正确性
所有影响 G1 排序或 Gate 的财务指标 SHALL 使用明确且一致的单位、分母和报告期。DCF、ROE、F-Score、PE、PB 等关键指标存在量纲不确定或无效值时，系统 MUST 阻止该值参与排序并显式标记原因。

#### Scenario: DCF 每股口径未验证
- **WHEN** DCF 输出无法证明企业价值到每股价值的换算口径、净债务和总股本处理正确
- **THEN** 该 DCF 值 MUST NOT 进入 L1 排序或 hard gate，并 SHALL 标记为 unavailable 或 non-decision

#### Scenario: 非法分母不污染排序
- **WHEN** 关键指标的分母为零、缺失或单位不一致
- **THEN** 系统 SHALL 将该指标记为 invalid/degraded，并 MUST NOT 将其静默转换为正常高分或低分

### Requirement: G1 与 G2 分层采集边界
G1 全市场路径 SHALL 只采集完成 L1/L2 所需的轻量维度，并按漏斗阶段缩小后续采集集合。`main_business`、`peers`、`research` 等 G2 dossier 维度 MUST NOT 由 G1 默认全市场采集。

#### Scenario: L1 全市场运行不采集 G2 维度
- **WHEN** 执行 G1 L1 全市场筛选
- **THEN** fetch plan SHALL 不包含 `main_business`、`peers` 或 `research`

#### Scenario: 漏斗逐层缩小采集集合
- **WHEN** 某股票在前一层 hard gate 被排除
- **THEN** 系统 SHALL 不再为该股票执行仅供后续筛选层使用的采集步骤

### Requirement: 完整漏斗与失败结果
G1 SHALL 为每只输入股票生成最终分类 `deep_dive`、`watch`、`skip` 或 `error`，并保留经过阶段、关键理由、降级状态和失败信息。shortlist MUST 由全量结果派生。

#### Scenario: 非 shortlist 股票仍可审计
- **WHEN** 某股票未进入 shortlist
- **THEN** 用户 SHALL 仍能查看其 `watch`、`skip` 或 `error` 分类及对应原因

#### Scenario: 单股失败不阻断整批
- **WHEN** 单只股票采集、特征计算或 L2 调用失败
- **THEN** 整批运行 SHALL 继续，失败股票 SHALL 进入 `error`，且未处理异常数量 MUST 为 0

### Requirement: 规模、数据质量、性能与成本 Gate
G1 在宣称全市场能力成立前 MUST 先通过不少于 300 只多行业样本验证，再完成一次真实全市场运行。全市场 warm-cache L1+L2 SHALL 在 15 分钟内完成，关键字段可用率 SHALL 不低于 95%，全市场 L2 成本 SHALL 不超过 ¥2。

#### Scenario: 300 只之前不得宣称全市场成立
- **WHEN** 系统只在少于 300 只或单一行业样本上验证
- **THEN** G1 capability status MUST 保持未通过，且 MUST NOT 宣称已具备全市场筛选能力

#### Scenario: 全市场运行满足工程 Gate
- **WHEN** 对当期完整可交易 A 股集合执行 warm-cache L1+L2
- **THEN** evidence SHALL 显示总耗时不超过 15 分钟、关键字段可用率不低于 95%、L2 成本不超过 ¥2，且 deep_dive/watch/skip/error 数量之和等于输入总数

### Requirement: Top 20 个人风格验收
G1 最终产品 Gate SHALL 包含用户对固定版本运行 Top 20 的逐只人工复核。至少 70% 的 Top 20 MUST 被用户判断为“值得进一步研究”，并保留判断标签与理由。

#### Scenario: 达到候选价值门
- **WHEN** 用户完成同一 run 和 ScreeningProfile 版本的 Top 20 复核
- **THEN** 至少 14 只 SHALL 被标记为“值得进一步研究”，并保留逐只理由

#### Scenario: 未达到候选价值门
- **WHEN** Top 20 中少于 14 只被判断为值得进一步研究
- **THEN** G1 capability status MUST 保持未通过，并 SHALL 通过新的 child change 调整数据、规则或阈值后重新验证

### Requirement: Umbrella 与 child change 治理
本 capability SHALL 作为 G1 umbrella charter 管理。运行时代码变更 MUST 由独立 child change 实现；每个 child change MUST 引用 `g1-fast-personal-value-screening` 并说明推进的 Gate 指标。Umbrella MUST NOT 仅因 artifacts 完整、tasks 勾选或自动化测试通过而标记能力完成。

#### Scenario: child change scope 合格
- **WHEN** 创建一个 G1 实现里程碑
- **THEN** proposal SHALL 引用本 umbrella、只覆盖一个可独立验证的里程碑，并明确对应的 Gate 与证据

#### Scenario: G1 放行 G2
- **WHEN** 所有必要 child changes 已归档且数值、分层采集、规模、性能、成本、完整漏斗和 Top 20 Gate 均有真实证据通过
- **THEN** G1 SHALL 标记为 capability passed，并允许进入 G2 正式能力验收
