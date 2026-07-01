## Context

L0→L4 全部骨架已落地（6 个 archived change），代码可跑单测，但**从未在 Docker 里用真实 LLM 端到端跑通过一只票**。当前 Docker 只剩 `Dockerfile`（`python:3.11-slim` + libxml2/libxslt，能 build），缺 `docker-compose.yml` 和数据卷声明。total-design §9.1 设计了 compose 骨架但未实现。

核实现状（本 change 探索阶段完成）：

- **Docker 缺口**：无 compose → 跑 L2/L3 要手拼 `docker run -e LLM_API_KEY=... -e LLM_API_BASE=... -e LLM_MODEL_HEAVY=... -e LLM_MODEL_MODERATE=... -e LLM_MODEL=...`；无 VOLUME → `data/cache`、`watchlist/`、`debate/` 写容器内，删容器即丢。
- **L1→L2 接缝**：L2 `scout_batch` 从 L1 candidate 只读 `ticker`（`scout/batch.py:128`），L1 其余产出全被丢弃，L2 经 `assemble_snapshot(ticker)` 从 L0 自取自算。**无运行时断裂**。L1 算力未被复用、L1/L2 同源指标口径分叉（ROE 5 年 vs 3 年）属架构问题，本 change 不修。
- **L1 单只语义退化**：`compute_industry_median_pe`（`industry_mapper.py:117`）在样本数 < `MIN_INDUSTRY_SAMPLES=5` 时丢弃该行业返回空 dict（不崩）；`top_300 = candidates_with_scores[:300]`（`main.py:90`）输入 < 300 时少截（不崩）。退化不报错但下游看不见——需补 stats 标记。
- **L3→L4 接缝**：已核实对齐（`.get()` 降级 + `l3_incomplete` 标记），本 change 不动。

约束：AD-01（L3 输入不假设来自 L1/L2，可手动输入 → 支撑跳过 L1 的最小闭环验证）、AD-03（L2 是成本闸门，完整链路验证时 L1→L2→L3 必须走，不可跳）。

## Goals / Non-Goals

**Goals:**
- 补齐 Docker 运行时：`docker-compose.yml` + `VOLUME` 声明，一条 `docker compose run` 命令能带 LLM env 跑任意 CLI 子命令，产出持久化到宿主。
- 修复 L1 单只/小批语义退化的"静默"问题：补 `industry_pe_degraded` / `input_scale` stats 字段，让退化可见。
- 以两道真实实跑验证门证明端到端可跑通（最小闭环 + 完整链路）。

**Non-Goals:**
- 不修 L1→L2 架构接缝（L1 算力未复用、口径分叉）——属后续 change。
- 不做 Streamlit 前端（L5）。
- 不落地 RULE.md 三层体系。
- 不验证全天团辩论质量（L3 后续 change 的事）。
- 不做多服务编排（Redis/DB 等）——单服务足够 MVP。
- 不改 L3 council / L4 monitor / watchlist schema。

## Decisions

### 决策 1：compose 用单服务 + `command` 覆盖 ENTRYPOINT

`docker-compose.yml` 定义单个 `value-screener` 服务，复用现有 `Dockerfile`（`ENTRYPOINT ["python","cli.py"]`）。子命令通过 `docker compose run --rm value-screener <subcommand>` 传入——compose 的 `command` 字段追加到 ENTRYPOINT 后，等价于 `python cli.py <subcommand>`。

**为何不做多服务**：系统无外部依赖（无 DB/Redis，数据是文件 JSON + akshare HTTP），单服务足够。多服务编排是 L5 前端 + 后续持久化层的事。

**为何用 `run` 而非 `up`**：CLI 是一次性命令（采数、筛选、辩论），不是长驻服务。`docker compose run --rm` 每次跑完即退，`--rm` 避免容器堆积。`up` 适合长驻服务（未来的前端）。

**备选**：写多个服务（screener/scout/council 各一）→ 拒绝，三个共用同一镜像同一代码，只是命令不同，拆服务徒增冗余。

