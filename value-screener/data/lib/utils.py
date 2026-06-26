"""数据层通用工具.

to_float 统一数值解析（review #8：原 4 份重复实现合并）：
  - 去逗号；正则提取前导数值（自然丢弃 % 等后缀）
  - 识别 亿/万 单位 → 换算到元
  - None / "-" / "False" / "nan" 等无效值 → None
  覆盖 basic（纯数值）/ valuation（含 %）/ risk（含 %）/ financials（含 亿/万）全部场景。
"""
from __future__ import annotations

import re

_NUM_RE = re.compile(r"^-?[\d,]+\.?\d*")
_INVALID = {"", "-", "--", "false", "nan", "none"}


def to_float(v) -> float | None:
    """解析带单位/百分号/逗号的数值字符串 → float；无效返 None."""
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in _INVALID:
        return None
    m = _NUM_RE.match(s)
    if not m:
        return None
    try:
        num = float(m.group().replace(",", ""))
    except ValueError:
        return None
    if "亿" in s:
        num *= 1e8
    elif "万" in s:
        num *= 1e4
    return num
