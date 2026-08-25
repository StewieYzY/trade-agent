## Context

本 repair 基于 `g2-growth-expectation-v0-engine` 的独立 child-only review。原 engine 已合入 main，但 reverse solver 将 business-value midpoint 同时当作 earnings 与 terminal profit，且没有对 solver 输出做方程残差验证。contract 已冻结，repair 不修改 contract schema，只修 engine 的实现和测试。

## Goals / Non-Goals

**Goals:**

- 用明确的 normalized earnings basis 计算高增长期 earnings 和成熟期 terminal earnings；current-business anchor 只作为现有价值基线/target decomposition，不重复作为 earnings。
- fixed-growth 与 fixed-duration 均在有限区间内求解，并拒绝无法满足 residual tolerance 的结果。
- 对每个 sensitivity assumption 独立 perturb，输出可解释的 impact range 和覆盖字段。
- 所有 contract-valid 输入都返回合法 diagnostic 或显式 failure artifact；failure 保留 input snapshot。
- facade 生成 artifact 后立即调用 `validate_diagnostic_binding`，确保自身输出可被 contract 接受。

**Non-Goals:**

- 不修改 archived contract 或原始 change archive。
- 不引入新的依赖，不接入任何上层 G2 runtime。
- 不重做 V1 reverse DCF 或同行数据选择。

## Decisions

### 1. Reverse 的现金流基数独立于 business anchor

reverse 模型使用 `normalized_earnings_basis` 作为当前 earnings；高增长期按 `growth_rate` 增长；终值使用成熟期 `normalized_net_profit` 乘 mature PE 的交叉锚，或同一 earnings basis 的成熟期资本化 proxy。business midpoint 仅用于估计当前经营价值与市场价值的差额，不再充当现金流本身。

### 2. Solver 必须 bracket + residual

fixed-growth 在 `[0, MAX_REVERSE_DURATION_YEARS]` 检查目标是否可被包围，fixed-duration 从 `growth=0` 开始自适应扩张上界，直到找到包围或识别非有限解。二分结束后必须验证 `abs(PV-target) <= tolerance * max(1,target)`，否则返回 computation failure。

### 3. Sensitivity 使用单变量情景

每条 sensitivity 固定其他 assumptions 为 base/midpoint，只替换当前 assumption 的合法边界/中值；影响范围分别记录 current-business value、reverse base、expectation gap、overdraft rank 和 pulled-forward years。为避免二维 impact range 丢失 metric 语义，`SensitivityScenario` 增加向后兼容的 `metric` 字段，并允许三值 credible-growth assumption 进行边界绑定。

### 4. Failure artifact 保留输入但不保留 numeric conclusions

failure/not-evaluable artifact 携带 `input_snapshot=input`、assumption snapshot、provenance、input/diagnostic digest，但所有 contract 定义的 numeric conclusion 字段保持 `None`/空 tuple。负净利润等合法输入走 `data_insufficient`/`invalid_value`，不让 `CurrentBusinessValue` 构造异常泄漏。

### 5. Overdraft 分类按 credible low/mid/high

若 implied assumption <= credible midpoint，返回 `within_credible_range`；大于 midpoint 且不超过 high，返回 `above_base_case`；大于 high，返回 `above_credible_upper_bound`。fixed-growth 模式比较 fixed base growth；fixed-duration 比较 solved base implied growth。

## Risks / Trade-offs

- [Risk] 终值采用 V0 代理仍不等于完整 EPV → 明确 formula version 和 diagnostic grade，保留 V1 non-goals。
- [Risk] 自适应增长搜索可能数值膨胀 → 设置有限最大增长率/迭代次数，并以 non-finite/no-solution fail closed；该上限写入 engine 常量和测试。
- [Risk] sensitivity contract 结构不足以表达完整输出 → 不扩展冻结 contract，使用确定性的 impact range 和 scenario key，后续 contract child 再升级结构。

## Migration Plan

1. 在 repair worktree 写 RED tests。
2. 实现最小修复并运行 focused/full regression。
3. 执行独立 repair child-only review。
4. 归档 repair，合入 main、push，并清理 repair worktree/branch。

## Open Questions

- V0 仍需由后续 dossier integration 决定如何把 sensitivity 的摘要文字化给 Agent；本 repair 只保证结构和数值边界。
