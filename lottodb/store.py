"""สร้าง/ปรับปรุงฐานข้อมูล SQLite"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path

from . import model, sources, thaidate
from .parse import Draw

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB = Path(__file__).resolve().parent.parent / "lotto.db"

# ลำดับความน่าเชื่อถือของแหล่งข้อมูล — ตัวเลขสูงกว่าชนะเมื่อข้อมูลขัดกัน
SOURCE_RANK = {"archive": 1, "sanook": 2, "glo-api": 3}


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def _existing(conn: sqlite3.Connection, draw_date: str) -> tuple[str, dict[str, list[str]]] | None:
    row = conn.execute("SELECT source FROM draws WHERE draw_date = ?", (draw_date,)).fetchone()
    if row is None:
        return None
    nums: dict[str, list[str]] = {}
    for r in conn.execute(
        "SELECT category, number FROM prizes WHERE draw_date = ? ORDER BY category, slot",
        (draw_date,),
    ):
        nums.setdefault(r["category"], []).append(r["number"])
    return row["source"], nums


def upsert_draw(conn: sqlite3.Connection, draw: Draw) -> str:
    """คืนค่า 'new' | 'updated' | 'unchanged' | 'kept-better-source'"""
    incoming = {k: sorted(v) for k, v in draw.numbers.items() if v}
    prior = _existing(conn, draw.draw_date)

    if prior is not None:
        prior_source, prior_nums = prior
        prior_sorted = {k: sorted(v) for k, v in prior_nums.items() if v}
        if prior_sorted == incoming:
            # เลขเหมือนเดิม แต่ข้อความตรวจสอบอาจเปลี่ยนไปตามเวอร์ชันโปรแกรม
            conn.execute(
                "UPDATE draws SET anomalies = ?, source_url = COALESCE(?, source_url),"
                " draw_date_th = ?, prize_count = ? WHERE draw_date = ?",
                (
                    "; ".join(draw.anomalies) or None,
                    draw.source_url,
                    thaidate.to_thai(draw.draw_date),
                    draw.prize_count,
                    draw.draw_date,
                ),
            )
            return "unchanged"
        if SOURCE_RANK.get(prior_source, 0) > SOURCE_RANK.get(draw.source, 0):
            _flag(
                conn,
                draw.draw_date,
                f"ข้อมูลจาก {draw.source} ไม่ตรงกับ {prior_source} ที่เก็บไว้ (ยึด {prior_source})",
            )
            return "kept-better-source"

    conn.execute("DELETE FROM prizes WHERE draw_date = ?", (draw.draw_date,))
    conn.execute(
        "INSERT INTO draws (draw_date, draw_date_th, ruleset, source, source_url,"
        " prize_count, anomalies, updated_at) VALUES (?,?,?,?,?,?,?,?)"
        " ON CONFLICT(draw_date) DO UPDATE SET"
        "   draw_date_th = excluded.draw_date_th, ruleset = excluded.ruleset,"
        "   source = excluded.source, source_url = excluded.source_url,"
        "   prize_count = excluded.prize_count, anomalies = excluded.anomalies,"
        "   updated_at = excluded.updated_at",
        (
            draw.draw_date,
            thaidate.to_thai(draw.draw_date),
            draw.ruleset,
            draw.source,
            draw.source_url,
            draw.prize_count,
            "; ".join(draw.anomalies) or None,
            _now(),
        ),
    )
    conn.executemany(
        "INSERT INTO prizes (draw_date, category, slot, number, digits) VALUES (?,?,?,?,?)",
        [
            (draw.draw_date, key, slot, number, model.BY_KEY[key].digits)
            for key in model.ORDERED_KEYS
            for slot, number in enumerate(draw.numbers.get(key, []), start=1)
        ],
    )
    return "new" if prior is None else "updated"


def _flag(conn: sqlite3.Connection, draw_date: str, message: str) -> None:
    """ต่อข้อความเตือนเข้าไปในคอลัมน์ anomalies ของงวดนั้น โดยไม่ซ้ำ"""
    row = conn.execute("SELECT anomalies FROM draws WHERE draw_date = ?", (draw_date,)).fetchone()
    parts = [p for p in (row["anomalies"] or "").split("; ") if p and p != message] if row else []
    parts.append(message)
    conn.execute("UPDATE draws SET anomalies = ? WHERE draw_date = ?", ("; ".join(parts), draw_date))


def sync(
    conn: sqlite3.Connection,
    *,
    archive: bool = True,
    glo: bool = True,
    work_dir: Path | None = None,
) -> dict[str, dict[str, int]]:
    init(conn)
    report: dict[str, dict[str, int]] = {}

    if archive:
        draws = sources.fetch_archive(work_dir=work_dir)
        report["archive"] = _apply(conn, draws, "archive")

    if glo:
        latest = sources.fetch_glo_latest()
        report["glo-api"] = _apply(conn, [latest], "glo-api")

    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('last_sync', ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (_now(),),
    )
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('sources', ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (json.dumps({"archive": sources.ARCHIVE_CREDIT, "glo": sources.GLO_LATEST}, ensure_ascii=False),),
    )
    conn.commit()
    return report


def _apply(conn: sqlite3.Connection, draws: list[Draw], source: str) -> dict[str, int]:
    tally = {"new": 0, "updated": 0, "unchanged": 0, "kept-better-source": 0, "skipped": 0}
    corrected = {
        r["bad_date"] for r in conn.execute("SELECT bad_date FROM corrections")
    }
    for draw in draws:
        if draw.draw_date in corrected:
            tally["skipped"] += 1  # งวดที่ต้นทางลงวันที่ผิด แก้ไว้แล้ว
            continue
        tally[upsert_draw(conn, draw)] += 1
    conn.execute(
        "INSERT INTO sync_log (ran_at, source, draws_new, draws_upd, detail) VALUES (?,?,?,?,?)",
        (_now(), source, tally["new"], tally["updated"], json.dumps(tally, ensure_ascii=False)),
    )
    conn.commit()
    return tally


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")
