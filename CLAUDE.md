# trade-agent

A 股价值投资选股 + 多 agent 研判系统。

## 当前状态

L0→L4 全流程骨架已落地（`value-screener/`），6 个 OpenSpec change 全部 archived（`openspec/changes/archive/`），有真实数据缓存与 2 份 debate/watchlist 产出文件，但**端到端全天团实跑尚未验证**——现有 `debate/` 记录要么是单 agent 模式（巴菲特，R2-R4 跳过），要么四 agent 输出高度同质化（疑为测试桩或廉价模型输出），`watchlist/*.json` 7 份中 6 份的 `consensus_summary/conviction/dissent_points` 为 `null`（R4 未跑到或 L3 R1 串台/同质化 bug），1 份（600009.SH）真实完整。两个核心需求的语义已稳定（需求 B 语义澄清见 `design/deviation-analysis-2026-07-01.md` §2.5），动手前必读 `design/total-design.md`，设计未稳定的部分先讨论再动手，不要自行假设填空。

**动手前必读**：`design/total-design.md`（第一参考源）、`design/architecture-decisions.md`（AD-01 ~ AD-09）。

## Workspace 结构

| 目录 | 角色 | 状态 |
|---|---|---|
| `design/total-design.md` | **当前设计稿**（第一参考源）——第一性原理、借鉴与砍掉的范围、目标架构、分阶段实施路径、技术决策 | 持续更新 |
| `design/architecture-decisions.md` | **架构决策记录**（AD-01 ~ AD-09）——跨 change 的架构级决策，change 拆分依据，各 change 的 proposal/design 必须引用而非重复搬运 | 持续更新 |
| `design/prd-rule&case.md` | **补充 PRD**——RULE.md 分层体系 + 历史案例库设计 | 设计稿 |
| `design/deviation-analysis-2026-07-01.md` | **偏移分析**——基于文件系统实证的开发偏移记录 + 纠偏优先级（P0/P1） | 活跃（纠偏中） |
| `design/kimi-worldcup-learnings.md` | **外部借鉴分析**——Kimi 2026 世界杯报告的辩论协议设计（6 要点）+ 校准降级机制（4 要点），含渐进式原文参照 | 参考文档 |
| `value-screener/` | **已落地的实现**——L0 数据层 / L1 screener / L2 scout / L3 council / L4 monitor | 骨架完成，见下 |
| `uzi-skill/` | 借鉴资产——开源股票分析 Claude plugin（v3.9.0，可运行，独立 git 仓库） | 只读借鉴 |
| `old-archive/` | 初版产品构想草稿，已被 total-design 融合吸收 | 只读 |
| `openspec/` | 根目录 OpenSpec 工作区，`changes/archive/` 下有 6 个已归档 change | 活跃 |

> 注意：`value-screener/openspec/` 是 L0 change 建出的空壳目录（`changes/archive/` 为空），真实 change 归档在**根** `openspec/changes/archive/`，不要往 `value-screener/openspec/` 写。

## 实施现状（L0–L4）

| 层 | 模块 | 落地状态 |
|---|---|---|
| L0 数据层 | `value-screener/data/`（`fetchers/` `lib/` `cache/`） | 已落地，多 ticker 多日缓存已采 |
| L1 量化筛选 | `value-screener/screener/`（`hard_gates` `factor_scores` `anti_trap` `heat_filter` `main`） | 已落地 |
| L2 LLM 初筛 | `value-screener/scout/`（`prompt` `input_assembly` `batch` `parse` `quality`） | 已落地 |
| L3 天团辩论 | `value-screener/council/`（`agents` `debate` `prompt` `schema` `features` `llm` `calibrate` `verify_quality_gate`） | 已落地（4 agent：巴菲特/芒格/段永平/冯柳 + DA + Synthesizer），张坤留待后续。**R1 串台/同质化 bug 未修（P0）** |
| L4 监控 | `value-screener/monitor/`（`weekly` `aggregation` `diff` `catalyst` `alert`） | 已落地 |
| L3→L4 接口 | `value-screener/watchlist/*.json` | 由 `council/debate.py::_write_council_output` 直接写 JSON，无 `watchlist/manager.py` |
| 前端 | — | **未落地**，total-design §8 规划的 `frontend/`（Streamlit）未创建 |
| 部署 | `value-screener/Dockerfile` + `docker-compose.yml` | 已落地（单服务 + bind mount 三卷 + `.env` 注入 5 个 LLM env，`${VAR:?err}` fail-fast）；`docker-runtime` capability 已建。**真实端到端实跑门待手动验证**（见已知差距） |
| RULE.md 三层 | — | **未落地**，见下 |

