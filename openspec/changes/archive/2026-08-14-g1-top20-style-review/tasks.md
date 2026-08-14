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

## 4. 真实用户 Gate

- [x] 4.1 使用用户授权的新受控 pinned run `b4862934-907a-441a-9503-8fbc2c3f57e4` 执行 `top20 derive`（`allow_stale`、离线派生、无 provider/LLM replay），产物见 `evidence/2026-08-14_b4862934/top20_derivation.json`。
- [x] 4.2 核对 derivation 漏斗与 pinned bundle 一致（5208/2545/300/250），生成 `user_review_template.json` 交付用户。
- [x] 4.3 用户完成 20 只逐条复核并填写 label、confidence、reason；执行 `top20 finalize` 产出 `top20_gate_evidence.json`，记录 `passed`、20/20。
- [x] 4.4 真实 Gate 完成并获授权后，已归档 evidence 副本与 SHA-256 索引，并同步 umbrella tasks 6.1/6.2；本次未触发校准 child。
- [x] 4.5 阻断记录（2026-08-13）：pinned run `7887d515` 的逐票候选未随 evidence bundle 归档（bundle 仅含聚合指标），且其 warm cache（5208×5=26040 槽位，`cache_warm=true`/`cache_hits=26040`）在本机已不可恢复：主 checkout `value-screener/data/cache` 仅剩 73 个 code（7 月旧数据）、其余候选缓存位置（worktree/废纸篓/Time Machine 本地快照）均无；全市场 child worktree 清理时未跟踪的 `data/cache` 随之删除。离线确定性再派生因此不可执行；不得以部分缓存重抓（会改变数据快照并触发全量 provider 调用）冒充 pinned run 的 Top 20。恢复路径需用户决定：(a) 授权一次新的受控全市场 warm-cache L1+L2 run 并将新 run 固定为产品 run（需 provider/LLM 授权、冻结输入、run ID、安全 output root）；(b) 其他用户指定路径。未授权前 6.1/6.2 保持 not started。**2026-08-13 用户已授权路径 (a)，执行见 4.6。**

## 4.6 受控全市场 warm-cache L1+L2 重跑（用户 2026-08-13 授权；design D8/D9）

- [x] 4.6.1 TDD（RED→GREEN）：evidence bundle 归档 `l1_candidates`（有序候选）；`derive_top20_from_pinned_bundle` 内嵌候选离线消费（无缓存/无 provider，身份与漏斗检查不变，`derivation_kind=pinned_bundle_l1_candidates`）；`run_full_market_evidence.py --force-l2` 透传（默认 False）。缺候选/数量漂移/候选缺 ticker → 阻断或 not_evaluable。focused 测试 80 passed。
- [x] 4.6.2 冻结 universe：归档 bundle 的 5208 SH/SZ `input_tickers` 写为 `value-screener/data/universe_g1_top20_frozen.json`；重算 hash == `9d20ac29743c`（与 8-12 run 输入身份一致）。
- [x] 4.6.3 全量五维预热（cache-first、进度遥测、失败明细落日志；预热点位在 worktree `value-screener/data/cache`，不触碰主 checkout 缓存与用户 WIP）。
- [x] 4.6.4 warm check 全暖 → 受控 evidence run（`--force-l2 --freshness-policy allow_stale --coverage full_market --tickers-file <冻结 universe>`；LLM env 来自主 checkout `.env`）。修复 freshness policy 断裂后重跑：2026-08-14 `b4862934`，真实 L2 调用 217 次。
- [x] 4.6.5 验证 bundle（coverage=full_market、cache_warm=true、hard_gate_passed、可用率、unhandled=0、`len(l1_candidates)==funnel.after_heat_filter`）→ bundle 副本与 SHA-256 归档到 child evidence（见 `evidence/2026-08-14_b4862934/evidence-index.md`）。
- [x] 4.6.6 新 bundle 固定为产品 run：`top20 derive` 消费内嵌候选 → `user_review_template.json` 已生成（20 条均为空 label/confidence/reason）。用户未逐只复核前 6.1/6.2 保持未勾选。
- [x] 4.6.7 修复 freshness policy 断裂：`allow_stale` 从 evidence → scout_batch → assemble_snapshot 全链路传递；保留 `require_fresh` 默认严格语义；新增 stale L2 输入测试。
- [x] 4.6.8 修复全量 L2 error false-pass：`force_l2=true`、L2 全部 error 且真实调用数为 0 时，保留 `hard_gate_passed` 工程字段结果，但最终 `gate_passed=false`；新增回归测试。

## 5. 验证与收口

- [x] 5.1 `value-screener/.venv/bin/python -m pytest tests/test_top20_review.py tests/test_cli_top20.py -q` 通过（35 passed）。
- [x] 5.2 `value-screener/.venv/bin/python -m pytest -q` 全量通过（859 passed, 1 skipped, 1 xfail，与基线一致）。
- [x] 5.3 `openspec validate --all --strict` 通过。
- [x] 5.4 `value-screener/.venv/bin/python -m compileall -q value-screener` 与 `git diff --check` 通过。
- [x] 5.5 独立 review：Top 20 绑定、mock/fixture 防冒充、逐只可审计、14/20 阈值、三态语义、WIP/debate/watchlist/data 无污染（见提交说明）。
- [x] 5.6 独立收口检查确认本 child、evidence 与必要 umbrella 6.1/6.2 更新范围明确；根目录用户 WIP 未修改未 stage；本次不 merge、不 push。
