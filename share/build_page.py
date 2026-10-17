#!/usr/bin/env python3
"""สร้างหน้าเว็บไฟล์เดียวที่ฝังข้อมูลทุกงวดไว้ในตัว

ผลลัพธ์เปิดได้โดยไม่ต้องมีเซิร์ฟเวอร์ ไม่ต้องมีฐานข้อมูล และส่งต่อให้คนอื่นได้

    python share/build_page.py                       # -> share/lotto-page.html
    python share/build_page.py --out ที่อื่น.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lottodb import model, queries, schedule, store  # noqa: E402

TEMPLATE = Path(__file__).with_name("page_template.html")
PLACEHOLDER = "__DATA__"


def build(db_path: str | None, out_path: Path) -> dict:
    conn = store.connect(db_path)
    try:
        payload = collect(conn)
    finally:
        conn.close()

    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if PLACEHOLDER in blob:
        raise SystemExit("ข้อมูลมีสตริงที่ชนกับ placeholder")
    if "</script" in blob.lower():
        raise SystemExit("ข้อมูลมีสตริงที่ปิด <script> ก่อนเวลา")

    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"ไม่พบ {PLACEHOLDER} ใน {TEMPLATE.name}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(template.replace(PLACEHOLDER, blob), encoding="utf-8")
    return {
        "draws": len(payload["draws"]),
        "prizes": payload["prize_count"],
        "data_kb": len(blob.encode("utf-8")) // 1024,
        "page_kb": out_path.stat().st_size // 1024,
    }


def collect(conn) -> dict:
    """เลขของแต่ละหมวดต่อกันเป็นสตริงเดียว หน้าเว็บคลี่ออกตามจำนวนหลัก"""
    order = [c.key for c in sorted(model.CATEGORIES, key=lambda c: c.order)]
    slot = {key: i for i, key in enumerate(order)}

    draws: dict[str, list[str]] = {}
    total = 0
    for row in conn.execute(
        "SELECT draw_date, category, number FROM prizes ORDER BY draw_date, category, slot"
    ):
        packed = draws.setdefault(row["draw_date"], ["" for _ in order])
        packed[slot[row["category"]]] += row["number"]
        total += 1

    synced = conn.execute("SELECT value FROM meta WHERE key = 'last_sync'").fetchone()

    # งวดตามปฏิทินของแต่ละวันออกรางวัล คิดฝั่ง Python ที่เดียว หน้าเว็บแค่เอาไปใช้
    periods = {date: schedule.period_of(date) for date in draws}
    notes = {
        date: schedule.shift_reason(date) for date in draws if schedule.is_shifted(date)
    }

    return {
        "tiers": [
            {
                "key": c.key,
                "label": c.th,
                "digits": c.digits,
                "match": c.match,
            }
            for c in sorted(model.CATEGORIES, key=lambda c: c.order)
        ],
        "tier_groups": [list(row) for row in queries.MATRIX_GROUPS],
        "draws": dict(sorted(draws.items())),
        "periods": periods,
        "shift_notes": notes,
        "cancelled": dict(sorted(schedule.CANCELLED.items())),
        "prize_count": total,
        "synced_at": (synced["value"][:10] if synced else None),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None, help="ที่เก็บไฟล์ฐานข้อมูล")
    parser.add_argument("--out", default=str(Path(__file__).with_name("lotto-page.html")))
    args = parser.parse_args()

    stats = build(args.db, Path(args.out))
    print(
        f"เขียน {args.out}\n"
        f"  {stats['draws']:,} งวด · {stats['prizes']:,} เลขรางวัล\n"
        f"  ข้อมูล {stats['data_kb']:,} KB · หน้าเว็บรวม {stats['page_kb']:,} KB"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
