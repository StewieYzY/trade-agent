# trade-agent

A 股价值投资选股 + 多 agent 研判系统。当前处于**设计讨论阶段**，尚无代码落地。

## Workspace 结构

| 目录 | 角色 |
|---|---|
| `design/260623-design-v1.md` | **当前设计稿**（第一参考源）——第一性原理、借鉴与砍掉的范围、目标架构、分阶段实施路径 |
| `uzi-skill/` | 借鉴资产——开源股票分析 Claude plugin（v3.9.0，可运行，独立 git 仓库） |
| `old-archive/` | 初版产品构想草稿，已被 design-v1 融合吸收 |

**动手前必读 `design/260623-design-v1.md`**。需求细节和架构仍在深入讨论中，设计未稳定的部分先讨论再动手，不要自行假设填空。

新代码目标目录：`value-screener/`（见 design-v1「八、实施路径」，尚未创建）。

## 技术栈

Python 3.10+，数据层 akshare，LLM 调用框架待定。

## 目标架构要点

快筛（L1 量化 + L2 LLM）和深研（L3 天团辩论）是**两条独立管线**，通过 watchlist 接口连接；L4 监控是独立层。详见 design-v1「八、实施路径」。

**硬约束**：
- 借鉴 UZI 数据层（采集 / 容错 / 并发 / resume / 特征层 / 金融模型），重做决策层（agent 天团替代规则引擎）
- L2 是成本闸门（200 只全丢 L3 不可承受）
- 实施顺序：L1+L2 先行（ROI 最高）→ L3 从单 agent 起步验证辩论增量 → L4 最后

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
- `trade-agent/` 根目录目前不在 git 下

- 修改代码前，先说明计划；如果只是阅读、评审或回答问题，不需要提出修改计划
- 不要主动引入新依赖，除非明确说明原因
- 不要重构无关文件
- 涉及用户输入时，需要考虑校验和错误提示
- 修改完成后，优先运行 lint 和相关测试
- 做 review 时优先指出风险、bug、回归和缺失测试；没有发现问题时也要说明剩余风险

## 禁区

- `old-archive/` — 只读，仅供设计讨论时回溯推导过程，不要修改
- `uzi-skill/` — 除非明确要求，否则不修改；其内部改动按它自己的 commit 规范走
