"""g1-canonical-run-identity: canonical ticker SoT + run_id 测试.

对应 run-identity spec：
- Canonical Ticker 单一 SoT（canonical_ticker / canonical_code）
- Run ID 生成与传播（generate_run_id / compute_input_ticker_set_hash）
"""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.lib.identity import (
    canonical_ticker,
    canonical_code,
    generate_run_id,
    compute_input_ticker_set_hash,
)


# ============================================================
# Task 1.1-1.5: canonical ticker SoT
# ============================================================

def test_canonical_ticker_pure_digit_adds_suffix():
    """canonical_ticker 纯 6 位数字 → 大写带后缀；920xxx → .BJ（不误判 SH）.

    修 cli._normalize_ticker 把 920xxx BJ 误判为 SH 的 bug（首字符 9 → SH）。
    market_router._a_share_suffix 优先判 BJ 前缀（43/83/87/88/92）。
    """
    assert canonical_ticker("600519") == "600519.SH"
    assert canonical_ticker("920060") == "920060.BJ", "920xxx BJ MUST NOT 误判为 SH"
    assert canonical_ticker("000001") == "000001.SZ"


def test_canonical_ticker_uppercases_suffix():
    """同证券不同大小写输入产出相同 canonical（大写）."""
    assert canonical_ticker("600519.sh") == "600519.SH"
    assert canonical_ticker("600519.SH") == "600519.SH"
    assert canonical_ticker("920060.bj") == "920060.BJ"
    assert canonical_ticker("920060.BJ") == "920060.BJ"
    # 同证券不同大小写 → 相同 canonical
    assert canonical_ticker("600519.sh") == canonical_ticker("600519.SH")


def test_canonical_ticker_hk_us_compat():
    """HK / US ticker 兼容，不抛错."""
    assert canonical_ticker("00700.HK") == "00700.HK"
    assert canonical_ticker("AAPL") == "AAPL"
    assert canonical_ticker("aapl") == "AAPL"  # US 大写化


def test_canonical_ticker_invalid_raises():
    """非法 ticker 抛 ValueError 附清晰原因，MUST NOT 静默返回原值或伪造后缀.

    注：parse_ticker 对 3-5 位数字识别为 HK（如 '123' → 00123.HK），属合法 HK，
    不在非法 case 内。非法 case 是：非 6 位且非 HK/US 形式、未知后缀、空。
    """
    invalid_cases = [
        "1234567",       # 7 位数字（非 6 位 A 股、非 3-5 位 HK）
        "600519.XX",     # 未知后缀（.XX 非 .SH/.SZ/.BJ）
        "abc123",        # 字母数字混合非 US（US 正则仅纯字母）
        "水晶光电",        # 中文名（本层不解析，调用方应先 resolve）
        "",
    ]
    for raw in invalid_cases:
        with pytest.raises(ValueError, match="ticker|invalid|无法识别"):
            canonical_ticker(raw)
        # 静默返回原值的反面断言：确保不返回原值
    # 合法 HK 短码不抛错（边界确认）
    assert canonical_ticker("123") == "00123.HK"


def test_canonical_code_returns_pure_digit():
    """canonical_code 返回纯标识部分，与 CacheManager._normalize_ticker（D3）方向一致.

    身份标识（canonical_ticker 带后缀）与 cache key（canonical_code 纯标识）分离。
    注：HK code 去 0 是 parse_ticker 既有行为（00700.HK → code=700），cache key 不要求固定宽度。
    """
    assert canonical_code("600519.SH") == "600519"
    assert canonical_code("600519") == "600519"
    assert canonical_code("600519.sh") == "600519"
    assert canonical_code("920060.BJ") == "920060"
    # HK / US 的 code（HK 去 0 是 parser 既有行为）
    assert canonical_code("00700.HK") == "700"
    assert canonical_code("AAPL") == "AAPL"


# ============================================================
# Task 3.1-3.4: run_id 生成（uuid4 唯一）+ 输入集合 hash（确定性）
# design D2 纠正：run_id 改 uuid4（每次唯一），input_hash 独立确定性，两者解耦
# ============================================================

def test_generate_run_id_unique_per_call():
    """相同输入两次调用 generate_run_id 返回不同 run_id（uuid4 每次唯一，非稳定 hash）.

    D2 纠正：原「稳定摘要」与 D6「同日不同 run 不覆盖」矛盾。run_id 改 uuid4，
    每次执行唯一，定位「哪一次 run」。「输入变 vs 规则变」可区分性由 input_hash +
    profile_version 承担，不再由 run_id 承担。
    """
    rid1 = generate_run_id()
    rid2 = generate_run_id()
    assert rid1 != rid2, "uuid4 run_id MUST 每次唯一（非稳定 hash）"


def test_generate_run_id_is_uuid4_format():
    """run_id SHALL 匹配 uuid4 标准格式（uuid.UUID 解析不抛错 + version==4）."""
    import uuid
    rid = generate_run_id()
    parsed = uuid.UUID(rid)  # 非法格式会抛 ValueError
    assert parsed.version == 4, "MUST 是 uuid4（非其他版本）"


def test_input_ticker_set_hash_stable_and_differs_on_input_change():
    """input_hash 确定性：相同集合两次相同；集合变化（增删改）→ hash 不同.

    input_hash 与 run_id 解耦：input_hash 描述「输入集合指纹」（确定），
    run_id 定位「哪次 run」（uuid4 唯一）。同输入两次 run → run_id 不同但 input_hash 相同。
    """
    tickers = ["600519", "000001"]
    h1 = compute_input_ticker_set_hash(tickers)
    h2 = compute_input_ticker_set_hash(tickers)
    assert h1 == h2, "相同集合 input_hash MUST 确定"
    # 集合变化（删一只）
    h_changed = compute_input_ticker_set_hash(["600519"])
    assert h1 != h_changed, "集合变化 input_hash MUST 不同"


def test_input_ticker_set_hash_order_invariant():
    """相同 ticker 集合不同顺序 → 相同 hash（sorted 消除顺序影响）."""
    tickers_order1 = ["600519", "000001", "920060"]
    tickers_order2 = ["920060", "600519", "000001"]  # 不同顺序
    hash1 = compute_input_ticker_set_hash(tickers_order1)
    hash2 = compute_input_ticker_set_hash(tickers_order2)
    assert hash1 == hash2, "集合语义，顺序无关"


def test_input_ticker_set_hash_canonicalizes_tickers():
    """输入 ticker 形式不同（600519 vs 600519.SH）但同证券 → 相同 hash.

    canonical_ticker 先归一再 hash，避免 600519 / 600519.SH 产生不同 hash。
    """
    tickers_plain = ["600519", "000001"]
    tickers_suffixed = ["600519.SH", "000001.SZ"]  # 同证券带后缀
    assert compute_input_ticker_set_hash(tickers_plain) == \
           compute_input_ticker_set_hash(tickers_suffixed), \
           "同证券不同形式 MUST 产出相同 hash（canonical 归一后 hash）"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
