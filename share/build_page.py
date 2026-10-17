#!/usr/bin/env python3
"""สร้างหน้าเว็บไฟล์เดียวที่ฝังข้อมูลทุกงวดไว้ในตัว

ผลลัพธ์เปิดได้โดยไม่ต้องมีเซิร์ฟเวอร์ ไม่ต้องมีฐานข้อมูล และส่งต่อให้คนอื่นได้

    python share/build_page.py                  # -> share/lotto-page.html
    python share/build_page.py --out ที่อื่น.html
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lottodb import page, store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="ที่เก็บไฟล์ฐานข้อมูล")
    parser.add_argument("--out", default=str(Path(__file__).with_name("lotto-page.html")))
    args = parser.parse_args()

    conn = store.connect(args.db)
    try:
        stats = page.build(conn, Path(args.out))
    finally:
        conn.close()

    print(
        f"เขียน {args.out}\n"
        f"  {stats['draws']:,} งวด · {stats['prizes']:,} เลขรางวัล · {stats['page_kb']:,} KB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