CLI 入口：`value-screener/cli.py`（typer），子命令 `fetch` / `batch` / `cache-clear` / `screen` / `scout` / `council`（含 `--calibrate`）/ `monitor weekly|watchlist|diff|history`。测试：`value-screener/tests/`（18 个测试文件）。Docker：`docker compose -f value-screener/docker-compose.yml run --rm value-screener <子命令>`，LLM env 走 `.env`（模板 `.env.example`）。

## 已知差距（设计目标 vs 现状）

- **RULE.md 三层体系未落地**：`~/.trade-agent/RULE.md`、`value-screener/RULE.md` 均不存在，`council/prompts/*.md` 目录不存在。当前 agent prompt 内联在 `council/prompt.py` 的 `build_*_prompt()` 函数里，**没有 global→project→agent 三层拼接逻辑**（设计目标见 `design/prd-rule&case.md`，实现位置原计划 `council/prompt_builder.py` 但该文件不存在）。
- **前端未落地**：Streamlit 前端（total-design Phase 5）未创建。
- **watchlist 无 manager**：`watchlist/` 目前只有 L3 写出的产出 JSON，total-design §8 规划的 `watchlist/manager.py`（增量 diff / 历史轨迹）未实现，diff 逻辑现由 `monitor/diff.py` 承担。
- **【P0】L3 R1 串台/同质化 bug**：600519（茅台）全天团 R1 输出逐字同质化 + 环形串台（buffett→munger→duan→feng_liu→buffett）；600900（长江电力）单 agent R1 复读茅台特征（水电股输出 ROE 32%、毛利率 90%+）。根因未定位，详见 `design/deviation-analysis-2026-07-01.md` §1.2-1.3。这是 AD-09 假设存亡问题。
- **【P1】全市场从未跑过**：`data/cache/` 26 个目录全是手工挑的白马，L1/L2 从没见过全市场 ~5000 只分布。ticker 后缀分裂（纯数字 vs .SH/.SZ）需归一。详见偏移分析 §1.5。
- **端到端全天团实跑未完整验证**：600009.SH 是唯一真实完整产出（neutral + dissent + key_variables），7 份中 6 份空壳。Docker 运行时已就绪（`l4b-docker-run` change），但 P0 bug 未修前不宜大规模验证。

## 技术栈

Python 3.10+，数据层 akshare，LLM 调用走 OpenAI 兼容 HTTP API（`httpx`，`council/llm.py` + `scout/batch.py`），无 LLM 框架依赖。CLI 用 typer，测试用 pytest。

**部署与前端**（见 total-design「九、技术决策」，部分未落地）：
- Docker 容器化部署：`Dockerfile` + `docker-compose.yml` 均已有（`l4b-docker-run` change），单服务 + `command` 覆盖 ENTRYPOINT，bind mount `data`/`watchlist`/`debate` 三卷，`.env` 注入 5 个 LLM env
- MVP 前端用 **Streamlit**（纯 Python 数据看板）——未落地
- 后续如需复杂交互可迁移到 FastAPI + React

LLM 环境变量：`LLM_API_KEY` / `LLM_API_BASE` / `LLM_MODEL`（L2 轻量）/ `LLM_MODEL_HEAVY`（L3 R1-3 重度）/ `LLM_MODEL_MODERATE`（L3 R4 中度）。推理等级映射见 AD-04。

## 目标架构要点

快筛（L1 量化 + L2 LLM）和深研（L3 天团辩论）是**两条独立管线**，通过 watchlist 接口连接；L4 监控是独立层。详见 total-design「八、实施路径」。

**硬约束**：
- 借鉴 UZI 数据层（采集 / 容错 / 并发 / resume / 特征层 / 金融模型），重做决策层（agent 天团替代规则引擎）
- L2 是成本闸门（200 只全丢 L3 不可承受，AD-03）
- 实施顺序：L1+L2 先行（ROI 最高）→ L3 从单 agent 起步验证辩论增量（AD-09 gate）→ L4 最后
- 格雷厄姆在 L1 规则引擎内核，不在天团（AD-07）
- L3 输出「好不好 + 为什么 + 什么条件下改变」，是仓位决策的前置判断；用户结合自身持仓做加仓/持有/减仓/清仓决策（需求 B 语义澄清，2026-07-01）

