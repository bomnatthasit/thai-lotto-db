#!/usr/bin/env python3
"""เทียบ "เลขในปฏิทินช่อง 3" กับผลรางวัลจริงของงวดนั้น แบบไขว้เลขได้

เลขในปฏิทินอ่านด้วยตาจากภาพสแกน (เขียนมือ วางแนวตั้ง) จึงต้องถือว่าเป็นค่าที่
ยืนยันด้วยสายตา ไม่ใช่ข้อมูลทางการ — แก้ได้ในตาราง CALENDAR ด้านล่าง

สิ่งที่สคริปต์นี้ตอบ
    1. งวดไหนบ้างที่เลขในปฏิทิน "ไขว้แล้วตรง" กับรางวัล
    2. ตรงบ่อยกว่าการเดาสุ่มหรือไม่ — เพราะเลข 4-5 หลักไขว้ได้หลายสิบแบบ
       โอกาสตรงโดยบังเอิญจึงสูงมาก ถ้าไม่เทียบกับค่าคาด ตัวเลขจะหลอกตาทันที
"""

from __future__ import annotations

import argparse
import sys
from itertools import permutations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lottodb import store, thaidate  # noqa: E402

# วันออกรางวัล -> เลขที่เขียนไว้ในช่องปฏิทินของวันนั้น (None = ช่องนั้นไม่มีเลข)
CALENDAR: dict[str, str | None] = {
    "2026-01-02": None,
    "2026-01-17": "7602",
    "2026-02-01": "5027",
    "2026-02-16": "7506",
    "2026-03-01": "3301",
    "2026-03-16": "6339",
    "2026-04-01": "25891",
    "2026-04-16": "7805",
    "2026-05-02": "1330",
    "2026-05-16": "7589",
    "2026-06-01": "2741",
    "2026-06-16": "6788",
    "2026-07-01": "1887",
    "2026-07-16": "7059",
    "2026-08-01": "7824",
    "2026-08-16": "3072",
    "2026-09-01": "9674",
    "2026-09-16": "8216",
    "2026-10-01": "27803",
    "2026-10-16": "7153",
}

# หมวดที่เอามาเทียบ: (คีย์, ชื่อ, จำนวนหลัก)
TARGETS = [
    ("last2", "เลขท้าย 2 ตัว", 2),
    ("front3", "เลขหน้า 3 ตัว", 3),
    ("back3", "เลขท้าย 3 ตัว", 3),
]


def cross(digits: str, size: int) -> set[str]:
    """ชุดเลขทั้งหมดที่ไขว้ได้จากเลขในปฏิทิน (ไม่ซ้ำ)"""
    return {"".join(p) for p in permutations(digits, size)}


def prize_numbers(conn, draw_date: str, category: str) -> list[str]:
    return [
        r["number"]
        for r in conn.execute(
            "SELECT number FROM prizes WHERE draw_date = ? AND category = ? ORDER BY slot",
            (draw_date, category),
        )
    ]


def analyse(conn) -> dict:
    rows = []
    for draw_date, calnum in sorted(CALENDAR.items()):
        if calnum is None:
            rows.append({"date": draw_date, "calnum": None})
            continue
        if not conn.execute(
            "SELECT 1 FROM draws WHERE draw_date = ?", (draw_date,)
        ).fetchone():
            continue  # ยังไม่ออกรางวัล

        entry = {"date": draw_date, "calnum": calnum, "hits": {}, "chance": {}}
        for key, label, size in TARGETS:
            pool = cross(calnum, size)
            actual = prize_numbers(conn, draw_date, key)
            matched = [n for n in actual if n in pool]
            entry["hits"][key] = matched
            # โอกาสตรงโดยบังเอิญ: ชุดที่ไขว้ได้ / เลขทั้งหมด แล้วคิดรวมทุกรางวัลในหมวด
            p_one = len(pool) / (10 ** size)
            entry["chance"][key] = 1 - (1 - p_one) ** max(len(actual), 1)
            entry.setdefault("pool_size", {})[key] = len(pool)
        rows.append(entry)
    return {"rows": rows}


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None)
    args = parser.parse_args()

    conn = store.connect(args.db)
    try:
        data = analyse(conn)
    finally:
        conn.close()

    graded = [r for r in data["rows"] if r.get("calnum") and "hits" in r]
    print("เทียบเลขในปฏิทินช่อง 3 กับผลรางวัลจริง (ไขว้เลขได้)\n")
    print(f"{'งวด':<22} {'เลขปฏิทิน':<9} {'ท้าย 2 ตัว':<14} {'หน้า 3 ตัว':<16} {'ท้าย 3 ตัว':<16}")
    print("-" * 84)

    for r in graded:
        cells = []
        for key, _label, _size in TARGETS:
            hit = r["hits"][key]
            cells.append(("✓ " + " ".join(hit)) if hit else "—")
        print(
            f"{thaidate.to_thai(r['date']):<22} {r['calnum']:<9}"
            f" {cells[0]:<14} {cells[1]:<16} {cells[2]:<16}"
        )

    print("\n" + "=" * 84)
    print("สรุป — เทียบกับค่าคาดถ้าเลขในปฏิทินไม่มีความหมายอะไรเลย\n")
    print(f"{'หมวด':<16} {'ตรงจริง':>9} {'ค่าคาด':>10} {'ชุดไขว้เฉลี่ย':>16} {'โอกาสต่องวดเฉลี่ย':>20}")
    print("-" * 84)

    for key, label, size in TARGETS:
        observed = sum(1 for r in graded if r["hits"][key])
        expected = sum(r["chance"][key] for r in graded)
        pool = sum(r["pool_size"][key] for r in graded) / len(graded)
        avg_chance = expected / len(graded)
        print(
            f"{label:<16} {observed:>6} งวด {expected:>9.1f} {pool:>13.0f} แบบ"
            f" {avg_chance * 100:>17.1f}%"
        )

    total_obs = sum(1 for r in graded if any(r["hits"][k] for k, _, _ in TARGETS))
    print(f"\nงวดที่ตรงอย่างน้อยหนึ่งหมวด: {total_obs} จาก {len(graded)} งวด")
    print(
        "\nอ่านผลอย่างไร: เลข 4 หลักไขว้เป็นเลข 2 ตัวได้ถึง 12 แบบ และเลข 3 ตัวได้ถึง 24 แบบ"
        "\nโอกาสตรงโดยบังเอิญจึงสูงมากอยู่แล้ว ตัวเลขช่อง 'ตรงจริง' จะมีความหมาย"
        "\nก็ต่อเมื่อมันสูงกว่าช่อง 'ค่าคาด' อย่างชัดเจนเท่านั้น"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
