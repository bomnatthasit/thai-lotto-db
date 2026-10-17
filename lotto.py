#!/usr/bin/env python3
"""ฐานข้อมูลผลสลากกินแบ่งรัฐบาล ย้อนหลังทุกงวด ทุกรางวัล

ตัวอย่าง
    python lotto.py sync                  สร้าง/อัปเดตฐานข้อมูล
    python lotto.py info                  ดูภาพรวมฐานข้อมูล
    python lotto.py draw 16/10/2569       ดูผลรางวัลทั้งงวด
    python lotto.py check 011781          ตรวจสลากกับงวดล่าสุด
    python lotto.py history 011781        ย้อนดูว่าเลขนี้เคยถูกงวดไหนมาแล้ว
    python lotto.py search "*781"         ค้นเลขรางวัลด้วยรูปแบบ
    python lotto.py freq last2 --top 10   เลขท้าย 2 ตัว ที่ออกบ่อยสุด
    python lotto.py matrix last2          ตารางเทียบเลขท้าย 2 ตัว รายเดือนทุกปี
    python lotto.py serve                 เปิดหน้าเว็บดูย้อนหลังที่เครื่องตัวเอง
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lottodb import model, queries, store, thaidate  # noqa: E402


def _utf8_stdout() -> None:
    """คอนโซล Windows ปริยายเป็น cp874/cp1252 ทำให้ภาษาไทยเพี้ยน"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def resolve_date(conn: sqlite3.Connection, text: str | None) -> str:
    if text is None or text in {"latest", "ล่าสุด"}:
        row = conn.execute("SELECT MAX(draw_date) AS d FROM draws").fetchone()
        if not row or not row["d"]:
            raise SystemExit("ฐานข้อมูลยังว่าง — สั่ง `python lotto.py sync` ก่อน")
        return row["d"]
    return thaidate.parse(text)


