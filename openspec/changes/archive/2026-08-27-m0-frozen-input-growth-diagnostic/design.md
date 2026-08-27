## Context

G2 的 growth expectation contract 已冻结输入来源、报告期、单位、假设快照、
失败语义和 digest；V0 engine 已实现 EPV proxy、成熟期估值锚、两种 reverse
模式和敏感性分析。M0.1 需要把这些能力接成一个可复现的单股入口，但不应另造
`DiagnosticInput` 或 `AssumptionSnapshot` schema，也不应把 MVP 产物升级为 Thesis
或 Gate 证据。

## Goals

- 只从显式 JSON bundle 读取输入。
- 在任何计算前验证 bundle envelope、ticker 和 run identity。
- 复用现有 validators、engine、digest 和 binding 逻辑。
- 为 clean/degraded/not_evaluable/failed 产物提供确定性 JSON/Markdown。
- 不把 failure 或 not_evaluable 转成数值结论。

## Non-Goals

- provider、LLM、Council、fallback、dossier integration、InvestmentThesis、前端、
  数据库、任务队列、G3 或 G2 Gate。
- 修改现有 engine/contract 语义；若发现其直接阻塞 adapter，应另开 repair。

## Design

### Bundle envelope

Bundle schema 为 `m0-frozen-growth-diagnostic-bundle-v1`，字段为：

```json
{
  "schema_version": "m0-frozen-growth-diagnostic-bundle-v1",
  "canonical_ticker": "600519.SH",
  "run_id": "m0-run-001",
  "dossier_snapshot": "dossier-v1",
  "profile_version": "profile-v1",
  "diagnostic_input": {},
  "assumption_snapshot": {}
}
```

`canonical_ticker` 必须与 `diagnostic_input.ticker` 一致；`run_id` 必须是非空
相对路径叶子，不能包含 `/`、`\`、`.` 或 `..`。adapter 通过现有
`validate_diagnostic_input()` 与 `validate_assumption_snapshot()` 构造两个已验证
对象，不复制其字段校验。

### Execution and artifacts

`run_frozen_input_growth_diagnostic(bundle, output_dir)` 执行：

1. 解析并校验 envelope；
2. 调用 `compute_growth_expectation_diagnostic()`；
3. 用 `validate_growth_expectation_artifact()` 校验 identity、digest 和计算结果；
4. 生成 envelope JSON 与 deterministic Markdown。

JSON envelope 携带 `artifact_type`、artifact schema、bundle identity、
`capability_status=mvp_evidence`、`gate_status=not_passed` 和完整 `diagnostic`
对象。Markdown 固定章节展示状态、输入 provenance、用户假设、核心诊断、
warnings/reasons 和“当前无法证明的结论”。不写 `generated_at`。

### Failure boundary

结构非法、ticker 不一致和 identity 不一致直接 fail closed，抛出 adapter error，
不产生半成品文件。模型不可用时由现有 engine 产生 `not_evaluable`；计算异常或
无有限解由现有 engine 产生 `failed`。两者均保留状态、原因、provenance、
`input_digest` 和 `diagnostic_digest`，且不含数值诊断结论。

### CLI

新增 `growth-diagnostic` 命令，参数为 `--input` 和 `--output-dir`，默认输出
文件名由 adapter 固定。命令只负责读取文件和报告路径，不初始化 provider/LLM。

## Verification

测试使用 `tmp_path`，覆盖两种 reverse 模式、digest 稳定性、来源/报告期/单位/
假设快照保留、失败语义、identity mismatch、输出路径隔离、JSON/Markdown 生成和
CLI help。验证使用项目现有 Python 环境、focused pytest、相关回归、compileall、
OpenSpec strict 和 `git diff --check`。
