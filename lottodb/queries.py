"""คำถามที่ใช้บ่อย — ย้อนดูผลรางวัล ตรวจสลาก ค้นเลข เทียบรายเดือน สถิติ"""

from __future__ import annotations

import sqlite3

from . import model, schedule, thaidate

# เทียบรายเดือนได้ทุกหมวด จัดปุ่มเป็นแถวตามชนิดรางวัล
MATRIX_GROUPS: tuple[tuple[str, ...], ...] = (
    ("first", "second", "third", "fourth", "fifth", "near1"),
    ("front3", "back3"),
    ("last2",),
)
MATRIX_CATEGORIES: tuple[str, ...] = tuple(k for row in MATRIX_GROUPS for k in row)


def summary(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) AS draws, MIN(draw_date) AS first_date, MAX(draw_date) AS last_date,"
        " SUM(prize_count) AS prizes FROM draws"
    ).fetchone()
    flagged = conn.execute(
        "SELECT COUNT(*) AS n FROM draws WHERE anomalies LIKE '%ปัญหา:%'"
    ).fetchone()["n"]
    noted = conn.execute(
        "SELECT COUNT(*) AS n FROM draws"
        " WHERE anomalies IS NOT NULL AND anomalies NOT LIKE '%ปัญหา:%'"
    ).fetchone()["n"]
    meta = {r["key"]: r["value"] for r in conn.execute("SELECT key, value FROM meta")}
    return {
        "draws": row["draws"] or 0,
        "first_date": row["first_date"],
        "last_date": row["last_date"],
        "prizes": row["prizes"] or 0,
        "flagged": flagged,
        "noted": noted,
        "last_sync": meta.get("last_sync"),
    }


def list_draws(
    conn: sqlite3.Connection,
    *,
    year: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    sql = (
        "SELECT d.draw_date, d.draw_date_th, d.ruleset, d.source, d.prize_count, d.anomalies,"
        " (SELECT number FROM prizes WHERE draw_date = d.draw_date AND category = 'first')"
        "   AS first_prize,"
        " (SELECT number FROM prizes WHERE draw_date = d.draw_date AND category = 'last2')"
        "   AS last2"
        " FROM draws d"
    )
    params: list = []
    if year is not None:
        sql += " WHERE substr(d.draw_date, 1, 4) = ?"
        params.append(str(year))
    sql += " ORDER BY d.draw_date DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    return [dict(r) for r in conn.execute(sql, params)]


def years(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT substr(draw_date, 1, 4) AS year, COUNT(*) AS draws FROM draws"
            " GROUP BY year ORDER BY year DESC"
        )
    ]


def get_draw(conn: sqlite3.Connection, draw_date: str) -> dict | None:
    head = conn.execute("SELECT * FROM draws WHERE draw_date = ?", (draw_date,)).fetchone()
    if head is None:
        return None
    rows = conn.execute(
        "SELECT category, slot, number FROM prizes WHERE draw_date = ?"
        " ORDER BY category, slot",
        (draw_date,),
    ).fetchall()

    groups: list[dict] = []
    for key in model.ORDERED_KEYS:
        items = [r for r in rows if r["category"] == key]
        if not items:
            continue
        groups.append(
            {
                "category": key,
                "label": model.BY_KEY[key].th,
                "match": model.BY_KEY[key].match,
                "count": len(items),
                "numbers": [r["number"] for r in items],
            }
        )
    return {
        "draw": dict(head),
        "groups": groups,
        "schedule": schedule.describe(draw_date),
    }


def neighbours(conn: sqlite3.Connection, draw_date: str) -> dict:
    prev = conn.execute(
        "SELECT draw_date FROM draws WHERE draw_date < ? ORDER BY draw_date DESC LIMIT 1",
        (draw_date,),
    ).fetchone()
    nxt = conn.execute(
        "SELECT draw_date FROM draws WHERE draw_date > ? ORDER BY draw_date ASC LIMIT 1",
        (draw_date,),
    ).fetchone()
    return {"prev": prev["draw_date"] if prev else None, "next": nxt["draw_date"] if nxt else None}


# ------------------------------------------------------------ เทียบรายเดือน


