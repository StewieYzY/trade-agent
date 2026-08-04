# M0：G2 前置可信基础 Rolling Handoff

日期：2026-08-04

## 当前基线

```text
workspace: /Users/admin/Documents/trade-agent
branch:    main
HEAD:      f47db88 chore(g2): archive mainline fallback integration
```

clean G2 integration worktree 仍保留：

```text
/Users/admin/Documents/trade-agent/.worktrees/g2-integration-mainline
codex/g2-integration-mainline@f47db88
```

## 本次完成

- 独立 review `g2-integration-mainline@f47db88`；
- 将 clean G2 fallback integration fast-forward 合入 `main`；
- 保留 `g2-mainline-fallback-integration` archive；
- 保留 `g2-strong-single-agent-fallback` active change，OpenSpec 显示
  12/12 complete；
- fallback dossier preflight、单次 strong-agent、deterministic synthesis、
  quality blocking 和 run-scoped artifact isolation 均通过代码 review；
- f3e 继续保持 bounded but inconclusive，既有 evidence 不删除、不冒充 G2
  capability evidence。

## 验证证据

本轮在当前本机环境独立复验：

```text
Council preflight + fallback focused: 22 passed
Cache integration + ticker normalization: 7 passed
Python compileall: passed
OpenSpec strict:
  g2-deep-investment-thesis: valid
  g2-strong-single-agent-fallback: valid
git diff --check: passed
```

full pytest 未能在当前环境重新 collection，原因是本机缺少项目已有依赖
`akshare`、`typer`、`pandas`，且 Docker daemon 未启动。之前 handoff 记录的
`527 passed` 保留为历史执行证据，本文件不将其描述为本轮独立复验结果。

## Review 结论

`g2-mainline-fallback-integration`：工程 review 通过，但带有 full-suite 环境
复验限制。

本次未发现需要阻断合入的 P0/P1 代码问题。当前合入只证明：

- clean mainline 能导入 fallback 所需的 cache source；
- invalid dossier 会在 cache/LLM/artifact 前 fail closed；
- valid fallback 最多调用一次 strong agent；
- blocked 输出不会变成方向性成功；
- fallback 不写入 Council cache、debate 或 watchlist 成功路径。

## Capability 边界

```text
G1：未通过
G2：未通过
G3：继续锁定
```

以下事项仍未被本次合入证明：

- strong model live quality；
- Council 相比 strong single-agent 的相对增量；
- 成本证据；
- 8–10 只样本 A/B；
- 人工盲评；
- InvestmentThesis evidence bundle；
- G3 HoldingContract runtime。

## 下一步

1. 在具备项目完整依赖的既有 Docker/虚拟环境中补跑 full pytest；
2. 更新 mainline baseline 后推进 M1/M2：
   provider qualification → canonical snapshot → G1 real capability Gate；
3. 等 M4 dossier 字段、单位、状态和 assumption 分区稳定后，创建
   `g2-growth-expectation-contract`；
4. 依次完成 growth expectation contract、V0 engine、dossier integration；
5. 在 diagnostic artifact 和 assumption snapshot 冻结后，才开始最终
   Council-vs-fallback A/B；
6. G2 capability Gate 通过前不启动 G3 runtime。

## 停止条件

- 不得把本次 merge、archive 或 focused 绿测描述为 G2 passed；
- 不得用 mock/fixture 替代真实 provider 或真实 A/B evidence；
- full suite 未在完整依赖环境复验前，不得关闭验证限制；
- M4.5 未冻结共享 diagnostic 前，不运行最终 Council A/B；
- 不得因新增成长预期 PRD 直接跳过 M1/M2/G1 Gate。
