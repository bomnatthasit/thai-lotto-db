"""จับคู่ "งวด" กับ "วันออกรางวัลจริง"

สลากออกงวดละ 2 ครั้งต่อเดือน คืองวดวันที่ 1 และงวดวันที่ 16 แต่วันออกรางวัลจริง
เลื่อนได้ และบางครั้งเลื่อนข้ามเดือน ทำให้ถ้าจัดตารางตามวันออกจริง จะเห็นบางเดือน
ว่างเปล่าและบางเดือนมี 3 งวด

โมดูลนี้คืนงวด "ตามปฏิทิน" ของแต่ละวันออกรางวัล เพื่อให้ตารางเทียบรายเดือนมี
2 ช่องต่อเดือนเสมอ และติดดาวไว้ที่งวดที่ออกคนละเดือนกับงวดของตัวเอง

รูปแบบที่พบในข้อมูล 473 งวด (2549-2569)
    วันที่ 1       งวดวันที่ 1 ตามปกติ
    วันที่ 2       งวดวันที่ 1 เลื่อนไปหนึ่งวัน (1 ม.ค. วันขึ้นปีใหม่, 1 พ.ค. วันแรงงาน)
    วันที่ 15-17   งวดวันที่ 16 เลื่อนหนึ่งวัน
    วันที่ 30-31   งวดวันที่ 1 ของ "เดือนถัดไป" ออกก่อนสิ้นเดือน
"""

from __future__ import annotations

import datetime as _dt

from . import thaidate

# งวดที่เลื่อนข้ามเดือนแบบไม่เข้ากฎทั่วไป ต้องระบุเอง
# วันออกรางวัลจริง -> (งวดตามปฏิทิน, เหตุผล)
SHIFTED: dict[str, tuple[str, str]] = {
    "2020-05-16": (
        "2020-04-01",
        "เลื่อนจากงวด 1 เม.ย. 2563 เพราะการระบาดของโควิด-19 "
        "ตามประกาศสำนักงานสลากกินแบ่งรัฐบาลในราชกิจจานุเบกษา",
    ),
}

# งวดที่งดจำหน่าย จึงไม่มีการออกรางวัลเลย
# งวดตามปฏิทิน -> เหตุผล
CANCELLED: dict[str, str] = {
    "2020-04-16": "งดจำหน่ายเพราะการระบาดของโควิด-19",
    "2020-05-01": "งดจำหน่ายเพราะการระบาดของโควิด-19 (งวดนี้กำหนดออก 2 พ.ค. 2563)",
    "2020-05-16": "งดจำหน่ายเพราะการระบาดของโควิด-19",
}


def period_of(draw_date: str) -> str:
    """งวดตามปฏิทินของวันออกรางวัลนี้ คืนค่าเป็น ISO ของวันที่ 1 หรือ 16"""
    if draw_date in SHIFTED:
        return SHIFTED[draw_date][0]

    date = _dt.date.fromisoformat(draw_date)
    if date.day >= 28:  # ออกก่อนสิ้นเดือน แทนงวดวันที่ 1 ของเดือนถัดไป
        year, month = (date.year + 1, 1) if date.month == 12 else (date.year, date.month + 1)
        return _dt.date(year, month, 1).isoformat()
    if date.day <= 10:
        return date.replace(day=1).isoformat()
    return date.replace(day=16).isoformat()


def is_shifted(draw_date: str) -> bool:
    """งวดนี้ออกรางวัลคนละเดือนกับงวดของตัวเองหรือไม่ (เกณฑ์การติดดาว)"""
    return period_of(draw_date)[:7] != draw_date[:7]


def shift_reason(draw_date: str) -> str | None:
    """คำอธิบายว่าทำไมงวดนี้ออกคนละเดือน"""
    if draw_date in SHIFTED:
        return SHIFTED[draw_date][1]
    if not is_shifted(draw_date):
        return None
    period = period_of(draw_date)
    return (
        f"งวด {thaidate.to_thai(period)} ออกรางวัลก่อนสิ้นเดือน "
        f"วันที่ {thaidate.to_thai(draw_date)}"
    )


def describe(draw_date: str) -> dict:
    """ข้อมูลงวด/วันออกรางวัล สำหรับแสดงผล"""
    period = period_of(draw_date)
    return {
        "draw_date": draw_date,
        "period": period,
        "period_th": thaidate.to_thai(period),
        "slot": int(period[-2:]),
        "shifted": is_shifted(draw_date),
        "same_month_shift": period[-2:] != draw_date[-2:] and period[:7] == draw_date[:7],
        "reason": shift_reason(draw_date),
    }


def cancelled_in(year: int, month: int) -> list[dict]:
    """งวดที่งดจำหน่ายในเดือนนั้น"""
    prefix = f"{year:04d}-{month:02d}"
    return [
        {"period": period, "slot": int(period[-2:]), "reason": reason}
        for period, reason in sorted(CANCELLED.items())
        if period.startswith(prefix)
    ]


def audit(draw_dates: list[str]) -> dict:
    """ตรวจว่าทุกวันออกรางวัลจับคู่กับงวดได้ไม่ชนกัน"""
    seen: dict[str, str] = {}
    clashes: list[tuple[str, str, str]] = []
    for date in draw_dates:
        period = period_of(date)
        if period in seen:
            clashes.append((period, seen[period], date))
        else:
            seen[period] = date
    return {
        "mapped": len(seen),
        "clashes": clashes,
        "shifted": sorted(d for d in draw_dates if is_shifted(d)),
        "cancelled": sorted(CANCELLED),
    }
