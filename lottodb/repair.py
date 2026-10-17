"""ซ่อมข้อมูลที่เสียจากคลังหลัก และเก็บ "เงินรางวัลจริง" ของแต่ละยุค

คลังย้อนหลังที่ใช้เป็นแหล่งหลักเกิดจากการ scrape เว็บข่าว จึงมีบางงวดที่ข้อมูล
ขาดหรือปนกับงวดอื่น โมดูลนี้ดึงงวดนั้นใหม่จาก sanook แล้วเขียนทับให้
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
import time

from . import queries, sanook, store

POLITE_DELAY = 1.2  # วินาที ระหว่างการยิงแต่ละครั้ง


def problem_draws(conn: sqlite3.Connection) -> list[dict]:
    """งวดที่ติดธงระดับ "ปัญหา" (ข้อสังเกตเรื่องเลขซ้ำไม่นับ)"""
    return [r for r in queries.anomalies(conn) if "ปัญหา:" in (r["anomalies"] or "")]


def repair_draw(
    conn: sqlite3.Connection,
    iso_date: str,
    *,
    replaces: str | None = None,
) -> dict:
    """ดึงงวด `iso_date` จาก sanook มาเขียนทับ  `replaces` = งวดผิดวันที่ให้ลบทิ้ง"""
    draw = sanook.fetch_draw(iso_date)
    action = store.upsert_draw(conn, draw)
    dropped = False
    if replaces and replaces != iso_date:
        cur = conn.execute("DELETE FROM draws WHERE draw_date = ?", (replaces,))
        dropped = cur.rowcount > 0
        conn.execute(
            "INSERT INTO corrections (bad_date, good_date, reason, noted_at)"
            " VALUES (?,?,?,?) ON CONFLICT(bad_date) DO UPDATE SET"
            "   good_date = excluded.good_date, noted_at = excluded.noted_at",
            (
                replaces,
                iso_date,
                "คลังต้นทางลงวันออกรางวัลผิด และข้อมูลปนกับงวดอื่น",
                _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            ),
        )
    conn.commit()
    return {
        "draw_date": iso_date,
        "action": action,
        "prize_count": draw.prize_count,
        "anomalies": draw.anomalies,
        "dropped": replaces if dropped else None,
    }


def repair_flagged(
    conn: sqlite3.Connection,
    *,
    shift_days: int = 3,
    log=print,
) -> list[dict]:
    """ซ่อมทุกงวดที่ติดธงปัญหา

    ถ้า sanook ไม่มีหน้าของวันที่นั้น จะลองวันใกล้เคียง ±shift_days เพราะสาเหตุ
    ที่พบจริงคือคลังหลักบันทึกวันออกรางวัลผิดไปหนึ่งวัน
    """
    results: list[dict] = []
    for row in problem_draws(conn):
        bad_date = row["draw_date"]
        log(f"ซ่อม {bad_date} ({row['draw_date_th']}) …")
        for candidate, replaces in _candidates(conn, bad_date, shift_days):
            try:
                outcome = repair_draw(conn, candidate, replaces=replaces)
            except LookupError:
                continue
            if candidate != bad_date:
                log(f"   วันที่ถูกต้องคือ {candidate} — ย้ายข้อมูลและลบ {bad_date}")
            log(f"   {outcome['action']}  {outcome['prize_count']} รางวัล")
            results.append(outcome)
            time.sleep(POLITE_DELAY)
            break
        else:
            log("   sanook ไม่มีงวดนี้ให้ดึงมาแทน — ต้องแก้มือ")
            results.append({"draw_date": bad_date, "action": "failed"})
    return results


def _candidates(conn: sqlite3.Connection, iso_date: str, shift_days: int):
    """วันที่ที่ควรลอง: วันเดิมก่อน แล้วค่อยไล่วันใกล้เคียงที่ยังไม่มีในฐานข้อมูล"""
    yield iso_date, iso_date
    base = _dt.date.fromisoformat(iso_date)
    for offset in range(1, shift_days + 1):
        for delta in (offset, -offset):
            other = (base + _dt.timedelta(days=delta)).isoformat()
            exists = conn.execute(
                "SELECT 1 FROM draws WHERE draw_date = ?", (other,)
            ).fetchone()
            if not exists:
                yield other, iso_date
