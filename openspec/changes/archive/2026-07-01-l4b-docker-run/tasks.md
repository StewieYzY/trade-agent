## 1. Docker compose 与环境配置

- [x] 1.1 编写 `value-screener/docker-compose.yml`：单服务 `value-screener`，`build: .`，`ENTRYPOINT` 不改（沿用 `python cli.py`），`environment` 注入 5 个 LLM 变量用 `${VAR:?err}` 语法，`volumes` bind mount `./data:/app/data`、`./watchlist:/app/watchlist`、`./debate:/app/debate`
- [x] 1.2 编写 `value-screener/.env.example`：含 5 个 LLM 变量占位符 + 注释（标注哪些必填/选填），可选列出 `HTTP_PROXY`/`HTTPS_PROXY` 注释为可选，不含真实 key
- [x] 1.3 核实并补 `value-screener/.gitignore`：确保 `.env` 被忽略（`.env.example` 不忽略）；若已有则跳过
- [x] 1.4 `Dockerfile` 加 `VOLUME ["/app/data", "/app/watchlist", "/app/debate"]` 声明
- [x] 1.5 验证 `docker compose -f value-screener/docker-compose.yml config` 成功退出（exit 0），无解析错误

## 2. L1 单只/小批语义退化标记

- [x] 2.1 写测试 `tests/test_screener_stats.py`：`screen_a_shares(["600519"])` 返回 `stats.industry_pe_degraded == True` 且 `stats.input_scale == "subset"`（先跑确认失败）
- [x] 2.2 写测试：`screen_a_shares(<≥300 只 ticker 列表>)` 返回 `stats.input_scale == "full_market"`；行业 PE 样本充足时 `industry_pe_degraded == False`（先跑确认失败）
- [x] 2.3 写测试：下游不读取新增字段时行为不变（回归测试：L1 下游 `scout_batch` 只读 `ticker`、新增 stats 字段不改变 candidates 字段结构 → 不受影响；L4 入口 `aggregate_watchlist` 读 L1 文件时只取 candidates 列表、不读 stats → 亦不受影响）
- [x] 2.4 修改 `screener/main.py`：`screen_a_shares` 的 `stats` 加 `industry_pe_degraded`（当 `industry_pe_map` 为空 dict 或覆盖 ticker 数不足时为 true）和 `input_scale`（`len(tickers) < 300` → `"subset"`，否则 `"full_market"`）
- [x] 2.5 跑 2.1-2.3 测试确认通过；跑现有 `tests/test_screener.py` 确认无回归

## 3. Docker 构建与基础跑通（无 LLM）

- [x] 3.1 `docker compose build` 构建镜像成功（akshare 依赖装好）
- [x] 3.2 `docker compose run --rm value-screener --help` 确认 CLI 入口可用
- [x] 3.3 `docker compose run --rm value-screener fetch --ticker 600519 --dim basic` 验证 L0 在容器内能采数（akshare 公网访问 + 写入 `./data/cache`）
- [x] 3.4 确认 3.3 产出的缓存文件落在宿主 `value-screener/data/cache/600519/`，可被宿主直接读取
- [x] 3.5 验证 fail-fast：不设 `LLM_API_KEY` 时 `docker compose run --rm value-screener council --ticker 600519` 应在容器启动前报错退出

## 4. 实跑验证门 1：最小闭环（L0→L3→L4 接口）

> 手动验证，需真实 LLM env（`LLM_API_KEY`/`LLM_API_BASE`/`LLM_MODEL_HEAVY`/`LLM_MODEL_MODERATE`）。成本 ~¥0.7。

- [x] 4.1 宿主配置 `.env`（或 export 环境变量）填入真实 LLM 凭据
- [x] 4.2 `docker compose run --rm value-screener council --ticker 600519` 跑通，退出码 0
- [x] 4.3 确认宿主 `value-screener/debate/600519/{date}.md` 生成，含 Round 1 巴菲特输出
- [x] 4.4 确认宿主 `value-screener/watchlist/{date}_600519.SH.json` 生成，`final_verdict` 非 null、`key_variables` 非 null
- [x] 4.5 （可选）跑 `docker compose run --rm value-screener council --ticker 600519 --force` 确认缓存命中与重跑两条路径

## 5. 实跑验证门 2：完整链路（L1→L2→L3）

> 手动验证，需真实 LLM env。成本 ~¥2（L2 20 只）+ ~¥20-60（L3 全天团单只，AD-03）。

- [x] 5.1 准备 `tickers.txt` 含 ~20 只 A 股代码（含 600519 + 几只同行业白酒 + 跨行业样本）
- [x] 5.2 `docker compose run --rm value-screener batch tickers.txt` 采全维度数据，确认缓存写入宿主
- [x] 5.3 `docker compose run --rm value-screener screen --tickers tickers.txt --output l1.json`，确认 `l1.json` 产出且 `stats.industry_pe_degraded`/`input_scale` 标记符合预期（20 只应标 `subset`、`industry_pe_degraded` 多半 true）
- [x] 5.4 `docker compose run --rm value-screener scout --input l1.json --output l2.json`，确认 `l2.json` 产出 deep_dive 列表（L2 只读 ticker，能消费 L1 candidates）
- [x] 5.5 从 `l2.json` 的 deep_dive 列表**人工**挑选一只 ticker（不写自动挑选脚本；人看 `confidence` 与 `reasoning` 选一只走 L3）
- [x] 5.6 `docker compose run --rm value-screener council --ticker <picked>` 跑 L3，确认 debate 记录与 watchlist JSON 产出
- [x] 5.7 记录端到端验证结果（哪些接缝顺畅、哪些有异常）到本 change 的 review 笔记

## 6. 收尾

- [x] 6.1 更新 `value-screener/README.md`：补 Docker 用法小节（`docker compose run` 示例 + `.env` 配置说明），修正现有"手拼 docker run"暗示
- [x] 6.2 更新根 `CLAUDE.md` 的「实施现状」表：`docker-runtime` 落地、`docker-compose.yml` 已有、L1 stats 字段已扩展；更新「已知差距」移除已解决项
- [x] 6.3 跑全量 `pytest value-screener/tests/` 确认无回归
- [x] 6.4 `openspec validate l4b-docker-run --strict` 通过，准备 archive
