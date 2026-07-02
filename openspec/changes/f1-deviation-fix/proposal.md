## Why

`design/deviation-analysis-2026-07-01.md` 的实证核查发现：L0→L4 骨架虽全落地，但两个核心架构假设零到极弱佐证——L2 成本闸门（AD-03）从未在真实候选集验证，L3 辩论信息增量（AD-09）7 次实跑仅 1 次真实产出、6 次空壳+同质化。其中 600519/600900 的 R1 输出逐字相同（含 `conviction=75`、`ROE 32%`、`可口可乐`），且 600900 是水电股却输出茅台特征——这是判定核心假设是否成立的关键反例。本 change 在动手改任何 L3 prompt 之前，先**定位根因**（代码层还是模型层）并**跑通需求 A 的全市场链路**，避免在未验证的假设上继续往上盖楼。

## What Changes

**P0 — L3 R1 同质化/串台根因定位与修复**
- 现状确认（缩减版，不搞复现仪式）：dump 600519/600900/600009 当前的 `assemble_council_features` 返回值，确认 financials_floor（pe_ttm/roe_3y/net_margin）当前是否为 None——根因已从 guard 代码推断，此步只为验证当前 cache 状态是否仍复现漏洞
- 代码核查已收窄范围：`council/llm.py` 无响应缓存层（假设 3 排除）；`council/prompt.py` 的 system prompt 与 `council/debate.py::_build_user_message` 均无 `"{other_agent} 看好"` 占位文本（假设 1 排除）；`council/features.py` 已做 `ticker.split(".")[0]` 标准化（ticker 后缀非根因）
- 当前最可能根因：`assemble_council_features` 对 600519/600900 返回空/缺字段（cache TTL 过期或 fetch 不全），guard 因缺失率 <50% 放行，模型拿空 features 后靠 system prompt 案例锚定编造——**待现状确认**
- 若根因在 features 注入：精确化 `assemble_snapshot` 的 insufficient_data guard——新增 `financials_floor = ["pe_ttm","roe_3y","net_margin"]` 财务三件套硬门槛，修复"basic 维命中、financials 维过期时缺失率 <50% 放行"的漏洞，让 L3 在数据不足时 fail-fast 报错而非拿空数据喂模型（与 review-notes #1 的 TTL 问题联动）
- 若根因在模型层：记录为已知限制，评估是否需调整 prompt 强约束（如"必须引用下方特征数据中的具体数字"）或换模型，**不在本 change 贸然改 prompt**

**P1 — 需求 A 全市场验证**
- 修 cache ticker 后缀分裂：在 CacheManager 层 normalize ticker key（统一纯 6 位数字），与 `features.py` 已有的 normalize 对齐，避免 `600519` / `600519.SH` 双目录；已有分裂目录安全迁移（先检后删，保护孤儿目录真实数据）
- 用 akshare 拉全 A 股代码列表，跑一次 `batch`（全市场采集，非 20 只手工样本）
- 跑 `screen` 看 L1 在真实分布下的漏斗比例（5000→?→?→?），验证 `industry_pe_degraded` / `input_scale` 退化标记在全市场触发面
- 跑 `scout` 看 L2 在真实候选集上的区分度（deep_dive 比例、confidence 分布），验证 AD-03 成本闸门假设
- 可能暴露 L1 阈值需校准（total-design §4.8 规划但未做）

**P1.5 — call_llm token usage 采集（方案 B）**
- 扩展 `council/llm.py::call_llm` 返回值从 `str` 改为 `(content, usage)`，采集 prompt_tokens/completion_tokens，L2+L3 调用点适配，支撑 AD-03 成本实测（≈¥0.01/只）真正落地——不再只记调用次数
- 选方案 B 而非方案 A 的理由：call_llm 签名迟早要改，现在调用点少（debate 3 处 + scout batch 1 处）一次性改完成本最低，拖着只会让后续 change 也要再适配一次，成本假设永远悬空

**不纳入本 change**（已在 deviation-analysis §2.5 关闭或暂缓）：
- P2 仓位决策语义（已关闭，L3 schema 语义正确）
- RULE.md 三层体系、前端 Streamlit、watchlist manager、张坤（第 5 agent）

## Capabilities

### New Capabilities
<!-- 本 change 不引入新 capability，全部是对已有 capability 的 delta -->
（无）

### Modified Capabilities
- `council-debate`: R1 在 features 不足时的行为从"拿空数据喂模型产出同质化幻觉"改为"fail-fast 报错"——新增 `financials_floor` 财务三件套硬门槛，修复"basic 命中、financials 过期时缺失率 <50% 放行"的漏洞；并 MODIFY `call_llm` 返回 `(content, usage)` 采集 token，避免 AD-09 gate 被空壳产出污染
- `debate-quality-gate`: 新增"R1 反向特征校验"（key_metrics 含 features 中不存在的凭空数字则拦截）+"环形引用检测"，强化 AD-09 gate；`verify_quality_gate.py` 重构为可导入模块以支持单测
- `scout-agent`: L2 在真实全市场候选集上的区分度验证 + AD-03 成本闸门假设的首次实证（依赖 `call_llm` 采集 token usage，真实测算 ¥0.01/只）
- `watchlist-aggregation`: cache ticker key normalize 统一为纯 6 位数字，消除 `600519`/`600519.SH` 双目录；已有分裂目录安全迁移（先检后删，保护孤儿目录真实数据）

## Impact

**受影响代码**：
- `value-screener/scout/input_assembly.py` — guard 段（约 338-354 行）新增 `financials_floor = ["pe_ttm","roe_3y","net_margin"]` 财务三件套硬门槛，修复"basic 命中、financials 过期时缺失率 <50% 放行"的漏洞
- `value-screener/council/features.py` — `assemble_council_features` 透传新 insufficient_data error
- `value-screener/council/llm.py` — **`call_llm` 签名变更**：从 `-> str` 改为 `-> tuple[str, dict]`，返回 `(content, usage)` 采集 token usage（方案 B，支撑 AD-03 成本实测）
- `value-screener/council/debate.py` — `call_agent`/`_call_da`/`_call_synthesizer` 适配 `call_llm` 新签名
- `value-screener/scout/batch.py` — 适配 `call_llm` 新签名，累加 usage
- `value-screener/council/verify_quality_gate.py` — 重构为可导入模块（核心校验抽成函数），新增"R1 反向特征校验"+"环形引用检测"，`verify_cost` 改为真实 token 采集
- `value-screener/data/cache/manager.py`（若存在）或 fetcher 层 — ticker key normalize + 已有分裂目录安全迁移（先检后删，保护孤儿目录真实数据）
- `value-screener/cli.py` — 可能需要 `batch` 支持全市场 ticker 列表输入

**依赖**：akshare（已有，用于拉全 A 股代码列表）

**风险**：
- P0 根因若落在模型层（DeepSeek 在空输入下的幻觉），则无法靠代码修复，需评估换模型或强约束 prompt——可能衍生新 change
- P1 全市场跑 `batch` 涉及 ~5000 只网络采集，耗时长、可能触发 akshare 限流，需分批 + 容错
- L1 阈值校准若暴露问题，可能超出本 change 范围（§4.8 是独立工作项）
- `call_llm` 签名变更扩散到 L2+L3 所有调用点（debate 3 处 + scout batch 1 处），需逐个适配 + 跑测试套件确认无回归（调用点少且清晰，风险可控）
