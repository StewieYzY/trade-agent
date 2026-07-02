"""Tests for cache ticker key normalize（f1-deviation-fix §4, D3）.

spec watchlist-aggregation: CacheManager SHALL 在读写缓存时将 ticker key 统一 normalize
为纯 6 位数字（去除 .SH / .SZ 后缀），消除 600519 / 600519.SH 双目录并存。

与 features.py 已有的 ticker.split(".")[0] 对齐——normalize 应在数据层最底层（CacheManager）
做一次，调用方不用各自处理。
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.cache.manager import CacheManager


def test_set_normalizes_suffixed_ticker_to_pure_digits(tmp_path):
    """task 4.2/4.3: 写 600519.SH → 落到 600519/ 目录，不创建 600519.SH/."""
    cm = CacheManager(base_dir=str(tmp_path / "cache"))
    cm.set("600519.SH", "basic", {"name": "贵州茅台"})

    # 应写入纯数字目录
    assert (tmp_path / "cache" / "600519" / "basic.json").exists()
    # 不应创建带后缀目录
    assert not (tmp_path / "cache" / "600519.SH").exists()


def test_get_normalizes_suffixed_ticker_to_pure_digits(tmp_path):
    """task 4.2/4.3: 以 600519.SH / 600519 / 600519.SZ 三种格式读，命中同一份缓存."""
    cm = CacheManager(base_dir=str(tmp_path / "cache"))
    cm.set("600519", "basic", {"name": "贵州茅台", "market_cap": 1e12})

    # 三种格式读同一份
    via_pure = cm.get("600519", "basic")
    via_sh = cm.get("600519.SH", "basic")
    via_sz = cm.get("600519.SZ", "basic")

    assert via_pure == via_sh == via_sz
    assert via_pure["name"] == "贵州茅台"


def test_is_expired_normalizes_ticker(tmp_path):
    """is_expired 也 normalize ticker——同票不同格式的一致性."""
    cm = CacheManager(base_dir=str(tmp_path / "cache"))
    cm.set("600519.SH", "basic", {"name": "贵州茅台"})

    # 用纯数字查 is_expired，应与带后缀一致（都不过期）
    assert cm.is_expired("600519", "basic") is False
    assert cm.is_expired("600519.SH", "basic") is False


def test_clear_normalizes_ticker(tmp_path):
    """clear 也 normalize ticker——清 600519.SH 应清掉 600519/ 下文件."""
    cm = CacheManager(base_dir=str(tmp_path / "cache"))
    cm.set("600519.SH", "basic", {"name": "贵州茅台"})
    cm.set("600519.SH", "financials", {"income": {}})

    n = cm.clear("600519.SH")
    assert n == 2
    assert not (tmp_path / "cache" / "600519" / "basic.json").exists()


def test_normalize_lowercases_suffix(tmp_path):
    """小写后缀 .sh / .sz 也 normalize（健壮性）."""
    cm = CacheManager(base_dir=str(tmp_path / "cache"))
    cm.set("600519.sh", "basic", {"name": "贵州茅台"})
    assert (tmp_path / "cache" / "600519" / "basic.json").exists()
    assert not (tmp_path / "cache" / "600519.sh").exists()
