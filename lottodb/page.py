"""สร้างหน้าเว็บไฟล์เดียวที่ฝังข้อมูลทุกงวดไว้ในตัว

ใช้ร่วมกันทั้งหน้าที่ส่งต่อได้ (share/lotto-page.html) และหน้าที่ `lotto.py serve`
เปิดให้ จึงมีหน้าตาและฟีเจอร์ชุดเดียว ไม่แตกเป็นสองเวอร์ชัน
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import model, queries, schedule

TEMPLATE = Path(__file__).resolve().parent.parent / "share" / "page_template.html"
PLACEHOLDER = "__DATA__"


def collect(conn: sqlite3.Connection) -> dict:
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
    notes = {date: schedule.shift_reason(date) for date in draws if schedule.is_shifted(date)}

    return {
        "tiers": [
            {"key": c.key, "label": c.th, "digits": c.digits, "match": c.match}
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


def render(conn: sqlite3.Connection) -> str:
    payload = collect(conn)
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if PLACEHOLDER in blob:
        raise RuntimeError("ข้อมูลมีสตริงที่ชนกับ placeholder")
    if "</script" in blob.lower():
        raise RuntimeError("ข้อมูลมีสตริงที่ปิด <script> ก่อนเวลา")

    template = TEMPLATE.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise RuntimeError(f"ไม่พบ {PLACEHOLDER} ใน {TEMPLATE.name}")
    return template.replace(PLACEHOLDER, blob)


def build(conn: sqlite3.Connection, out_path: Path) -> dict:
    html = render(conn)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    info = queries.summary(conn)
    return {
        "draws": info["draws"],
        "prizes": info["prizes"],
        "page_kb": out_path.stat().st_size // 1024,
    }