### 决策 2：LLM env 从宿主 `.env` 文件注入

compose 的 `environment` 字段列出全部 5 个 LLM 变量，值用 `${VAR}` 插值从宿主环境或 `.env` 文件读取。新增 `.env.example` 模板（含 5 个变量的占位符 + 注释，**不含真实 key**），`.env` 本身进 `.gitignore`（若未在）。

```
environment:
  - LLM_API_KEY=${LLM_API_KEY:?err}
  - LLM_API_BASE=${LLM_API_BASE:?err}
  - LLM_MODEL=${LLM_MODEL:?err}
  - LLM_MODEL_HEAVY=${LLM_MODEL_HEAVY:?err}
  - LLM_MODEL_MODERATE=${LLM_MODEL_MODERATE:?err}
```

用 `${VAR:?err}` 语法：变量缺失时 compose 直接报错退出，**fail-fast**，避免容器跑起来后 LLM 调用时才报错（浪费采数时间）。

**为何不写死在 compose**：key 不能进 git。`.env` + `${VAR}` 是 Docker 官方惯例，`docker compose run` 自动读同目录 `.env`。

**备选**：`env_file: .env` → 也行，但 `environment` + `${VAR:?err}` 能对缺失变量 fail-fast，`env_file` 静默跳过缺失变量，前者更适合"必填 env"语义。两者不互斥，可同时用，但 MVP 选 `environment` + 插值即可。

### 决策 3：三个数据卷 bind mount 到宿主同名目录

```
volumes:
  - ./data:/app/data
  - ./watchlist:/app/watchlist
  - ./debate:/app/debate
```

用 bind mount（非 named volume）——产出直接落在宿主 `value-screener/data/` 等目录，人可直接 `cat watchlist/*.json` 查看，无需 `docker cp`。

**为何不用 named volume**：named volume 由 Docker 管理，路径不透明，查看/调试要 `docker cp` 或进容器。端到端验证阶段人要反复看产出，bind mount 更顺手。后续上生产可换 named volume。

**Dockerfile 同步加 `VOLUME`**：`VOLUME ["/app/data", "/app/watchlist", "/app/debate"]`。这是无 compose 时的兜底（`docker run` 不带 `-v` 时 Docker 会持久化到匿名卷，虽不绑宿主路径但至少隔离）。compose 的 bind mount 优先级高于 `VOLUME`，两者不冲突。

**VOLUME 兜底的边界**：`VOLUME` 仅在 `docker run`（不带 `--rm`）时持久化匿名卷；`docker run --rm` 退出时会连匿名卷一并删除。本 change 主用 `docker compose run --rm`（决策1），compose 已配 bind mount 不受影响；但若有人脱离 compose 直接用 `docker run --rm`（不带 `-v`），VOLUME 兜底不生效、数据照丢。故 `--rm` 场景必须配 `-v` bind mount，不可依赖 VOLUME 兜底——VOLUME 只覆盖"裸 `docker run` 不带 `--rm`"的窄场景。

### 决策 4：L1 单只语义退化——补 stats 标记，不改逻辑

不修改 `compute_industry_median_pe` 或 `top_300` 截断逻辑（它们的不崩降级行为是合理的），只补**可见性**：

- `screen_a_shares` 输出的 `stats` 新增 `industry_pe_degraded: bool`——当 `industry_pe_map` 为空 dict 或覆盖 ticker 数 < 阈值时为 `true`。
- `stats` 新增 `input_scale: "full_market" | "subset"`——当 `len(tickers) < 300` 时为 `subset`，标记本次"top_300 截断无意义"的语境。

**为何不改逻辑**：单只/小批跑 L1 是端到端验证的用法，不是生产用法。生产是全市场 ~5000 只。强行让单只也产出有意义的行业折价锚（比如硬编码茅台的白酒行业中位 PE）是给验证场景打补丁，污染生产逻辑。补标记让退化可见即可，下游（L2/L4）目前不消费这俩字段，不影响行为。

