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
