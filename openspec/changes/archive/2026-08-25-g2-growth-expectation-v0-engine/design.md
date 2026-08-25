## Context

G2 umbrella 3.2 依赖已归档的 `g2-growth-expectation-contract`。contract 已冻结输入单位/来源、user assumption snapshot、`clean/degraded/not_evaluable/failed` 语义、reverse mode exclusivity、provenance 和 digest binding；本 change 只实现计算，不修改 contract。当前仓库是 Python 3.10+、pytest 项目，且本 change 必须在独立 worktree 内完成。

## Goals / Non-Goals

**Goals:**

- 以 validated `DiagnosticInput` 和 `AssumptionSnapshot` 为唯一输入，完成 deterministic V0。
- 计算 EPV proxy 区间：`(earnings_basis - total_capex * maintenance_capex_ratio) / (cost_of_equity - maintenance_growth)`。
- 计算成熟期 PE 交叉锚区间：`normalized_net_profit * mature_pe`。
- 用两个锚的 min/max 形成现有经营能力价值区间，并保留锚分歧 warning，不机械平均。
- 计算 signed priced-growth value/share、固定增长率求年限、固定年限求增长率、可信增长区间、expectation gap、overdraft、sensitivity。
- 生成 frozen dataclass artifact，并通过 `validate_diagnostic_binding` 验证 identity/digest。
- 通过 TDD 覆盖正常、边界、不可解、输入失败、reverse exclusivity、sensitivity、provenance 和重复运行确定性。

**Non-Goals:**

- 不修改 `growth_expectation_contract.py` 的要求或 schema。
- 不接入 dossier、InvestmentThesis、Council、A/B harness、G1 ranking/hard gate 或 G3。
- 不调用外部数据源、LLM、网络服务或新增依赖。
- 不做完整 reverse DCF、多阶段增长、ROIC/reinvestment 建模、同行自动选择或交易建议。
- 不把 `quality_status=warning` 的 diagnostic 宣称为 G2 capability passed。

## Decisions

### 1. 纯函数 + 单一 facade

引擎提供可独立测试的数值函数，以及一个 `compute_growth_expectation_diagnostic(...)` facade。所有函数只接收已验证 contract 对象和显式 provenance；不读取全局状态、不做 I/O。选择该方案是为了确保相同输入完全复现，并让后续 dossier integration 只依赖 artifact。

### 2. 区间传播而非伪精确单点

对 maintenance capex ratio、cost of equity、mature PE 取 contract 冻结范围的边界传播：EPV 取所有合法组合的 min/max，成熟期锚取 earnings × PE 的 min/max。若 `cost_of_equity <= maintenance_growth` 的组合使 EPV 无有限解，返回 `not_evaluable`/`failed`，不使用默认折现率。

### 3. Reverse 采用有限 horizon 的显式现金流模型

以当前经营价值锚的 base midpoint 作为现有能力基线，未来高增长期每年把选定 earnings basis 按 `g` 增长，成熟期现金流/利润按 maintenance growth 进入终值，并以 cost of equity 折现。fixed growth 在 0..50 年内寻找满足市值的最小有限年限；fixed duration 在给定 duration 下对正增长率做二分求解。没有有限解时保留 machine-readable `no_finite_solution`/`solver_no_solution`。

### 4. Artifact 状态和 contract binding

适用性、输入和假设错误返回 `not_evaluable`；数值 solver 失败返回 `failed`；可计算但存在 unknown industry/非 clean source 等非阻断问题返回 `degraded`。artifact 使用新对象生成，计算后立即 canonical serialize、计算 digest，并调用 contract binding 校验。失败结果不携带任何 numeric conclusion。

### 5. Sensitivity 只在冻结 assumption bounds 内

至少覆盖 maintenance capex ratio、cost of equity、credible growth rate 和 mature PE 的边界/中值组合；每条 sensitivity 记录 assumption key、bound value 和 impact range。所有 scenario 值必须落在 contract snapshot 的范围内，避免把越界实验写入正式 artifact。

## Risks / Trade-offs

- [Risk] V0 把总资本开支按用户比例近似维护性资本开支，可能系统性低估成长公司价值 → 强制保存并展示 assumption snapshot，比例未确认或 solver 条件不满足时 fail closed。
- [Risk] EPV 与成熟期锚差异可能很大 → 输出 min/max 区间和 anchor divergence warning，不取无依据平均值。
- [Risk] reverse 求解结果受离散年度和终值设定影响 → 固定 horizon 上限 50 年、记录 formula version，并把结果限定为 diagnostic。
- [Risk] 当前 contract 的 `clean` 状态要求空 warnings 且所有 source fresh/clean → 引擎默认不伪造 clean；输入有可见降级时输出 degraded。
- [Risk] 非财务行业缺失标签时只能给 warning → contract 的 applicability 已定义 `industry_unknown`，引擎保留为 degraded，不硬阻断。

## Migration Plan

1. 在 child worktree 新增 engine 与 focused tests。
2. 运行 focused tests、全量 pytest、compileall、OpenSpec strict validation 和 diff check。
3. 完成 child-only read-only review，修复 review findings 后 archive change。
4. 将 child commit 合入 main、push `origin/main`，再删除 worktree/分支；根目录未跟踪 WIP 全程不纳入提交。

## Open Questions

- V0 的独立 engine 不决定成熟期可比公司集合；contract 只接受确认的 mature PE 区间，后续 integration/数据 child 负责来源。
- `value_pulled_forward_years` 采用 base credible growth 与 base cost-of-equity 的 diagnostic 等价年限，不代表持有期限或价格预测。
