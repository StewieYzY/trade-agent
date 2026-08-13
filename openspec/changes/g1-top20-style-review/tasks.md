## 1. OpenSpec child 建立

- [x] 1.1 创建 `openspec/changes/g1-top20-style-review/`，含 proposal、design、tasks、specs delta。
- [x] 1.2 写明隶属 `g1-fast-personal-value-screening`、只负责 6.1/6.2、不触碰 7.x、不进入 G2、不宣称 G1 capability passed。
- [x] 1.3 `openspec validate g1-top20-style-review --strict` 通过。

## 2. RED 测试（先失败）

- [x] 2.1 pinned bundle 解析测试：合法 bundle 提取 run_id/profile_version/input_ticker_set_hash/input_tickers；缺 identity 字段或空 input_tickers 报错。
- [x] 2.2 派生绑定测试：derivation 与 pinned 的 profile_version/input_ticker_set_hash/漏斗一致时产出 Top 20；任一不一致 → not_evaluable 且无 passed。
- [x] 2.3 Top 20 数量与排序测试：候选 ≥20 取前 20 且顺序等于候选顺序；候选 <20 不凑数，阈值按实际数量。
- [x] 2.4 复核记录完整性测试：缺失/重复/rank-ticker 不匹配 → 阻断（不得出 Gate 结论）。
- [x] 2.5 标签与理由校验测试：非法 label 报错并指明 ticker；空 reason 阻断。
- [x] 2.6 Gate 阈值测试：worth=14 → passed；worth=13 → failed；失败结果不得写成 passed。
- [x] 2.7 汇总-only 输入拒绝测试：只有比例没有逐只记录 → 报错。
- [x] 2.8 evidence 内容测试：passed/failed/not_evaluable 三态 evidence 均含逐只记录、统计与 verdict；不得出现 capability passed 表述。
- [x] 2.9 运行全部 RED 测试确认失败（模块不存在，collection error）。

## 3. 最小实现（转 GREEN）

- [x] 3.1 新增 `value-screener/screener/top20_review.py`：pinned bundle 解析与校验（含 input_tickers 集合 hash 复核）。
- [x] 3.2 实现派生绑定校验与 Top 20 选择（前 20、不凑数、identity 记录）。
- [x] 3.3 实现用户复核记录校验（枚举 label、rank/ticker 匹配、非空 reason、缺失/重复阻断）。
- [x] 3.4 实现 Gate 统计与三态判定（`worth_count*10 >= n*7`）。
- [x] 3.5 实现 evidence bundle 组装与持久化（derivation / review template / gate evidence 三类产物）。
- [x] 3.6 `cli.py` 新增 `top20 derive` / `top20 finalize` 子命令（只读 pinned bundle 与复核文档，写入 evidence 目录；不改既有命令）。
- [x] 3.7 RED 测试全部转 GREEN（33 passed）。
- [x] 3.8 `top20 derive` 增加缓存温暖度预检（复用 `_check_cache_warmth`）：pinned 输入集合的 L1 缓存不完整时 exit 2 拒绝，MUST NOT 退回 provider 抓取；CLI 测试 2 例（cold 拒绝不触达 screen_a_shares / warm 放行）转 GREEN。

## 4. 真实用户 Gate 准备（实现后停止，等待用户复核）

- [ ] 4.1 用真实 pinned bundle（archive 的 `2026-08-12_7887d515.json`，SHA-256 已核对一致）与真实本地缓存执行 `top20 derive`（allow_stale，离线，无 provider/LLM 调用）。**2026-08-13 首次执行即阻断：pinned run 的 warm cache（26040 槽位）已不存在**。详见 4.5 阻断记录。
- [ ] 4.2 核对 derivation 漏斗与 pinned bundle 一致（2533/300/252），生成 `user_review_template.json` 交付用户。
- [ ] 4.3 用户逐只填写 label 与 reason 后执行 `top20 finalize`，产出 gate evidence；用户未复核前 MUST NOT 勾选 6.1/6.2。
- [ ] 4.4 真实 Gate 完成并获授权后：归档 evidence 副本与 SHA-256 索引；按结果同步 umbrella tasks 6.1/6.2（失败则记录失败证据并准备校准 child，不扩大本 child scope）。
- [x] 4.5 阻断记录（2026-08-13）：pinned run `7887d515` 的逐票候选未随 evidence bundle 归档（bundle 仅含聚合指标），且其 warm cache（5208×5=26040 槽位，`cache_warm=true`/`cache_hits=26040`）在本机已不可恢复：主 checkout `value-screener/data/cache` 仅剩 73 个 code（7 月旧数据）、其余候选缓存位置（worktree/废纸篓/Time Machine 本地快照）均无；全市场 child worktree 清理时未跟踪的 `data/cache` 随之删除。离线确定性再派生因此不可执行；不得以部分缓存重抓（会改变数据快照并触发全量 provider 调用）冒充 pinned run 的 Top 20。恢复路径需用户决定：(a) 授权一次新的受控全市场 warm-cache L1+L2 run 并将新 run 固定为产品 run（需 provider/LLM 授权、冻结输入、run ID、安全 output root）；(b) 其他用户指定路径。未授权前 6.1/6.2 保持 not started。

## 5. 验证与收口

- [x] 5.1 `value-screener/.venv/bin/python -m pytest tests/test_top20_review.py tests/test_cli_top20.py -q` 通过（35 passed）。
- [x] 5.2 `value-screener/.venv/bin/python -m pytest -q` 全量通过（859 passed, 1 skipped, 1 xfail，与基线一致）。
- [x] 5.3 `openspec validate --all --strict` 通过。
- [x] 5.4 `value-screener/.venv/bin/python -m compileall -q value-screener` 与 `git diff --check` 通过。
- [x] 5.5 独立 review：Top 20 绑定、mock/fixture 防冒充、逐只可审计、14/20 阈值、三态语义、WIP/debate/watchlist/data 无污染（见提交说明）。
- [x] 5.6 提交仅含本 child 相关文件；根目录用户 WIP 未修改未 stage；不 archive、不 merge、不 push。
