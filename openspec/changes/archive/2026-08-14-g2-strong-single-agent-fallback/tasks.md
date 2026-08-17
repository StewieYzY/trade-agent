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
- [x] 4.4 验证证据：fallback focused 27 passed；Council preflight/dossier 16 passed；production-path 20 passed；provenance/provider-redaction 53 passed；最终全量 `value-screener/tests` 927 passed；OpenSpec strict 29/29；compileall、diff check 通过

## 5. Post-archive CR repair closure

- [x] 5.1 修复 schema-valid `agent_output`、`usage`、raw JSON 及嵌套 secret 的递归落盘脱敏
- [x] 5.2 修复 `core_snapshot` 深层 identity mismatch 的 fail-closed 校验
- [x] 5.3 将 protected output-root 校验提前到 dossier/provider preflight 之前
- [x] 5.4 同步 CURRENT handoff baseline、OpenSpec archive 状态和本次 CR closure evidence
- [x] 5.5 修复裸短 `Bearer`/`Token` credential 与普通诊断短语的边界，并补回归测试
- [x] 5.6 让 identity walker 覆盖 `collections.abc.Mapping` 的 core/research nested section
- [x] 5.7 修复嵌入上下文短 `Bearer` credential 落盘泄露，并同步 CURRENT handoff 当前 main/PR/WIP 状态
- [x] 5.8 修复小写嵌入 credential redaction，并在 CR2 repair 合入前将 R-G2-002 标为 `regressed`
- [x] 5.9 修复包围符与句末标点语境中的短 `Bearer`/`Token` credential 落盘泄露；fallback regression 覆盖 `result.json` 与 `manifest.json`，状态保持 `independent_review` / integration pending
- [x] 5.10 扩展常见括号/分号/冒号终止语境的短 credential redaction；补充 malformed raw、schema-valid JSON、usage 与 provider-batch artifact/消费路径回归
- [x] 5.11 收紧短 token 形状并保持换行、相邻标点与重复 redaction 的幂等性；补充 `Token expired`、`bearer bond` 等普通诊断负例和 provider snapshot consumer 回归
