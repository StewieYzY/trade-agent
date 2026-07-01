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

#### Scenario: 已有分裂目录的迁移
- **WHEN** `data/cache/` 下已存在 `600519.SH/`（空壳）与 `600519/`（真实数据）双目录
- **THEN** normalize 落地后 SHALL 以纯数字目录为唯一真值，带后缀空壳目录 SHALL 被清理或忽略，不再产生新的分裂

#### Scenario: 与 features.py 已有 normalize 对齐
- **WHEN** `assemble_council_features("600519.SH")` 调用 `assemble_snapshot(normalized_ticker)`
- **THEN** CacheManager 层的 normalize SHALL 与 `features.py` 的 `ticker.split(".")[0]` 行为一致，避免调用方各自 normalize 导致口径分歧
