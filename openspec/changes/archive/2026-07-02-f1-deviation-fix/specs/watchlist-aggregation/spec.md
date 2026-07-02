## ADDED Requirements

### Requirement: cache ticker key normalize
CacheManager SHALL 在读写缓存时将 ticker key 统一 normalize 为纯 6 位数字（去除 `.SH` / `.SZ` 后缀），消除 `600519` / `600519.SH` 双目录并存。

> 背景：deviation-analysis §1.4 实证发现 `data/cache/` 下同票两份目录并存——纯数字目录（`600519/`）有真实数据，带后缀目录（`600519.SH/`）多为空壳。`features.py` 已做 `ticker.split(".")[0]` 标准化，但 CacheManager 层未对齐，导致 fetcher 写缓存时有的用纯数字、有的带后缀。下游 `council` 用 `.SH` 读时读到空壳，叠加 TTL 过期导致门 1 首跑 `insufficient_data` 崩溃。

#### Scenario: 写缓存时 normalize ticker key
- **WHEN** fetcher 对 ticker `600519.SH` 写任意维度缓存
- **THEN** CacheManager SHALL 将 key normalize 为 `600519`，写入 `data/cache/600519/`，不创建 `data/cache/600519.SH/` 目录

#### Scenario: 读缓存时 normalize ticker key
- **WHEN** 调用方以 `600519.SH` / `600519` / `600519.SZ` 任一格式读取缓存
- **THEN** CacheManager SHALL 都从 `data/cache/600519/` 读取，返回相同数据

#### Scenario: 已有分裂目录的安全迁移
- **WHEN** `data/cache/` 下已存在带后缀目录（如 `600519.SH/` 或孤儿 `002594.SZ/`）
- **THEN** 迁移逻辑 SHALL 先检查带后缀目录是否含真实数据文件（basic.json/financials.json/kline.json/risk.json/valuation.json），**不得直接删除**：
  - 若带后缀目录为空壳（无真实数据文件）→ 直接删除
  - 若带后缀目录有真实数据，但纯数字目录也存在且有数据 → 以纯数字目录为真值，带后缀目录数据作为参考归档后删除（或人工确认后合并）
  - 若带后缀目录有真实数据，且无对应纯数字目录（孤儿目录，如 `002594.SZ`）→ SHALL 将数据文件移动到纯数字目录（`002594/`）后再删除带后缀目录，**不得丢弃真实数据**
- **AND** normalize 落地后不再产生新的带后缀目录

#### Scenario: 孤儿目录数据保护
- **WHEN** `data/cache/002594.SZ/` 是孤儿目录（无 `002594/`）且含真实数据文件
- **THEN** 迁移 SHALL 创建 `data/cache/002594/` 并移动数据文件，再删除 `002594.SZ/`，SHALL NOT 直接 `rm -rf 002594.SZ/`

#### Scenario: 与 features.py 已有 normalize 对齐
- **WHEN** `assemble_council_features("600519.SH")` 调用 `assemble_snapshot(normalized_ticker)`
- **THEN** CacheManager 层的 normalize SHALL 与 `features.py` 的 `ticker.split(".")[0]` 行为一致，避免调用方各自 normalize 导致口径分歧
