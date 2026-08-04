# G2 Strong Single-Agent Fallback Foundation

日期：2026-08-04
change：`g2-strong-single-agent-fallback`
工作树：`f3c-harness-mainline`

## 已完成

- 新增 [council/fallback.py](/Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline/value-screener/council/fallback.py)。
- 新增 [test_council_fallback.py](/Users/admin/Documents/trade-agent/.worktrees/f3c-harness-mainline/value-screener/tests/test_council_fallback.py)。
- fallback 复用 dossier preflight，但不调用 `run_debate`，不写 Council cache、debate 或 watchlist。
- 每次最多调用一个 strong agent 一次。
- grounding/circular-reference 检查作为 hard quality breaker。
- 失败时 deterministic synthesis 输出 `signal=skip`、`conviction=0`，不复制未经验证事实。
- passed/blocked/transport 结果均写入 run-scoped fallback artifact。

## 验证

- fallback focused tests：`10 passed`。
- fallback + provider compatibility focused tests：`22 passed`。
- 完整 pytest：`591 passed in 44.95s`。
- Python compile check：通过。
- OpenSpec strict validation：通过。
- `git diff --check`：通过。

## Capability 边界

该 foundation 只证明工程机制可运行，不证明 strong model live quality，也不证明 G2 capability passed。

- 未执行新的 fallback live call；此前 provider compatibility probe 已显示当前 provider/model 链路不稳定。
- 尚未定义最终 `InvestmentThesis` interface。
- 尚未完成 8-10 只样本的 Council A/B、人工盲评和 G2 相对价值 Gate。
- G3 runtime 继续锁定。
