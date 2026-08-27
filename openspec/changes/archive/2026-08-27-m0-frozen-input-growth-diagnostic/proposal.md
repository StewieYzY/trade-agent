## Why

M0.1 是 G2 深研、M0 单股研究 MVP 的第一个 child。现有
`growth_expectation_diagnostic` contract 和确定性 engine 已存在，但缺少一个
只消费显式冻结 input bundle 的可运行入口，无法让用户复核输入身份、用户确认假设、
诊断状态和可读产物。

## What Changes

- 新增版本化 frozen input bundle envelope，绑定 canonical ticker、`run_id`、
  `dossier_snapshot`、`profile_version`、`DiagnosticInput` 和 `AssumptionSnapshot`。
- 新增最小 Python adapter/orchestrator：显式解析、校验 bundle，调用现有
  `compute_growth_expectation_diagnostic()`，再次执行 artifact binding 校验。
- 输出确定性的 JSON envelope 和人类可读 Markdown，输出目录由调用方显式传入。
- 提供 `growth-diagnostic` CLI 命令；只读取 `--input`，不调用 provider 或 LLM。

## Scope Boundary

本 change 只覆盖“冻结输入 → growth diagnostic”。它不生成 Investment Thesis，
不代表 G2 Capability Gate 通过，不修改 G2 umbrella 的 Gate 结论，也不实现
M0.2、M1、M2、M3 或 G3。产物是 `capability_status=mvp_evidence`，不是正式
Capability Gate evidence。

## Non-Goals

- 不调用 AkShare、东财、LongPort、Longbridge 或任何 provider。
- 不调用真实 LLM、Council 或 fallback。
- 不修改现有 growth expectation contract/engine 的既有语义。
- 不生成 `business_quality`、`view_signal`、`investment_eligibility`、目标价或交易指令。
- 不开发前端、数据库、任务队列、holding runtime 或自动交易。