## RULE.md 分层体系（设计目标，未落地）

Agent 的 system prompt 计划通过三层规则继承组装（见 `design/prd-rule&case.md`）：

```
~/.trade-agent/RULE.md          ← 全局投资铁律（硬约束，不可覆盖）
value-screener/RULE.md          ← 项目级规则（结构性规则 + 周期性判断）
council/prompts/*.md            ← Agent 个性化学术立场
```

设计意图：组装逻辑按 global → project → agent 顺序拼接。**全局 RULE.md 中的铁律（如「不择时」「不懂不做」）为硬约束，agent prompt 不可覆盖或违反；项目规则可提出异议但需明确论证。**

> 现状：三层均未落地，agent prompt 内联在 `council/prompt.py`。新增 RULE 三层组装属于独立工作项，不要在改 L3 prompt 时顺手塞进去。

## L3 天团辩论：不用 Multi-Agent 框架

**不需要 AgentScope / LangGraph 等框架**（见 total-design「六、6.5」、AD-05）：

- 天团辩论本质是「带上下文的串行 LLM 调用」，不是分布式多 agent 系统
- `council/debate.py` 是唯一的消息总线和状态持有者——agent 之间不直接通信
- Agent 工作区分割靠 **prompt 设计**（不同的投资哲学/关注点/角色），不是靠框架隔离
- 4 轮辩论 = `asyncio.gather` + 信息可见性控制（R1 隔离 / R2 可见他人 R1 / R3 DA 可见 R1+R2 / R4 收敛可见 R1-R3），无框架依赖
- 辩论记录 append-only 写入 `debate/{ticker}/{date}.md`，每轮结束立即写（中途崩溃可复盘）

## OpenSpec 工作流

变更走 OpenSpec 流程（根 `openspec/`）：`opsx:propose` → 实现 → `opsx:archive`。已有 6 个 archived change（L0–L4）。状态查询 `openspec list --json`。新 change 的 proposal/design 必须引用 AD 记录而非重复搬运架构决策。

## UZI-Skill 借鉴资产

进入 `uzi-skill/` 工作时以它自己的 `CLAUDE.md` / `AGENTS.md` / `ARCHITECTURE.md` 为准。

**关键模块**（借鉴时找这些）：

| 模块 | 路径 | 处理方式 |
|------|------|----------|
| 数据采集 | `skills/deep-analysis/scripts/fetch_*.py` | 借鉴模式，重新组织 |
| 特征层 | `skills/deep-analysis/scripts/lib/stock_features.py` | 直接复用（~108 标准化特征） |
| 金融模型 | `skills/deep-analysis/scripts/compute_deep_methods.py` + `lib/` | 借鉴模式 |
| Pipeline | `skills/deep-analysis/scripts/lib/pipeline/` | 借鉴三段式架构 |
| 评委规则引擎 | `skills/deep-analysis/scripts/lib/investor_criteria.py` 等 | **砍掉重做** |

## 约定

- 设计 / 讨论用**中文**；代码标识符、库 API、提交信息跟随子项目惯例
- 借鉴 UZI 模式时同步修工程债，不把脏代码带过来：
  - 两份 `run.py` → 只保留一份
  - `except Exception` 泛滥 → 收窄为具体异常类型
  - 模块级 `os.chdir` / `sys.path.insert` → 移到 `main()` 内
  - 源码搜索测试 → 不搬，后续改行为测试
- 根目录 `trade-agent/` 已在 git 跟踪下（含 `CLAUDE.md`、`design/`、`value-screener/`、`openspec/`）；`value-screener/` 不是独立 repo，跟随根

- 修改代码前，先说明计划；如果只是阅读、评审或回答问题，不需要提出修改计划
- 不要主动引入新依赖，除非明确说明原因
- 不要重构无关文件
- 涉及用户输入时，需要考虑校验和错误提示
- 修改完成后，优先运行 lint 和相关测试
- 做 review 时优先指出风险、bug、回归和缺失测试；没有发现问题时也要说明剩余风险

## 禁区

- `old-archive/` — 只读，仅供设计讨论时回溯推导过程，不要修改
- `uzi-skill/` — 除非明确要求，否则不修改；其内部改动按它自己的 commit 规范走
