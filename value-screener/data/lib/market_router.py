"""市场路由 · A 股/HK/US ticker 解析 + 证券类型分类.

借鉴 UZI market_router.py（212 行），去掉 fund_name_em 网络依赖（纯前缀判定），
符合 change 0 数据层"纯函数、不触发额外采集"的约束。

A 股代码规则：
  SH 主板 60xxxx / STAR 688xxx / B 股 900xxx / CDR 689xxx
  SZ 主板+中小板 00xxxx / 创业板 30xxxx / B 股 20xxxx
  BJ 43/83/87/88/92xxxx
  基金/ETF：SH 50/51/52/56/58xxxx；SZ 15/16xxxx
  可转债：SH 11xxxx；SZ 12xxxx
HK：5 位数字 + .HK；US：字母代码。
"""
from __future__ import annotations

import re
from collections import namedtuple

TickerInfo = namedtuple("TickerInfo", ["raw", "code", "full", "market"])

_RE_A_FULL = re.compile(r"^(?P<code>\d{6})\.(?P<ex>SH|SZ|BJ)$", re.I)
_RE_A_NUMERIC = re.compile(r"^\d{6}$")
_RE_HK = re.compile(r"^\d{1,5}\.HK$", re.I)
_RE_US = re.compile(r"^[A-Z]{1,6}(\.[A-Z]{1,3})?$")

_SH_STOCK_PREFIXES_3 = ("688", "689", "900", "600", "601", "603", "605")
_SH_B_SHARE = "900"
_SZ_STOCK_PREFIXES_3 = ("000", "001", "002", "003", "300", "301", "200", "201")
_SZ_LOF_PREFIXES_2 = ("16",)
_SZ_FUND_PREFIXES_3 = ("159", "150", "152")
_SH_FUND_PREFIXES_2 = ("50", "51", "52", "56", "58")
_SH_BOND_PREFIXES_2 = ("11",)
_SZ_BOND_PREFIXES_2 = ("12",)
_BJ_PREFIXES_2 = ("43", "83", "87", "88", "92")


def _a_share_suffix(code6: str) -> str:
    """6 位 A 股代码 → 交易所后缀 SH/SZ/BJ."""
    if code6.startswith("6") or code6.startswith("9"):
        return "SH"
    if code6.startswith("8") or code6.startswith("4") or code6.startswith("92"):
        return "BJ"
    return "SZ"


def is_chinese_name(raw: str) -> bool:
    """含 CJK 字符（需名称→代码解析，本层不实现解析，由调用方处理）."""
    return any("\u4e00" <= ch <= "\u9fff" for ch in raw)


def classify_security_type(code6: str) -> str:
    """6 位代码 → 证券类型（stock / etf / lof / convertible_bond / unknown）.

    纯前缀判定，不调用 akshare（去掉 UZI 的 fund_name_em 网络依赖）。
    """
    if not code6 or not code6.isdigit() or len(code6) != 6:
        return "unknown"
    if code6.startswith(_SZ_FUND_PREFIXES_3) or code6.startswith(_SH_FUND_PREFIXES_2):
        if code6.startswith(("501", "502", "506")):
            return "lof"
        return "etf"
    if code6.startswith(_SZ_LOF_PREFIXES_2):
        return "lof"
    if code6.startswith(_SH_BOND_PREFIXES_2) or code6.startswith(_SZ_BOND_PREFIXES_2):
        return "convertible_bond"
    if code6.startswith(_SH_STOCK_PREFIXES_3) or \
       code6.startswith(_SH_B_SHARE) or \
       code6.startswith(("60",)) or \
       code6.startswith(_SZ_STOCK_PREFIXES_3) or \
       code6.startswith(_BJ_PREFIXES_2):
        return "stock"
    return "unknown"


def parse_ticker(raw: str) -> TickerInfo:
    """Best-effort ticker 解析。中文名（如 '水晶光电'）需调用方先 resolve."""
    s = raw.strip().upper().replace(" ", "")
    m = _RE_A_FULL.match(s)
    if m:
        return TickerInfo(raw=raw, code=m.group("code"),
                          full=f"{m.group('code')}.{m.group('ex').upper()}", market="A")
    if _RE_A_NUMERIC.match(s):
        suffix = _a_share_suffix(s)
        return TickerInfo(raw=raw, code=s, full=f"{s}.{suffix}", market="A")
    if s.endswith(".HK"):
        code = s.removesuffix(".HK").lstrip("0") or "0"
        return TickerInfo(raw=raw, code=code, full=f"{code.zfill(5)}.HK", market="H")
    if s.isdigit() and 3 <= len(s) <= 5:
        return TickerInfo(raw=raw, code=s.lstrip("0") or "0",
                          full=f"{s.zfill(5)}.HK", market="H")
    if _RE_US.match(s):
        return TickerInfo(raw=raw, code=s, full=s, market="U")
    return TickerInfo(raw=raw, code=raw, full=raw, market="A")


if __name__ == "__main__":
    for t in ["000001", "600519", "002273.SZ", "300750", "00700.HK", "AAPL", "水晶光电"]:
        print(t, "->", parse_ticker(t), classify_security_type(parse_ticker(t).code))
