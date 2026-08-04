from __future__ import annotations

import json

from data.cache.manager import CacheManager


def test_cache_manager_is_importable_and_normalizes_ticker(tmp_path):
    cache = CacheManager(tmp_path / "cache")

    cache.set("600009.SH", "basic", {"code": "600009", "name": "上海机场"})

    assert cache.get("600009", "basic") == {
        "code": "600009",
        "name": "上海机场",
    }
    assert (tmp_path / "cache" / "600009" / "basic.json").exists()


def test_cache_manager_writes_valid_json_atomically(tmp_path):
    cache = CacheManager(tmp_path / "cache")

    cache.set("002156.SZ", "financials", {"code": "002156", "value": 1})

    path = tmp_path / "cache" / "002156" / "financials.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "code": "002156",
        "value": 1,
    }
    assert not list(path.parent.glob("*.tmp"))