def clean_ticket(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 6:
        raise SystemExit(f"เลขสลากต้องมี 6 หลัก (ได้ {raw!r} -> {digits!r})")
    return digits


# ---------------------------------------------------------------- commands


def cmd_sync(args, conn: sqlite3.Connection) -> int:
    print("กำลังดึงข้อมูล…")
    report = store.sync(conn, archive=not args.no_archive, glo=not args.no_glo)
    for source, tally in report.items():
        print(
            f"  {source:9s} ใหม่ {tally['new']:4d}  แก้ไข {tally['updated']:4d}"
            f"  เท่าเดิม {tally['unchanged']:4d}  คงของเดิม {tally['kept-better-source']:3d}"
        )
    info = queries.summary(conn)
    print(
        f"\nรวม {info['draws']:,} งวด  ({info['first_date']} ถึง {info['last_date']})"
        f"  เลขรางวัล {info['prizes']:,} รายการ"
    )
    if info["flagged"]:
        print(
            f"มี {info['flagged']} งวดที่ข้อมูลไม่ครบ — ดูด้วย `python lotto.py doctor`"
            " แล้วซ่อมด้วย `python lotto.py repair --auto`"
        )
    return 0


def cmd_info(args, conn: sqlite3.Connection) -> int:
    info = queries.summary(conn)
    if not info["draws"]:
        print("ฐานข้อมูลยังว่าง — สั่ง `python lotto.py sync` ก่อน")
        return 1
    print("ฐานข้อมูลผลสลากกินแบ่งรัฐบาล")
    print(f"  งวดทั้งหมด      {info['draws']:,}")
    print(
        f"  ช่วงข้อมูล       {thaidate.to_thai(info['first_date'])}"
        f"  ถึง  {thaidate.to_thai(info['last_date'])}"
    )
    print(f"  เลขรางวัล        {info['prizes']:,} รายการ")
    print(f"  ซิงก์ล่าสุด       {info['last_sync'] or '-'}")
    print(f"  งวดข้อมูลไม่ครบ   {info['flagged']}")
    print(f"  งวดมีข้อสังเกต    {info['noted']}")
    print("\nจำนวนงวดต่อปี (ค.ศ.)")
    rows = queries.years(conn)
    line = "  "
    for i, r in enumerate(rows, start=1):
        line += f"{r['year']}:{r['draws']:>3}   "
        if i % 6 == 0:
            print(line.rstrip())
            line = "  "
    if line.strip():
        print(line.rstrip())
    return 0


def cmd_draw(args, conn: sqlite3.Connection) -> int:
    date = resolve_date(conn, args.date)
    result = queries.get_draw(conn, date)
    if result is None:
        print(f"ไม่มีงวดวันที่ {thaidate.to_thai(date)} ในฐานข้อมูล")
        return 1
    head = result["draw"]
    print(f"ผลสลากกินแบ่งรัฐบาล งวดวันที่ {head['draw_date_th']}  ({head['draw_date']})")
    print(f"แหล่งข้อมูล: {head['source']}   รางวัลรวม {head['prize_count']} รายการ")
    if head["anomalies"]:
        print(f"หมายเหตุ: {head['anomalies']}")
    print()
    for group in result["groups"]:
        print(f"{group['label']}  ({group['count']} รางวัล)")
        nums = group["numbers"]
        per_line = 10 if group["count"] > 10 else len(nums)
        for i in range(0, len(nums), per_line):
            print("   " + "  ".join(nums[i : i + per_line]))
        print()
    return 0


def cmd_check(args, conn: sqlite3.Connection) -> int:
    date = resolve_date(conn, args.date)
    for raw in args.numbers:
        ticket = clean_ticket(raw)
        result = queries.check_ticket(conn, ticket, date)
        if result is None:
            print(f"ไม่มีงวดวันที่ {thaidate.to_thai(date)} ในฐานข้อมูล")
            return 1
        print(f"สลาก {ticket}  งวด {result['draw']['draw_date_th']}")
        if not result["wins"]:
            print("   ไม่ถูกรางวัล\n")
            continue
        for win in result["wins"]:
            print(f"   ถูก {win['label']}  (เลข {win['number']})")
        print()
    return 0


def cmd_history(args, conn: sqlite3.Connection) -> int:
    ticket = clean_ticket(args.number)
    rows = queries.history(conn, ticket)
    info = queries.summary(conn)
    print(f"ย้อนดูเลข {ticket} เทียบกับ {info['draws']:,} งวดในฐานข้อมูล")
    if not rows:
        print("   ไม่เคยถูกรางวัลเลยแม้แต่งวดเดียว")
        return 0
    for row in rows:
        labels = ", ".join(f"{w['label']} ({w['number']})" for w in row["wins"])
        print(f"   {row['draw_date']}  {row['draw_date_th']:<22} {labels}")
    print(f"\n   ถูกรางวัล {len(rows)} งวด")
    print(f"   คิดเป็น {len(rows) / info['draws'] * 100:.1f}% ของงวดทั้งหมด")
    return 0


def cmd_search(args, conn: sqlite3.Connection) -> int:
    rows = queries.search(conn, args.pattern, category=args.category, limit=args.limit)
    if not rows:
        print("ไม่พบเลขที่ตรงรูปแบบนี้")
        return 1
    print(f"พบ {len(rows)} รายการ (รูปแบบ {args.pattern})")
    for r in rows:
        print(f"   {r['draw_date']}  {r['draw_date_th']:<22} {r['label']:<28} {r['number']}")
    return 0


def cmd_freq(args, conn: sqlite3.Connection) -> int:
    since = thaidate.parse(args.since) if args.since else None
    until = thaidate.parse(args.until) if args.until else None
    rows = queries.frequency(
        conn, args.category, since=since, until=until, top=args.top, ascending=args.low
    )
    label = model.BY_KEY[args.category].th
    scope = f" ช่วง {since or 'เริ่มต้น'} ถึง {until or 'ล่าสุด'}" if (since or until) else ""
    print(f"{'ออกน้อยสุด' if args.low else 'ออกบ่อยสุด'} — {label}{scope}")
    for i, r in enumerate(rows, start=1):
        print(
            f"   {i:2d}. {r['number']:<7} ออก {r['hits']:3d} ครั้ง"
            f"   ครั้งแรก {r['first_seen']}  ล่าสุด {r['last_seen']}"
        )
    return 0


def cmd_gaps(args, conn: sqlite3.Connection) -> int:
    rows = queries.gaps(conn, args.category, top=args.top)
    print(f"หายไปนานสุด — {model.BY_KEY[args.category].th}")
    for i, r in enumerate(rows, start=1):
        print(
            f"   {i:2d}. {r['number']:<7} ไม่ออกมาแล้ว {r['draws_since']:3d} งวด"
            f"   (ล่าสุด {r['last_seen']}, เคยออก {r['hits']} ครั้ง)"
        )
    return 0


def cmd_never(args, conn: sqlite3.Connection) -> int:
    nums = queries.never_drawn(conn, args.category)
    label = model.BY_KEY[args.category].th
    total = 10 ** model.BY_KEY[args.category].digits
    print(f"{label}: ยังไม่เคยออก {len(nums)} จาก {total} เลข")
    for i in range(0, len(nums), 15):
        print("   " + " ".join(nums[i : i + 15]))
    return 0


def cmd_draws(args, conn: sqlite3.Connection) -> int:
    rows = queries.list_draws(conn, year=args.year, limit=args.limit, offset=args.offset)
    print(f"{'วันที่':<12} {'งวด':<24} {'รางวัลที่ 1':<12} {'ท้าย 2 ตัว':<10} แหล่ง")
    for r in rows:
        flag = " *" if r["anomalies"] else ""
        print(
            f"{r['draw_date']:<12} {r['draw_date_th']:<24} {r['first_prize'] or '-':<12}"
            f" {r['last2'] or '-':<10} {r['source']}{flag}"
        )
    return 0


def cmd_doctor(args, conn: sqlite3.Connection) -> int:
    rows = queries.anomalies(conn)
    problems = [r for r in rows if "ปัญหา:" in (r["anomalies"] or "")]
    notes = [r for r in rows if r not in problems]

    if problems:
        print(f"ปัญหา — ข้อมูลไม่ครบ {len(problems)} งวด (ซ่อมด้วย `python lotto.py repair --auto`)")
        for r in problems:
            detail = r["anomalies"]
            if len(detail) > 160:
                detail = detail[:157] + "…"
            print(f"   {r['draw_date']}  ({r['prize_count']} รางวัล, {r['source']})  {detail}")
    else:
        print("ไม่มีงวดที่ข้อมูลขาด — ทุกงวดมีรางวัลครบ 173 รายการ")

    if notes:
        print(f"\nข้อสังเกต {len(notes)} งวด (ไม่ใช่ข้อมูลผิด — เลขซ้ำในหมวดเดียวกันเกิดขึ้นได้จริง)")
        for r in notes:
            print(f"   {r['draw_date']}  {r['anomalies']}")
    return 1 if problems else 0


def cmd_repair(args, conn: sqlite3.Connection) -> int:
    from lottodb import repair

    if args.auto:
        results = repair.repair_flagged(conn, shift_days=args.shift)
        if not results:
            print("ไม่มีงวดที่ต้องซ่อม")
            return 0
        failed = [r for r in results if r["action"] == "failed"]
        print(f"\nซ่อมสำเร็จ {len(results) - len(failed)} งวด  ไม่สำเร็จ {len(failed)} งวด")
        return 1 if failed else 0

    if not args.date:
        print("ระบุวันที่ หรือใช้ --auto")
        return 2
    date = thaidate.parse(args.date)
    replaces = thaidate.parse(args.replaces) if args.replaces else None
    try:
        outcome = repair.repair_draw(conn, date, replaces=replaces)
    except LookupError as exc:
        print(exc)
        return 1
    print(f"{date}: {outcome['action']}  {outcome['prize_count']} รางวัล")
    if outcome["dropped"]:
        print(f"   ลบงวดวันที่ผิด {outcome['dropped']} ออกแล้ว")
    for note in outcome["anomalies"]:
        print(f"   {note}")
    return 0


MONTHS_ABBR = ("ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.")


def cmd_matrix(args, conn: sqlite3.Connection) -> int:
    """ตารางเทียบ ปี × เดือน ของหมวดรางวัลเดียว"""
    data = queries.monthly_matrix(conn, args.category, half=args.half)
    half_note = {"all": "ทุกงวด", "early": "เฉพาะงวดวันที่ 1-10", "late": "เฉพาะงวดวันที่ 11 ขึ้นไป"}[args.half]
    print(f"{data['label']} — เทียบรายเดือนทุกปี ({half_note})\n")

    table = [
        (
            year["year_be"],
            ["/".join(_cell(d, data["digits"]) for d in draws) for draws in year["months"]],
        )
        for year in data["years"]
    ]
    # ต้องกว้างพอทั้งเนื้อหาในช่องและชื่อเดือนที่เป็นหัวตาราง
    width = max(
        max((len(c) for _, cells in table for c in cells), default=0),
        max(len(m) for m in MONTHS_ABBR),
    ) + 2

    print("ปี    " + "".join(f"{m:<{width}}" for m in MONTHS_ABBR))
    print("-" * (6 + width * 12))
    for year_be, cells in table:
        print(f"{year_be:<6}" + "".join(f"{c:<{width}}" for c in cells))
    print(f"\n{len(data['years'])} ปี  ·  ช่องว่าง = ไม่มีงวดในเดือนนั้น")
    if args.half == "all":
        print("ในช่องที่มีสองงวด เรียงตามวันที่ออกรางวัล คั่นด้วย /")
    return 0


def _cell(draw: dict, digits: int) -> str:
    return " ".join(draw["numbers"]) if digits < 6 else draw["numbers"][0]


def cmd_drop(args, conn: sqlite3.Connection) -> int:
    date = thaidate.parse(args.date)
    cur = conn.execute("DELETE FROM draws WHERE draw_date = ?", (date,))
    conn.commit()
    print(f"ลบงวด {date} แล้ว" if cur.rowcount else f"ไม่มีงวด {date} ในฐานข้อมูล")
    return 0 if cur.rowcount else 1


def cmd_export(args, conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT p.draw_date, d.draw_date_th, p.category, p.slot, p.number"
        " FROM prizes p JOIN draws d ON d.draw_date = p.draw_date"
        " ORDER BY p.draw_date DESC, p.category, p.slot"
    ).fetchall()
    out = Path(args.out)
    if args.format == "json":
        payload = [dict(r) for r in rows]
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        with out.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["draw_date", "draw_date_th", "category", "slot", "number"])
            writer.writerows([tuple(r) for r in rows])
    print(f"เขียน {len(rows):,} แถวไปที่ {out}")
    return 0


