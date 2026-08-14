## 1. Fallback contract tests (TDD)

- [x] 1.1 RED：新增 dossier preflight zero-side-effect 测试，覆盖空/错误/错 ticker 输入
- [x] 1.2 RED：新增 single-call 测试，断言只调用一个 strong agent、跳过 R2/DA/LLM synthesizer
- [x] 1.3 RED：新增 schema/transport/grounding/crosstalk quality breaker 测试，断言 blocked 不发布方向性结论
- [x] 1.4 RED：新增 deterministic synthesis 与 artifact isolation 测试，断言 passed 只复制字段、blocked 输出 skip

## 2. Fallback foundation implementation

- [x] 2.1 GREEN：实现 `council/fallback.py` 的 preflight、single-agent call 和 provenance
- [x] 2.2 GREEN：实现 deterministic fact checker 与 R1 hard quality breaker
- [x] 2.3 GREEN：实现 non-fabricating synthesis envelope、failure classification 和 run-scoped artifacts
- [x] 2.4 GREEN：提供最小 CLI/API 入口，默认 strong model，支持显式 model override

## 3. Verification and Gate boundary

- [x] 3.1 运行 fallback focused tests、既有 Council/f3e tests 和完整 pytest
- [x] 3.2 运行 strict OpenSpec validation、Python compile check 和 `git diff --check`
- [x] 3.3 用 fixture/mock 完成 passed/blocked/transport 三类机制证据，不伪造 live capability
- [x] 3.4 更新 G2 handoff，明确 fallback foundation 完成不等于 G2 capability pass，G3 继续锁定

## 4. Repair closure evidence

- [x] 4.1 `R-G2-001`：显式 dossier 的 canonical `core_snapshot.ticker` 必填，顶层与 nested optional section identity mismatch 在共享 Council/fallback preflight 中 fail closed；focused identity tests 覆盖 missing/empty/mismatch/normal path，确认 LLM/artifact/cache/watchlist 零副作用
- [x] 4.2 `R-G2-002`：fallback 复用 shared `redact_sensitive_text()`；focused tests 覆盖 error 与 malformed raw 中的 api_key、token、Bearer、URL credential、嵌套 mapping/list，并确认 error/raw/result/manifest 不含原始敏感值
- [x] 4.3 `R-G2-003`：fallback 复用 shared `validate_g1_output_root()`；focused tests 覆盖 cache/watchlist/debate/data/snapshots exact/descendant/ancestor/symlink 拒绝、外部 tmp root 允许及拒绝时零副作用
- [x] 4.4 验证证据：fallback focused 27 passed；Council preflight/dossier 16 passed；production-path 20 passed；provenance/provider-redaction 53 passed；全量 `value-screener/tests` 893 passed；compileall、diff check 和 strict OpenSpec 均待最终收口命令确认