def monthly_matrix(
    conn: sqlite3.Connection,
    category: str,
    *,
    slot: str = "all",
) -> dict:
    """ตารางเทียบ งวด (แถว = ปี, คอลัมน์ = เดือน) ของหมวดรางวัลหนึ่ง

    จัดตาม **งวดตามปฏิทิน** ไม่ใช่วันออกรางวัลจริง จึงได้ 2 ช่องต่อเดือนเสมอ
    งวดที่ออกคนละเดือนกับงวดของตัวเองจะมี `shifted` เป็นจริง (แสดงเป็นดอกจัน)
    และงวดที่งดจำหน่ายจะมี `cancelled` เป็นจริง

    `slot` = '1' เฉพาะงวดวันที่ 1, '16' เฉพาะงวดวันที่ 16, 'all' ทั้งคู่
    """
    if category not in MATRIX_CATEGORIES:
        raise ValueError(f"ไม่รู้จักหมวด {category}")
    if slot not in {"all", "1", "16"}:
        raise ValueError("slot ต้องเป็น all, 1 หรือ 16")

    rows = conn.execute(
        "SELECT p.draw_date, p.slot, p.number FROM prizes p"
        " WHERE p.category = ? ORDER BY p.draw_date, p.slot",
        (category,),
    ).fetchall()

    by_draw: dict[str, list[str]] = {}
    for r in rows:
        by_draw.setdefault(r["draw_date"], []).append(r["number"])

    cells: list[dict] = []
    for draw_date, numbers in by_draw.items():
        info = schedule.describe(draw_date)
        cells.append(
            {
                "period": info["period"],
                "slot": info["slot"],
                "date": draw_date,
                "day": int(draw_date[-2:]),
                "numbers": numbers,
                "shifted": info["shifted"],
                "cancelled": False,
                "note": info["reason"],
            }
        )

    covered = {c["period"][:7] for c in cells}
    for period, reason in schedule.CANCELLED.items():
        if period[:7] in covered or _in_range(conn, period):
            cells.append(
                {
                    "period": period,
                    "slot": int(period[-2:]),
                    "date": None,
                    "day": None,
                    "numbers": [],
                    "shifted": False,
                    "cancelled": True,
                    "note": reason,
                }
            )

    if slot != "all":
        cells = [c for c in cells if c["slot"] == int(slot)]

    grid: dict[int, list[list[dict]]] = {}
    for cell in cells:
        year, month = int(cell["period"][:4]), int(cell["period"][5:7])
        grid.setdefault(year, [[] for _ in range(12)])
        grid[year][month - 1].append(cell)
    for months in grid.values():
        for bucket in months:
            bucket.sort(key=lambda c: c["slot"])

    return {
        "category": category,
        "label": model.BY_KEY[category].th,
        "digits": model.BY_KEY[category].digits,
        "slot": slot,
        "shifted_count": sum(1 for c in cells if c["shifted"]),
        "cancelled_count": sum(1 for c in cells if c["cancelled"]),
        "years": [
            {"year": year, "year_be": year + 543, "months": grid[year]}
            for year in sorted(grid, reverse=True)
        ],
    }


def _in_range(conn: sqlite3.Connection, period: str) -> bool:
    row = conn.execute(
        "SELECT MIN(draw_date) AS lo, MAX(draw_date) AS hi FROM draws"
    ).fetchone()
    return bool(row["lo"]) and row["lo"] <= period <= row["hi"]


def schedule_notes(conn: sqlite3.Connection) -> list[dict]:
    """รายการงวดที่ออกคนละเดือน และงวดที่งดจำหน่าย"""
    dates = [r["draw_date"] for r in conn.execute("SELECT draw_date FROM draws ORDER BY draw_date")]
    out = [
        {
            "kind": "shifted",
            "period": schedule.period_of(d),
            "period_th": thaidate.to_thai(schedule.period_of(d)),
            "drawn_on": d,
            "drawn_on_th": thaidate.to_thai(d),
            "note": schedule.shift_reason(d),
        }
        for d in dates
        if schedule.is_shifted(d)
    ]
    out += [
        {
            "kind": "cancelled",
            "period": period,
            "period_th": thaidate.to_thai(period),
            "drawn_on": None,
            "drawn_on_th": None,
            "note": reason,
        }
        for period, reason in sorted(schedule.CANCELLED.items())
        if _in_range(conn, period)
    ]
    out.sort(key=lambda r: r["period"])
    return out


# ------------------------------------------------------------ ตรวจสลาก


def _ticket_clause(ticket: str) -> tuple[str, list[str]]:
    """เงื่อนไข SQL ที่ครอบทุกแบบการถูกรางวัลของเลขสลาก 6 หลัก"""
    return (
        "((p.digits = 6 AND p.number = ?)"
        " OR (p.category = 'front3' AND p.number = ?)"
        " OR (p.category = 'back3'  AND p.number = ?)"
        " OR (p.category = 'last2'  AND p.number = ?))",
        [ticket, ticket[:3], ticket[-3:], ticket[-2:]],
    )


def check_ticket(conn: sqlite3.Connection, ticket: str, draw_date: str) -> dict | None:
    """ตรวจสลาก 1 ใบ กับ 1 งวด — รางวัลต่างหมวดถูกซ้อนกันได้"""
    head = conn.execute("SELECT * FROM draws WHERE draw_date = ?", (draw_date,)).fetchone()
    if head is None:
        return None
    clause, params = _ticket_clause(ticket)
    rows = conn.execute(
        f"SELECT p.category, p.slot, p.number FROM prizes p"
        f" WHERE p.draw_date = ? AND {clause}",
        [draw_date, *params],
    ).fetchall()
    return {"draw": dict(head), "ticket": ticket, "wins": _as_wins(rows)}


