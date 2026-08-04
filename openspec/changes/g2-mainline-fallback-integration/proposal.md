## Why

G2 strong single-agent fallback 已在 f3c worktree 中完成，但从最新 `main` 的干净
checkout 集成时暴露出两个未显式纳入版本控制的前置依赖：`data.cache.CacheManager`
缺失，以及 Council dossier input preflight 尚未进入 mainline。现在需要把 fallback
变成可独立检出、可测试、可审计的 G2 foundation，而不是依赖某个脏 worktree 的本地文件。

## What Changes

- 将 `CacheManager` 运行时源码纳入 mainline，保留现有 ticker 归一化、TTL 和原子写语义；
- 将 Council dossier input preflight 作为 fallback 的显式 mainline prerequisite 接入；
- 保持 fallback 只调用一个 strong agent，不写 Council cache、debate 或 watchlist；
- 增加 clean-checkout integration tests，证明 fallback 在没有本地缓存 JSON 时仍可导入、
  preflight，并对无效输入零副作用；
- 不提交任何 `data/cache/{ticker}/*.json`、live raw、debate 或 watchlist 运行产物；
- 不以本 change 宣称 G2 capability pass，也不启动 G2 A/B 或 G3 runtime。

## Capabilities

### New Capabilities

- `g2-mainline-fallback-integration`: 定义 fallback foundation 在干净 mainline 中的
  可移植依赖、输入 preflight 和 artifact isolation 合同。

### Modified Capabilities

- 无；本 change 只把既有 f3c preflight 与 G2 fallback foundation 集成到 mainline，
  不改变生产 Council 的既有 requirement。

## Impact

- 受影响代码：`value-screener/data/cache/`、`value-screener/council/debate.py`、
  `value-screener/council/fallback.py` 及对应测试；
- 受影响 OpenSpec：新增 `g2-mainline-fallback-integration` capability；
- 不引入新依赖，不纳入缓存数据和实验运行产物；
- 需要在 clean worktree 中运行 focused/full pytest、strict validation 和 diff check。
