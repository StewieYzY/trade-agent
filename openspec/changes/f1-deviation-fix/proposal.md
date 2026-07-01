## Why

`design/deviation-analysis-2026-07-01.md` 的实证核查发现：L0→L4 骨架虽全落地，但两个核心架构假设零到极弱佐证——L2 成本闸门（AD-03）从未在真实候选集验证，L3 辩论信息增量（AD-09）7 次实跑仅 1 次真实产出、6 次空壳+同质化。其中 600519/600900 的 R1 输出逐字相同（含 `conviction=75`、`ROE 32%`、`可口可乐`），且 600900 是水电股却输出茅台特征——这是判定核心假设是否成立的关键反例。本 change 在动手改任何 L3 prompt 之前，先**定位根因**（代码层还是模型层）并**跑通需求 A 的全市场链路**，避免在未验证的假设上继续往上盖楼。

## What Changes

**P0 — L3 R1 同质化/串台根因定位与修复**
- 先做最小复现实验：对 600519/600900 重跑 R1，dump 实际传入 LLM 的 `user_message`（features JSON）和 `system_prompt`，确认根因落在代码层（features 注入空/错）还是模型层（空输入下的幻觉）
- 代码核查已收窄范围：`council/llm.py` 无响应缓存层（假设 3 排除）；`council/prompt.py` 的 system prompt 与 `council/debate.py::_build_user_message` 均无 `"{other_agent} 看好"` 占位文本（假设 1 排除）；`council/features.py` 已做 `ticker.split(".")[0]` 标准化（ticker 后缀非根因）
- 当前最可能根因：`assemble_council_features` 对 600519/600600 返回空/缺字段（cache TTL 过期或 fetch 不全），模型拿空 features 后靠 system prompt 案例锚定编造——**待实验确认**
- 若根因在 features 注入：修 `assemble_snapshot` 的空数据检测/降级路径，让 L3 在数据不足时 fail-fast 报错而非拿空数据喂模型（与 review-notes #1 的 TTL 问题联动）
- 若根因在模型层：记录为已知限制，评估是否需调整 prompt 强约束（如"必须引用下方特征数据中的具体数字"）或换模型，**不在本 change 贸然改 prompt**

**P1 — 需求 A 全市场验证**
- 修 cache ticker 后缀分裂：在 CacheManager 层 normalize ticker key（统一纯 6 位数字），与 `features.py` 已有的 normalize 对齐，避免 `600519` / `600519.SH` 双目录
- 用 akshare 拉全 A 股代码列表，跑一次 `batch`（全市场采集，非 20 只手工样本）
- 跑 `screen` 看 L1 在真实分布下的漏斗比例（5000→?→?→?），验证 `industry_pe_degraded` / `input_scale` 退化标记在全市场触发面
- 跑 `scout` 看 L2 在真实候选集上的区分度（deep_dive 比例、confidence 分布），验证 AD-03 成本闸门假设
- 可能暴露 L1 阈值需校准（total-design §4.8 规划但未做）

**不纳入本 change**（已在 deviation-analysis §2.5 关闭或暂缓）：
- P2 仓位决策语义（已关闭，L3 schema 语义正确）
- RULE.md 三层体系、前端 Streamlit、watchlist manager、张坤（第 5 agent）

## Capabilities

### New Capabilities
<!-- 本 change 不引入新 capability，全部是对已有 capability 的 delta -->
（无）

### Modified Capabilities
- `council-debate`: R1 在 features 不足时的行为从"拿空数据喂模型产出同质化幻觉"改为"fail-fast 报错或显式降级标记"，避免 AD-09 gate 被空壳产出污染
- `debate-quality-gate`: 新增"R1 输出必须引用 features 中的具体数据点"的校验维度（区分真实产出 vs 空输入幻觉），强化 AD-09 gate
- `scout-agent`: L2 在真实全市场候选集上的区分度验证（AD-03 成本闸门假设的首次实证）
- `watchlist-aggregation`: cache ticker key normalize 统一为纯 6 位数字，消除 `600519`/`600519.SH` 双目录

## Impact

**受影响代码**：
- `value-screener/council/features.py` — `assemble_council_features` 的空数据检测/降级
- `value-screener/scout/input_assembly.py` — `assemble_snapshot` 返回值语义（与 features 联动）
- `value-screener/council/verify_quality_gate.py` — 新增"引用真实特征"校验维度
- `value-screener/data/cache/manager.py`（若存在）或 fetcher 层 — ticker key normalize
- `value-screener/cli.py` — 可能需要 `batch` 支持全市场 ticker 列表输入

**依赖**：akshare（已有，用于拉全 A 股代码列表）

**风险**：
- P0 根因若落在模型层（DeepSeek 在空输入下的幻觉），则无法靠代码修复，需评估换模型或强约束 prompt——可能衍生新 change
- P1 全市场跑 `batch` 涉及 ~5000 只网络采集，耗时长、可能触发 akshare 限流，需分批 + 容错
- L1 阈值校准若暴露问题，可能超出本 change 范围（§4.8 是独立工作项）