def history(conn: sqlite3.Connection, ticket: str, *, limit: int = 1000) -> list[dict]:
    """ย้อนดูทุกงวดในฐานข้อมูลที่เลขนี้จะถูกรางวัล"""
    clause, params = _ticket_clause(ticket)
    rows = conn.execute(
        "SELECT p.draw_date, d.draw_date_th, p.category, p.slot, p.number"
        " FROM prizes p JOIN draws d ON d.draw_date = p.draw_date"
        f" WHERE {clause} ORDER BY p.draw_date DESC",
        params,
    ).fetchall()

    by_draw: dict[str, list] = {}
    labels: dict[str, str] = {}
    for r in rows:
        by_draw.setdefault(r["draw_date"], []).append(r)
        labels[r["draw_date"]] = r["draw_date_th"]

    return [
        {"draw_date": date, "draw_date_th": labels[date], "wins": _as_wins(draw_rows)}
        for date, draw_rows in list(by_draw.items())[:limit]
    ]


def _as_wins(rows) -> list[dict]:
    return [
        {
            "category": r["category"],
            "label": model.BY_KEY[r["category"]].th,
            "number": r["number"],
            "slot": r["slot"],
        }
        for r in sorted(rows, key=lambda r: (model.BY_KEY[r["category"]].order, r["slot"]))
    ]


# ------------------------------------------------------------ ค้นหา/สถิติ


def search(
    conn: sqlite3.Connection,
    pattern: str,
    *,
    category: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """ค้นเลขรางวัลด้วยรูปแบบ: ? หรือ _ แทนหนึ่งหลักใด ๆ, * หรือ % แทนกี่หลักก็ได้"""
    glob = pattern.replace("_", "?").replace("%", "*")
    sql = (
        "SELECT p.draw_date, d.draw_date_th, p.category, p.slot, p.number"
        " FROM prizes p JOIN draws d ON d.draw_date = p.draw_date"
        " WHERE p.number GLOB ?"
    )
    params: list = [glob]
    if category:
        sql += " AND p.category = ?"
        params.append(category)
    sql += " ORDER BY p.draw_date DESC, p.category, p.slot LIMIT ?"
    params.append(limit)
    return [
        {**dict(r), "label": model.BY_KEY[r["category"]].th} for r in conn.execute(sql, params)
    ]


def frequency(
    conn: sqlite3.Connection,
    category: str,
    *,
    since: str | None = None,
    until: str | None = None,
    top: int = 20,
    ascending: bool = False,
) -> list[dict]:
    """นับความถี่ของเลขในหมวดหนึ่ง (เช่น last2) ตามช่วงวันที่"""
    direction = "ASC" if ascending else "DESC"
    sql = (
        "SELECT p.number, COUNT(*) AS hits, MIN(p.draw_date) AS first_seen,"
        " MAX(p.draw_date) AS last_seen FROM prizes p WHERE p.category = ?"
    )
    params: list = [category]
    if since:
        sql += " AND p.draw_date >= ?"
        params.append(since)
    if until:
        sql += " AND p.draw_date <= ?"
        params.append(until)
    sql += f" GROUP BY p.number ORDER BY hits {direction}, p.number LIMIT ?"
    params.append(top)
    return [dict(r) for r in conn.execute(sql, params)]


def never_drawn(conn: sqlite3.Connection, category: str = "last2") -> list[str]:
    """เลขในหมวดที่ยังไม่เคยออกเลยในฐานข้อมูล (ใช้กับ last2 / front3 / back3)"""
    digits = model.BY_KEY[category].digits
    if digits > 3:
        raise ValueError("ใช้ได้กับหมวดเลข 2-3 หลักเท่านั้น")
    seen = {
        r["number"]
        for r in conn.execute("SELECT DISTINCT number FROM prizes WHERE category = ?", (category,))
    }
    return [f"{i:0{digits}d}" for i in range(10**digits) if f"{i:0{digits}d}" not in seen]


def gaps(conn: sqlite3.Connection, category: str = "last2", *, top: int = 20) -> list[dict]:
    """เลขที่หายไปนานที่สุด — นับจำนวนงวดตั้งแต่ครั้งล่าสุดที่ออก"""
    total = conn.execute("SELECT COUNT(*) AS n FROM draws").fetchone()["n"]
    rows = conn.execute(
        "SELECT p.number, MAX(p.draw_date) AS last_seen, COUNT(*) AS hits"
        " FROM prizes p WHERE p.category = ? GROUP BY p.number",
        (category,),
    ).fetchall()
    out = [
        {
            "number": r["number"],
            "last_seen": r["last_seen"],
            "draws_since": conn.execute(
                "SELECT COUNT(*) AS n FROM draws WHERE draw_date > ?", (r["last_seen"],)
            ).fetchone()["n"],
            "hits": r["hits"],
            "total_draws": total,
        }
        for r in rows
    ]
    out.sort(key=lambda x: -x["draws_since"])
    return out[:top]


def anomalies(conn: sqlite3.Connection) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            "SELECT draw_date, draw_date_th, source, prize_count, anomalies FROM draws"
            " WHERE anomalies IS NOT NULL ORDER BY draw_date DESC"
        )
    ]
