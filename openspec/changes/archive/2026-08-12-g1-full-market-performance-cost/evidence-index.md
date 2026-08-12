# Evidence Index

本索引随 `g1-full-market-performance-cost` 归档，保留原始 JSON 证据的来源、哈希和解释。原始运行目录为 `value-screener/data/evidence/`；该目录被 `.gitignore` 忽略，因此归档副本放在本 change 的 `evidence/` 目录。

## Final Full-Market Evidence

- `evidence/2026-08-12_7887d515.json`
- 原始来源：`value-screener/data/evidence/2026-08-12_7887d515.json`
- SHA-256：`80334e3b2afdcf920100dbe33b52d0d27a3144caad45426f1950ff200d45760d`
- Scope：沪深 5208 只；北交所 334 只排除；`coverage=full_market`
- Policy：`freshness_policy=allow_stale`；`cache_warm=true`；fresh 18552、stale 7488、missing 0、invalid 0
- Hard Gate：字段可用率 100%；未处理异常 0；`hard_gate_passed=true`
- Observed：总耗时 67.2 秒；L2 真实调用 218 次；247656 tokens；实测/等效成本 ¥0.247656
- L2 distribution：deep_dive 93、watch 158、skip 0、error 1、degraded 34
- Known error：`603529.SH`，`stage=parse`，`LLM 输出解析失败`；未隐藏
- `gate_passed=true` 仅表示本 child 的 full-market hard Gate 通过，不代表 G1 capability passed

## Full-Market Cache-Read Evidence

- `evidence/2026-08-12_9053b2ea.json`
- 原始来源：`value-screener/data/evidence/2026-08-12_9053b2ea.json`
- Scope：沪深 5208 只；`coverage=full_market`
- Policy：`freshness_policy=allow_stale`；`cache_warm=true`
- Purpose：新 schema / stale cache 读取 / full-market 口径验证；本次 L2 复用 217 个 cache hit，未产生新 LLM 调用

## Partial-Market Controlled Evidence

- `evidence/2026-08-12_8776878f.json`
- 原始来源：`value-screener/data/evidence/2026-08-12_8776878f.json`
- Scope：沪深 10 只子集；北交所排除；`coverage=partial_market`
- Policy：`freshness_policy=allow_stale`；50 个数据槽位全部 stale 但结构有效；missing 0、invalid 0
- Purpose：验证 partial-market bundle、cache_warm/data_freshness 分离和 L2 failure distribution
