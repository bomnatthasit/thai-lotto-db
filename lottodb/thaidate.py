"""แปลงวันที่ไทย <-> ISO  รับได้หลายรูปแบบที่คนไทยพิมพ์จริง"""

from __future__ import annotations

import datetime as _dt
import re

MONTHS_TH = (
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
)

MONTHS_ABBR = (
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
)

_MONTH_LOOKUP: dict[str, int] = {}
for _i, _name in enumerate(MONTHS_TH, start=1):
    _MONTH_LOOKUP[_name] = _i
for _i, _name in enumerate(MONTHS_ABBR, start=1):
    _MONTH_LOOKUP[_name] = _i
    _MONTH_LOOKUP[_name.replace(".", "")] = _i


def to_thai(iso: str) -> str:
    """'2026-10-16' -> '16 ตุลาคม 2569'"""
    d = _dt.date.fromisoformat(iso)
    return f"{d.day} {MONTHS_TH[d.month - 1]} {d.year + 543}"


def to_thai_short(iso: str) -> str:
    """'2026-10-16' -> '16 ต.ค. 69'"""
    d = _dt.date.fromisoformat(iso)
    return f"{d.day} {MONTHS_ABBR[d.month - 1]} {(d.year + 543) % 100:02d}"


def _year_to_ce(year: int) -> int:
    """ปี 4 หลัก: >2400 ถือเป็น พ.ศ.  2 หลัก: ถือเป็น พ.ศ. ย่อ"""
    if year > 2400:
        return year - 543
    if year < 100:
        return 2500 + year - 543 if year < 90 else 2400 + year - 543
    return year


def parse(text: str) -> str:
    """คืนค่า ISO 'YYYY-MM-DD'  รับ: 2026-10-16 / 16-10-2569 / 16/10/69 /
    16102569 (แบบ sanook) / '16 ตุลาคม 2569' / '16 ต.ค. 69'"""
    s = text.strip()

    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, da = (int(g) for g in m.groups())
        return _build(y, mo, da)

    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})", s)
    if m:
        da, mo, y = (int(g) for g in m.groups())
        return _build(_year_to_ce(y), mo, da)

    m = re.fullmatch(r"(\d{2})(\d{2})(\d{4})", s)  # DDMMYYYY เช่น 16102569
    if m:
        da, mo, y = (int(g) for g in m.groups())
        return _build(_year_to_ce(y), mo, da)

    m = re.fullmatch(r"(\d{1,2})\s*([^\s\d]+)\s*(\d{2}|\d{4})", s)
    if m:
        da, name, y = m.group(1), m.group(2), m.group(3)
        mo = _MONTH_LOOKUP.get(name) or _MONTH_LOOKUP.get(name.replace(".", ""))
        if mo:
            return _build(_year_to_ce(int(y)), mo, int(da))

    raise ValueError(f"อ่านวันที่ไม่ออก: {text!r}")


def _build(year: int, month: int, day: int) -> str:
    return _dt.date(year, month, day).isoformat()


def sanook_slug(iso: str) -> str:
    """'2026-10-16' -> '16102569' (ใช้ประกอบลิงก์อ้างอิง)"""
    d = _dt.date.fromisoformat(iso)
    return f"{d.day:02d}{d.month:02d}{d.year + 543}"
