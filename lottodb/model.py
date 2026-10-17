"""นิยามหมวดรางวัล และโครงสร้างเงินรางวัล"""

from __future__ import annotations

from dataclasses import dataclass

# วันที่โครงสร้างรางวัลเปลี่ยน: ยกเลิก "เลขท้าย 3 ตัว 4 รางวัล"
# มาเป็น "เลขหน้า 3 ตัว 2 รางวัล" + "เลขท้าย 3 ตัว 2 รางวัล"
RULESET_SWITCH = "2015-09-01"


@dataclass(frozen=True)
class Category:
    key: str
    th: str
    digits: int
    match: str  # 'exact' | 'prefix' | 'suffix' — วิธีเทียบกับเลขสลาก 6 หลัก
    order: int
    expect: int | None  # จำนวนรางวัลมาตรฐาน (None = ไม่คงที่ตามยุค)


CATEGORIES: tuple[Category, ...] = (
    Category("first", "รางวัลที่ 1", 6, "exact", 1, 1),
    Category("near1", "รางวัลข้างเคียงรางวัลที่ 1", 6, "exact", 2, 2),
    Category("front3", "รางวัลเลขหน้า 3 ตัว", 3, "prefix", 3, None),
    Category("back3", "รางวัลเลขท้าย 3 ตัว", 3, "suffix", 4, None),
    Category("last2", "รางวัลเลขท้าย 2 ตัว", 2, "suffix", 5, 1),
    Category("second", "รางวัลที่ 2", 6, "exact", 6, 5),
    Category("third", "รางวัลที่ 3", 6, "exact", 7, 10),
    Category("fourth", "รางวัลที่ 4", 6, "exact", 8, 50),
    Category("fifth", "รางวัลที่ 5", 6, "exact", 9, 100),
)

BY_KEY: dict[str, Category] = {c.key: c for c in CATEGORIES}
ORDERED_KEYS: tuple[str, ...] = tuple(c.key for c in sorted(CATEGORIES, key=lambda c: c.order))

# จำนวนรางวัลของสองหมวดที่ขึ้นกับยุค
EXPECT_BY_RULESET: dict[str, dict[str, int]] = {
    "post2015": {"front3": 2, "back3": 2},
    "pre2015": {"front3": 0, "back3": 4},
}

# ป้ายกำกับในไฟล์ของ vicha-w/thai-lotto-archive
ARCHIVE_LABELS: dict[str, str] = {
    "FIRST": "first",
    "NEAR_FIRST": "near1",
    "THREE_FIRST": "front3",
    "THREE_LAST": "back3",
    "THREE": "back3",  # ยุคก่อน ก.ย. 2558 — เลขท้าย 3 ตัว 4 รางวัล
    "TWO": "last2",
    "SECOND": "second",
    "THIRD": "third",
    "FOURTH": "fourth",
    "FIFTH": "fifth",
}

# คีย์ใน JSON ของ API สำนักงานสลากกินแบ่งรัฐบาล
# หมายเหตุ: GLO ตั้งชื่อ last3f ไว้สำหรับ "เลขหน้า 3 ตัว" (ไม่ใช่เลขท้าย)
GLO_KEYS: dict[str, str] = {
    "first": "first",
    "near1": "near1",
    "last3f": "front3",
    "last3b": "back3",
    "last2": "last2",
    "second": "second",
    "third": "third",
    "fourth": "fourth",
    "fifth": "fifth",
}


def ruleset_for(draw_date: str) -> str:
    """'pre2015' หรือ 'post2015' ตามวันออกรางวัล (ISO)"""
    return "post2015" if draw_date >= RULESET_SWITCH else "pre2015"


def expected_counts(ruleset: str) -> dict[str, int]:
    counts = {c.key: c.expect for c in CATEGORIES if c.expect is not None}
    counts.update(EXPECT_BY_RULESET[ruleset])
    return counts


def matches(category: str, prize_number: str, ticket: str) -> bool:
    """เลขสลาก 6 หลัก `ticket` ถูกรางวัลหมวดนี้ด้วยเลข `prize_number` หรือไม่"""
    how = BY_KEY[category].match
    if how == "exact":
        return ticket == prize_number
    if how == "prefix":
        return ticket.startswith(prize_number)
    if how == "suffix":
        return ticket.endswith(prize_number)
    raise ValueError(f"unknown match mode: {how}")
