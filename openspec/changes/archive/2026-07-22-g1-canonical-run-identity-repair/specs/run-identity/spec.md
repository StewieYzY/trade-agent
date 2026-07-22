## MODIFIED Requirements

### Requirement: 运行隔离（同 run 不覆盖、跨 run 可定位）
同 ticker 不同 run 的**运行产物**（L1 输出 / L2 payload / watchlist / CLI output）SHALL 互相隔离，MUST NOT 因同一 ticker 或同一 output path 互相覆盖或混淆。跨 run 的历史产物 SHALL 仍可定位读取。CLI `--output` 与 `watchlist/{date}.json` 的同日直接覆盖语义 SHALL 改为 run-scoped 命名，使同日多次运行不互相覆盖；目标路径已存在但无 `run_id`（G1-3 前遗留产物）SHALL 同样分流，MUST NOT 覆盖旧无 identity 文件。

`run_id` 是 execution identity：定位某次 run、产物隔离命名、审计溯源。**cache 复用判定 MUST NOT 使用 `run_id`**——24h L2 cache 的 hit/miss 由 TTL + `profile_version` 决定（详见 `scout-agent` 24h Cache requirement）。同 ticker 不同 run_id 但同 `profile_version` 同日 → cache 复用（不混淆，因 verdict 在同规则下可复用）；cache entry 中的 `run_id` 是 provenance 元数据，记录该 verdict 源自哪次 run，不参与 hit 判定。L2 cache 的跨日隔离仍由 `{date}` 子目录承担（不变）。

> g1-canonical-run-identity-repair 修改：G1-3 原 `#### Scenario: 同 ticker 不同 run 的 cache 不混淆` 写「cache entry SHALL 通过 `run_id`/采集日区分」，被 G1-3 实现误读为「不同 run_id → cache miss」，破坏 24h 复用。本修改澄清：cache「不混淆」指 entry 通过 `{date}` 子目录 + `profile_version` 区分（跨日/跨规则不复用），**不指通过 run_id 区分**（同日同规则不同 run 该复用就复用）。run_id 只管运行产物隔离（watchlist/CLI output 的 run-scoped 文件名），不管 cache hit。另补「legacy CLI output 无 run_id 不覆盖」scenario（G1-3 实现 `_run_scoped_output_path` 漏了无 run_id 的旧文件分流）。

#### Scenario: 同日多次运行不互相覆盖
- **WHEN** 同一天对同一 ticker 集合多次运行 `screen` 或 `scout`
- **THEN** 每次 run 的输出 SHALL 带不同 `run_id`，产物文件 SHALL 不互相覆盖（带 run_id 命名），旧 run 产物仍可读取

#### Scenario: 跨 run 历史可定位
- **WHEN** 用户查看某 ticker 在历史某次 run 的结果
- **THEN** 系统 SHALL 能通过 `run_id` + canonical ticker 定位该次 run 的 L1/L2/watchlist 产物，MUST NOT 因后续 run 覆盖而丢失

#### Scenario: 同 ticker 不同 run 的 cache 复用规则
- **WHEN** 同一 canonical ticker 在不同 run（不同 run_id）但相同 `profile_version` 同日产生/查询 L2 cache
- **THEN** cache entry SHALL 通过 `{date}` 子目录 + `profile_version` 区分复用性，MUST NOT 通过 `run_id` 判定 hit/miss；不同 run_id 同 `profile_version` 同日 SHALL cache 复用（verdict 在同规则下可复用），cache entry 的 `run_id` 字段作 provenance 不参与判定；既有跨日 `{date}` 子目录隔离语义保留

#### Scenario: 旧 watchlist 文件保留只读
- **WHEN** canonical ticker 命名统一后，既有 watchlist 目录存在历史命名文件（含空壳与真数据分裂）
- **THEN** 既有文件 SHALL 保留只读作历史证据，MUST NOT 迁移或清空；新 run 用统一 canonical 命名

#### Scenario: legacy CLI output 无 run_id 不覆盖
- **WHEN** CLI `screen`/`scout` 的 `--output` 目标路径已存在一个无 `run_id` 字段的旧文件（G1-3 前遗留产物，或损坏的非 JSON 文件），且当前 run 携带 `run_id`
- **THEN** 当前 run SHALL 写入 run-scoped 分流文件名（`{stem}.{run_id[:8]}.json`），MUST NOT 覆盖该旧无 identity 文件；旧文件保留可读取
