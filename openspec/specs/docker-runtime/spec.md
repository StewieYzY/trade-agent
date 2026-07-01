# docker-runtime Specification

## Purpose
TBD - created by archiving change l4b-docker-run. Update Purpose after archive.
## Requirements
### Requirement: Docker compose 服务定义

系统 SHALL 提供 `value-screener/docker-compose.yml`，定义单个 `value-screener` 服务，基于仓库内 `Dockerfile` 构建。服务 SHALL 通过 `docker compose run --rm value-screener <cli-subcommand>` 执行任意 CLI 子命令，命令参数追加到镜像 ENTRYPOINT（`python cli.py`）之后。

#### Scenario: 跑 council 子命令
- **WHEN** 执行 `docker compose run --rm value-screener council --ticker 600519` 且宿主提供全部 LLM env
- **THEN** 容器启动、`python cli.py council --ticker 600519` 执行、退出后容器自动移除（`--rm`）

#### Scenario: compose 配置可校验
- **WHEN** 执行 `docker compose -f value-screener/docker-compose.yml config`
- **THEN** 命令成功退出（exit 0），无 YAML/env 解析错误

### Requirement: LLM 环境变量注入与 fail-fast

compose 服务的 `environment` SHALL 注入全部 5 个 LLM 变量：`LLM_API_KEY`、`LLM_API_BASE`、`LLM_MODEL`、`LLM_MODEL_HEAVY`、`LLM_MODEL_MODERATE`。每个变量 SHALL 使用 `${VAR:?error message}` 插值语法从宿主环境或同目录 `.env` 文件读取。

#### Scenario: 缺失必填 env 时 fail-fast
- **WHEN** 宿主未设置 `LLM_API_KEY` 且 `.env` 不含该变量，执行 `docker compose run --rm value-screener council --ticker 600519`
- **THEN** compose 在容器启动前报错退出，错误信息含变量名，不进入 LLM 调用阶段

#### Scenario: env 文件模板提交不含真实 key
- **WHEN** 检查 `value-screener/.env.example`
- **THEN** 文件含 5 个 LLM 变量的占位符与注释，不含任何真实 API key；`value-screener/.env`（若存在）SHALL 被 `.gitignore` 忽略

### Requirement: 数据卷持久化

compose 服务 SHALL 通过 bind mount 将容器内 `/app/data`、`/app/watchlist`、`/app/debate` 三个路径映射到宿主 `value-screener/data`、`value-screener/watchlist`、`value-screener/debate`。`Dockerfile` SHALL 对这三个路径声明 `VOLUME` 作为无 compose 时的兜底。

#### Scenario: 产出持久化到宿主
- **WHEN** 在容器内执行 `council --ticker 600519` 并产出 `debate/600519/{date}.md` 与 `watchlist/{date}_600519.SH.json`
- **THEN** 容器退出后，这两个文件存在于宿主 `value-screener/debate/600519/` 与 `value-screener/watchlist/` 路径，可被宿主直接读取

#### Scenario: 缓存跨容器复用
- **WHEN** 容器 A 内执行 `fetch --ticker 600519 --dim financials` 写入 `data/cache/600519/`，随后容器 B 内执行 `council --ticker 600519`
- **THEN** 容器 B 能读到容器 A 写入的缓存数据，不重新采集

### Requirement: L1 输出 stats 含退化标记

`screen_a_shares` 输出的 `stats` 对象 SHALL 包含 `industry_pe_degraded: bool` 字段：当行业 PE 中位数映射为空或覆盖样本不足时为 `true`，否则为 `false`。`stats` 对象 SHALL 包含 `input_scale: "full_market" | "subset"` 字段：当输入 ticker 数 < 300 时为 `"subset"`，否则为 `"full_market"`。这两个字段是加法式扩展，不改变现有 `stats` 字段语义。

#### Scenario: 单只输入标记 subset
- **WHEN** 调用 `screen_a_shares(["600519"])`
- **THEN** 返回的 `stats.industry_pe_degraded` 为 `true`，`stats.input_scale` 为 `"subset"`

#### Scenario: 全市场输入标记 full_market
- **WHEN** 调用 `screen_a_shares(<5000 只 ticker 列表>)` 且行业 PE 映射样本充足
- **THEN** 返回的 `stats.industry_pe_degraded` 为 `false`，`stats.input_scale` 为 `"full_market"`

#### Scenario: 字段向后兼容
- **WHEN** 下游消费者（L2 scout_batch / L4 aggregation）读取 L1 输出
- **THEN** 新增的 `industry_pe_degraded` / `input_scale` 字段不影响现有字段消费，下游不读取这两个字段时行为不变

