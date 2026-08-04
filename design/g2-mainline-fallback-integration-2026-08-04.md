# G2 Mainline Fallback Integration Handoff

日期：2026-08-04
工作树：`/Users/admin/Documents/trade-agent/.worktrees/g2-integration-mainline`
分支：`codex/g2-integration-mainline`

## 本次集成

- 基线：`main@dd52d11`
- fallback foundation checkpoint：`a6341a1 feat(g2): add strong single-agent fallback foundation`
- 新增 OpenSpec child：`g2-mainline-fallback-integration`
- 只集成 `CacheManager` source、Council input preflight 和受影响测试 fixture；
- 未集成 f3c live harness、live raw、cache JSON、debate 或 watchlist 产物。

## RED → GREEN

- RED：clean checkout 缺少 `data.cache`，fallback test collection 报
  `ModuleNotFoundError: No module named 'data.cache'`；
- RED：补入测试后，Council preflight tests 暴露 main 缺少
  `_prepare_council_input`，并在无效输入时先访问 cache；
- GREEN：tracked `data/cache` source + f3c preflight 最小实现 + 受影响 fixture 迁移；
- focused：`93 passed`（含 cache/preflight/fallback 与 Council 回归）；
- full：`527 passed in 45.33s`；
- OpenSpec strict validation：通过；
- `git diff --check`：通过。
- OpenSpec child 已归档至
  `openspec/changes/archive/2026-08-04-g2-mainline-fallback-integration/`。

## 当前边界

该 checkpoint 证明 G2 fallback foundation 可以从 clean mainline 导入和测试，不证明：

- strong model live quality；
- Council 相对 fallback 的增量；
- G2 capability A/B、成本证据或人工盲评；
- G3 runtime 可启动。

测试运行产生的 `debate/` 与 `watchlist/` 文件保持为本地运行产物，不进入提交。