**备选**：单只跑时直接 skip heat_filter / skip industry_pe → 拒绝，改控制流比加字段风险大，且 heat_filter 单只已核实语义完整（自参照分位），不该 skip。

### 决策 5：两道实跑验证门，分先后

**门 1（最小闭环，先做）**：`docker compose run --rm value-screener council --ticker 600519`。跳过 L1/L2，直接 L0 采数 → L3 辩论 → 写 watchlist。验证：① compose 能注入 env 跑通 ② L0 采茅台数据成功 ③ L3 用真实 LLM 产出 debate 记录 ④ `watchlist/{date}_600519.SH.json` 写出且 `final_verdict` 非 null。

为何先做这条：成本最低（~¥0.7，单 agent R1）、链路最短、隔离了 L1 语义退化变量。若这条跑不通，问题一定在 Docker/env/L0/L3，不用猜 L1。

**门 2（完整链路，后做）**：`batch` 采 ~20 只 → `screen --tickers 20.txt` → `scout --input l1.json` → 从 deep_dive 挑一只 → `council --ticker <picked>`。验证：① L1 单只/小批 stats 的 `industry_pe_degraded` / `input_scale` 标记生效 ② L1→L2 拼接（L2 只读 ticker，能消费 L1 candidates 列表）③ L2 deep_dive 列表产出 ④ 选一只走 L3。

为何要 20 只而非 1 只：给 `compute_industry_median_pe` 一点样本（虽然 20 只仍可能 < 5 同行业，但至少能触发标记逻辑），同时验证 `screen` 的 batch 路径。门 2 总成本 = 20 只 L2 ~¥2（AD-03，¥0.01/只）+ L3 全天团 ~¥20-60（AD-03，单只），可接受。

**为何不跑全市场**：5000 只采数 ~1 小时 + L2 ~¥2，端到端验证不需要这个规模，20 只足以验证接缝。

## Risks / Trade-offs

- **[Risk] bind mount 在容器内写文件权限错位**（容器 root 写宿主文件，宿主用户读不了）→ Mitigation：Dockerfile 已 `python:3.11-slim`，默认 root 用户；宿主 macOS/Linux 下 root 写的文件普通用户通常可读（同组/其他位）。若出问题，加 `user:` 字段或 `chmod`。先观察，不预防。
- **[Risk] `.env` 误进 git 泄露 key**→ Mitigation：`.env` 进 `.gitignore`（核实后补）；只提交 `.env.example`；commit 前用 `git status` 确认。
- **[Risk] 实跑验证门依赖真实 LLM key，CI 跑不了**→ Mitigation：这两道门是**手动验证**，写在 tasks.md 但标注 `manual / requires LLM env`，不纳入自动化测试。compose `config` 校验和 L1 stats 字段的单测才是自动化部分。
- **[Risk] akshare 在 Docker 内访问公网被限流**→ Mitigation：L0 已有容错链（主选+兜底），非阻塞；端到端验证失败时先 `docker compose run fetch --ticker 600519 --dim basic` 单独验证网络。
- **[Trade-off] 只补 stats 标记不改 L1 逻辑**：好处是风险低、不污染生产；代价是单只跑 L1 时 factor_scores 的行业折价锚仍为空，L2 不消费它所以无下游影响，但人看 L1 输出会觉得"分数不太对"——靠 `industry_pe_degraded` 标记解释。

## Migration Plan

无需迁移（纯新增 + 字段扩展）。回滚：删 `docker-compose.yml`、撤 Dockerfile 的 VOLUME、撤 main.py 的两个 stats 字段即可。stats 字段是加法式扩展，下游不消费，向后兼容。

## Open Questions

- `.env.example` 是否也列出可选的 `HTTP_PROXY` / `HTTPS_PROXY`？（README 提过代理配置）→ 倾向列上，注释为可选，Docker 内访问 akshare/LLM 可能需要。
- 门 2 的"从 deep_dive 里挑一只"是手动挑还是脚本挑？→ 倾向手动（验证阶段人看 L2 输出更稳），tasks 里写明手动步骤。
