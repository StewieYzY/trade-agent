## Why

M0.1 已经把冻结输入转成可复核的 growth expectation diagnostic，但用户仍缺少一份把可靠事实、增长预期、风险和未知项组织成研究判断的可读草稿。M0.2 需要用一次强单 Agent 调用完成这段最小产品闭环，同时保留人工复核和正式 G2 Gate 的边界。

## What Changes

- 新增一个只消费已校验 M0.1 diagnostic artifact 和可信 dossier 的 strong single-agent Thesis draft 运行入口。
- 在调用前校验 ticker、run、dossier snapshot、profile、diagnostic digest 与输入身份一致，失败时 fail closed。
- 组装包含事实、来源、growth diagnostic、用户假设和质量状态的单 Agent 输入，并使用现有 strong LLM HTTP 客户端只调用一次。
- 复用现有 `AgentOutput` 校验，生成带 diagnostic 摘要、质量状态、风险与待验证项的草稿。
- 生成确定性的 JSON/Markdown 草稿及最小 CLI 命令，输出只写入显式目录。
- 产物标记 `capability_status=mvp_evidence`、`gate_status=not_passed`，明确需要人工复核。

## Capabilities

### New Capabilities

- `m0-strong-agent-thesis-draft`: 从已绑定的 M0.1 diagnostic 与 dossier 生成一次 strong single-agent Thesis 草稿及 JSON/Markdown 产物。

### Modified Capabilities

- 无。现有 `investment-thesis` 是未来稳定接口；本 change 只生成实验性草稿，不修改其正式要求。

## Impact

- 影响 `value-screener/council/` 下的单 Agent 输入组装、输出校验和草稿渲染代码。
- 影响 `value-screener/cli.py`，增加 provider/LLM 可控的 Thesis draft 命令入口。
- 新增 focused 测试覆盖身份绑定、单次调用、成功/拒答/失败语义、确定性渲染、目录隔离和 CLI。
- 不新增依赖，不修改 provider、Council 多轮编排、稳定 `InvestmentThesis`、G3 或正式 Capability Gate。