def cmd_serve(args, conn: sqlite3.Connection) -> int:
    conn.close()
    from lottodb import web

    web.serve(db_path=args.db, host=args.host, port=args.port, open_browser=not args.no_browser)
    return 0


# ---------------------------------------------------------------- wiring

CATEGORY_CHOICES = [c.key for c in model.CATEGORIES]
SMALL_CATEGORIES = ["last2", "front3", "back3"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lotto",
        description="ฐานข้อมูลผลสลากกินแบ่งรัฐบาล ย้อนหลังทุกงวด ทุกรางวัล",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--db", default=str(store.DEFAULT_DB), help="ที่เก็บไฟล์ฐานข้อมูล")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sync", help="ดึงข้อมูลเข้าฐานข้อมูล")
    p.add_argument("--no-archive", action="store_true", help="ไม่ดึงคลังย้อนหลัง")
    p.add_argument("--no-glo", action="store_true", help="ไม่ดึงงวดล่าสุดจาก API สำนักงานสลากฯ")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("info", help="ภาพรวมฐานข้อมูล")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("draw", help="ผลรางวัลทั้งงวด")
    p.add_argument("date", nargs="?", help="เช่น 16/10/2569, 2026-10-16, '16 ต.ค. 69' (ว่าง = ล่าสุด)")
    p.set_defaults(func=cmd_draw)

    p = sub.add_parser("check", help="ตรวจสลากกับงวดหนึ่ง")
    p.add_argument("numbers", nargs="+", help="เลขสลาก 6 หลัก")
    p.add_argument("--date", help="งวดที่ต้องการตรวจ (ว่าง = ล่าสุด)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("history", help="ย้อนดูว่าเลขนี้เคยถูกงวดไหน")
    p.add_argument("number", help="เลขสลาก 6 หลัก")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("search", help="ค้นเลขรางวัลด้วยรูปแบบ (? = 1 หลัก, * = กี่หลักก็ได้)")
    p.add_argument("pattern")
    p.add_argument("--category", choices=CATEGORY_CHOICES)
    p.add_argument("--limit", type=int, default=200)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("freq", help="ความถี่ของเลขในหมวดหนึ่ง")
    p.add_argument("category", choices=CATEGORY_CHOICES, default="last2", nargs="?")
    p.add_argument("--since")
    p.add_argument("--until")
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--low", action="store_true", help="เรียงจากออกน้อยสุด")
    p.set_defaults(func=cmd_freq)

    p = sub.add_parser("gaps", help="เลขที่หายไปนานสุด")
    p.add_argument("category", choices=SMALL_CATEGORIES, default="last2", nargs="?")
    p.add_argument("--top", type=int, default=20)
    p.set_defaults(func=cmd_gaps)

    p = sub.add_parser("never", help="เลขที่ยังไม่เคยออกเลย")
    p.add_argument("category", choices=SMALL_CATEGORIES, default="last2", nargs="?")
    p.set_defaults(func=cmd_never)

    p = sub.add_parser("draws", help="รายการงวด")
    p.add_argument("--year", type=int, help="ปี ค.ศ.")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--offset", type=int, default=0)
    p.set_defaults(func=cmd_draws)

    p = sub.add_parser("doctor", help="ตรวจความครบถ้วนของข้อมูล")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("repair", help="ดึงงวดที่ข้อมูลเสียมาใหม่จาก sanook")
    p.add_argument("date", nargs="?", help="งวดที่ต้องการดึงใหม่")
    p.add_argument("--auto", action="store_true", help="ซ่อมทุกงวดที่ติดธงปัญหา")
    p.add_argument("--replaces", help="ลบงวดวันที่ผิดนี้ออกหลังดึงสำเร็จ")
    p.add_argument("--shift", type=int, default=3, help="ลองวันใกล้เคียงกี่วัน (โหมด --auto)")
    p.set_defaults(func=cmd_repair)

    p = sub.add_parser("matrix", help="ตารางเทียบรายเดือนทุกปี")
    p.add_argument(
        "category",
        choices=list(queries.MATRIX_CATEGORIES),
        default="last2",
        nargs="?",
        help="first = รางวัลที่ 1, front3 = เลขหน้า 3 ตัว, back3 = เลขท้าย 3 ตัว, last2 = เลขท้าย 2 ตัว",
    )
    p.add_argument(
        "--half",
        choices=["all", "early", "late"],
        default="all",
        help="all = ทุกงวด, early = งวดวันที่ 1-10, late = งวดวันที่ 11 ขึ้นไป",
    )
    p.set_defaults(func=cmd_matrix)

    p = sub.add_parser("drop", help="ลบงวดหนึ่งออกจากฐานข้อมูล")
    p.add_argument("date")
    p.set_defaults(func=cmd_drop)

    p = sub.add_parser("export", help="ส่งออกเป็น CSV หรือ JSON")
    p.add_argument("--format", choices=["csv", "json"], default="csv")
    p.add_argument("--out", default="lotto-export.csv")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("serve", help="เปิดหน้าเว็บย้อนดูผลรางวัลที่เครื่องตัวเอง")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8777)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    args = build_parser().parse_args(argv)
    conn = store.connect(args.db)
    try:
        if args.command != "sync":
            store.init(conn)
        return args.func(args, conn)
    finally:
        try:
            conn.close()
        except sqlite3.ProgrammingError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
