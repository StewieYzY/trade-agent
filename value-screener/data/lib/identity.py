"""运行身份模块（g1-canonical-run-identity）.

提供横切运行身份契约（design D1-D2, D7）：
- canonical_ticker / canonical_code：统一 canonical ticker SoT，收敛 5 处旧归一化
- generate_run_id：每次执行唯一的 uuid4（D2 纠正：原稳定 hash 与 D6 同日不覆盖矛盾）
- compute_input_ticker_set_hash：输入集合指纹（确定性，与 run_id 解耦）

D2 纠正后的职责分离：
- run_id（uuid4 唯一）：定位「哪一次 run」，保证同日不同 run 不覆盖（D6）
- input_ticker_set_hash（确定性）：描述「输入集合指纹」，相同集合相同 hash
- profile_version（显式常量）：描述「规则版本」
「输入变 vs 规则变」可区分性由 input_hash + profile_version 两字段承担，不再由 run_id 承担。

身份标识与 cache key 分离：
- canonical_ticker(raw) 返回带后缀形式（600519.SH）作身份/输出/聚合 key
- canonical_code(raw) 返回纯 6 位数字（600519）作 cache key，与
  CacheManager._normalize_ticker（f1-deviation-fix D3）行为一致，D3 不动

复用 data/lib/market_router.parse_ticker（最完整解析器，含 BJ/HK/US），不重写解析器。
未识别格式（parse_ticker 返回 market=="A" 且 code==raw 即原始未识别）→ 抛 ValueError，
不静默返回原值或伪造后缀（run-identity spec: 非法 ticker 清晰报错）。
"""
from __future__ import annotations

import hashlib
import re
import uuid

from data.lib.market_router import parse_ticker, _RE_A_FULL, _RE_HK, _RE_US

# 合法 canonical 判定：parse_ticker 对已识别输入会转换（补后缀/补零/大写化），
# 对未识别输入兜底返回 TickerInfo(raw=raw, code=raw, full=raw, market="A")。
# 用 market + 后缀正则判断「已识别」而非裸 code==raw 比较（避免合法带后缀输入误判）。
_RE_A_FULL_CANONICAL = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")


def canonical_ticker(raw: str) -> str:
    """统一 canonical ticker（身份标识 SoT），大写带后缀.

    返回 parse_ticker(raw).full（如 600519.SH / 920060.BJ / 00700.HK / AAPL）。
    未识别格式抛 ValueError（不静默返回原值、不伪造后缀）。

    合法判定：parse_ticker 已识别 → full 是规范形式（A 股含 .SH/.SZ/.BJ 后缀，
    HK 含 .HK，US 大写字母）；未识别兜底 → full 等于规范化后的 raw 本身（无转换）。
    用 full 是否匹配合法后缀正则判断，避免「合法带后缀输入 full==raw」的误判。
    """
    info = _parse_or_raise(raw)
    _raise_if_unrecognized(raw, info)
    return info.full


def canonical_code(raw: str) -> str:
    """统一 canonical code（cache key），纯标识部分.

    返回 parse_ticker(raw).code（A 股为 6 位数字 600519，HK 去前导零如 700，US 为字母 AAPL）。
    与 CacheManager._normalize_ticker（D3，ticker.split(".")[0]）行为方向一致（取纯标识），
    但通过 parse_ticker 走 canonical SoT 而非裸 split（避免未归一输入分裂）。

    注：HK code 去 0 是 parse_ticker 既有行为（00700.HK → code=700），
    cache key 不要求固定宽度，HK 不与 A 股 6 位 cache 目录混用。
    """
    info = _parse_or_raise(raw)
    _raise_if_unrecognized(raw, info)
    return info.code


def _parse_or_raise(raw: str):
    """parse_ticker 包装：非字符串/空 → ValueError."""
    if not raw or not isinstance(raw, str):
        raise ValueError(f"invalid ticker: {raw!r}, expected non-empty string")
    return parse_ticker(raw)


def _raise_if_unrecognized(raw: str, info) -> None:
    """若 parse_ticker 未识别（兜底 full 等于规范化 raw 且非合法后缀形式）→ 抛 ValueError.

    合法判定规则：
    - market=='H'（HK）或 market=='U'（US）：parse_ticker 已识别，合法
    - market=='A'：full SHALL 匹配 ^\\d{6}\\.(SH|SZ|BJ)$，否则未识别兜底（非法）
    """
    if info.market in ("H", "U"):
        return  # HK / US 已识别
    if info.market == "A" and _RE_A_FULL_CANONICAL.match(info.full):
        return  # A 股合法后缀形式
    # 未识别兜底（full 是 raw 本身或含非法后缀如 .XX）
    raise ValueError(
        f"invalid ticker: {raw!r}, expected 6-digit A-share code "
        f"(e.g. 600519) or known suffix form (.SH/.SZ/.BJ), HK (.HK) or US ticker"
    )


def compute_input_ticker_set_hash(tickers: list[str]) -> str:
    """输入 ticker 集合的稳定 hash（集合语义，顺序无关）.

    对 canonical_ticker 集合排序后哈希，使：
    - 相同集合不同顺序 → 相同 hash（sorted 消除顺序）
    - 同证券不同形式（600519 vs 600519.SH）→ 相同 hash（canonical 归一）
    - 集合变化（增删改）→ 不同 hash（定位「输入数据变了」）

    返回 12 字符 sha256 摘要前缀。
    """
    if not tickers:
        # 空集合也需稳定 hash（不抛错，L1 输入可能为空边界）
        return hashlib.sha256("".encode("utf-8")).hexdigest()[:12]
    canonical_sorted = sorted(canonical_ticker(t) for t in tickers)
    joined = "|".join(canonical_sorted)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


def generate_run_id() -> str:
    """每次执行唯一的 run_id（design D2 纠正版：uuid4，非稳定 hash）.

    D2 纠正：原用 sha256(input_hash|run_date|profile_version) 稳定摘要，与 D6「同日不同
    run 不覆盖」矛盾（相同输入同日两次跑产出相同 run_id 无法区分）。改 uuid4 每次唯一。

    职责分离：
    - run_id（本函数，uuid4）：定位「哪一次 run」，保证同日不覆盖
    - input_ticker_set_hash（独立函数，确定性）：描述「输入集合指纹」
    - profile_version（screener.profile 常量）：描述「规则版本」
    「输入变 vs 规则变」可区分性由 input_hash + profile_version 承担，不在此函数。

    L1 生成一次，L2/weekly 继承同一值，MUST NOT 重新生成。纯 L2 单跑 fallback 生成 +
    标 run_id_source="scout_fallback"（由调用方标注，本函数只产 uuid4）。
    """
    return str(uuid.uuid4())
