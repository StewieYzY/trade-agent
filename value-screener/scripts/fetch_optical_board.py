"""Task 5.1 (f1-deviation-fix): 拉取光通信模块板块股票列表.

用户决策（2026-07-02）：§5 全市场验证用 A 股光通信模块板块（BK1136）替代全 A 股，
控制在 50 只左右（"少一些，不然容易崩"）。验证 batch→screen→scout 管线在真实板块分布
（非 20 只手工白马样本）下的漏斗比例与 L2 区分度。

输出：data/all_a_share.txt（每行一个 6 位代码，前 50 只）

用法：
    cd value-screener && python scripts/fetch_optical_board.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import akshare as ak

OUT_FILE = Path(__file__).resolve().parent.parent / "data" / "all_a_share.txt"
LIMIT = 50  # 用户要求控制在 50 只左右


def main() -> None:
    df = ak.stock_board_concept_cons_em(symbol="光通信模块")
    codes = df["代码"].astype(str).str.zfill(6).tolist()
    print(f"光通信模块板块成分股：{len(codes)} 只")

    selected = codes[:LIMIT]
    print(f"取前 {len(selected)} 只（用户要求控制在 50 左右）")

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text("\n".join(selected) + "\n", encoding="utf-8")
    print(f"写入 {OUT_FILE}")
    print(f"前 10: {selected[:10]}")


if __name__ == "__main__":
    main()
