# Proposal: bootstrap-data-layer

## 问题

trade-agent 需要从 UZI-Skill 中剥离可复用的数据层资产到新 repo，为后续 L1/L2/L3/L4 提供数据采集、特征工程、缓存管理的基础设施。UZI 的数据层有成熟的工程模式（22 维 fetcher + 三级容错 + wave 并发 + dim 级 resume），但存在严重工程债（285 个 except Exception、模块级副作用、两份 run.py），直接照搬会把脏代码带入新系统。

## 目标

从 UZI 借鉴设计模式到新 repo `value-screener/`，同时修复最脏的工程债，建立干净的数据层骨架：

1. **fetcher 模块**：5 个维度（basic/financials/kline/valuation/risk），每个维度独立容错链
2. **特征工程层**：stock_features.py 直接复用 + 新增 F-Score 九项组装
3. **缓存管理**：dim 级缓存 + 6 档 TTL + resume 机制
4. **批量采集 wrapper**：batch_fetcher.py 封装并发控制
5. **工程债清零**：收窄 except Exception、消除模块级副作用、单入口 cli.py

## 架构决策引用

- **AD-01**：数据层必须支撑 L1/L2 独立运行——fetcher/features 模块可被 L1 直接消费，不依赖 L3/L4
- **AD-03**：数据层零 LLM——fetcher 是纯数据采集，不调用任何模型

## 边界

**IN**：
- `data/fetchers/{basic,financials,kline,valuation,risk}.py`（含容错链）
- `data/lib/{stock_features,market_router,fin_models,data_sources,batch_fetcher}.py`
  - `fin_models.py` change 0 只做简化 DCF（`compute_simple_dcf`），完整版 DCF/LBO/Comps/三表预测 OUT 到 L3 change
- `data/cache/`（dim 级 + 6 档 TTL）
- `Dockerfile`（base 镜像 + 核心依赖：akshare/httpx/pydantic/typer）
- `cli.py` 骨架（data 子命令入口）
- `requirements.txt`

**OUT**：
- `screener/`（L1 选股引擎 → change 1）
- `scout/`（L2 LLM 初筛 → change 2）
- `council/`（L3 天团深研 → change 3a/3b）
- `monitor/`（L4 监控 → change 4）
- `watchlist/`（watchlist 管理 → 后续 change）
- `frontend/`（Streamlit 前端 → change 5）
- `prompt_builder` + RULE.md 三层体系（→ change 3a）
- `docker-compose.yml` 完整版（Ollama/Redis → 后续 change）
- `fin_models.py` 完整版 DCF/LBO/Comps/三表预测（→ L3 change，change 0 只做简化 DCF）

**关键边界**：fetcher 模块本身 + 其容错链 = change 0；用 fetcher 做「全市场快照→批量→治理」的筛序编排（§4.7.1）= change 1

## 依赖

无上游依赖。本 change 是 change 链路起点。

## 风险

- **东财接口限流**：`stock_zh_a_spot_em()` 在 Docker 内 IP 固定易被限流，需实现 §4.7.2 容错链（主选 + 兜底 1）
- **UZI 代码质量**：直接复制会引入工程债，必须在借鉴时同步修复
- **akshare 版本漂移**：依赖 akshare 的接口可能随版本变更，需在 requirements.txt 中锁定版本
