"""อ่านไฟล์ผลรางวัลจากคลัง vicha-w/thai-lotto-archive

รูปแบบไฟล์ `lottonumbers/YYYY-MM-DD.txt`
    บรรทัดแรก  = URL แหล่งอ้างอิง
    บรรทัดถัดมา = <LABEL> <เลข> <เลข> ...
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import model


@dataclass
class Draw:
    draw_date: str
    source_url: str | None = None
    source: str = "archive"
    numbers: dict[str, list[str]] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)

    @property
    def ruleset(self) -> str:
        return model.ruleset_for(self.draw_date)

    @property
    def prize_count(self) -> int:
        return sum(len(v) for v in self.numbers.values())


def parse_archive_text(draw_date: str, text: str) -> Draw:
    draw = Draw(draw_date=draw_date)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        draw.anomalies.append("ปัญหา: ไฟล์ว่าง")
        return draw

    if lines[0].lower().startswith(("http://", "https://")):
        draw.source_url = lines[0]
        lines = lines[1:]

    for line in lines:
        label, *nums = line.split()
        key = model.ARCHIVE_LABELS.get(label.upper())
        if key is None:
            draw.anomalies.append(f"ปัญหา: ป้ายกำกับไม่รู้จัก {label}")
            continue
        want = model.BY_KEY[key].digits
        clean: list[str] = []
        for n in nums:
            if not n.isdigit():
                draw.anomalies.append(f"ปัญหา: {label} ไม่ใช่ตัวเลข {n!r}")
                continue
            if len(n) != want:
                draw.anomalies.append(f"ปัญหา: {label} ควรมี {want} หลัก แต่ได้ {n!r}")
                continue
            clean.append(n)
        draw.numbers.setdefault(key, []).extend(clean)

    _validate(draw)
    return draw


def parse_glo_response(payload: dict) -> Draw:
    """แปลง JSON จาก API สำนักงานสลากกินแบ่งรัฐบาลให้เป็น Draw เดียวกัน"""
    body = payload.get("response") or {}
    draw_date = body.get("date")
    if not draw_date:
        raise ValueError("ไม่พบวันที่ในผลลัพธ์จาก GLO API")

    draw = Draw(draw_date=draw_date, source="glo-api", source_url=body.get("pdf_url"))

    for glo_key, entry in (body.get("data") or {}).items():
        key = model.GLO_KEYS.get(glo_key)
        if key is None:
            draw.anomalies.append(f"ปัญหา: หมวดใหม่จาก GLO ที่ยังไม่รองรับ {glo_key}")
            continue
        items = sorted(entry.get("number") or [], key=lambda n: n.get("value", ""))
        draw.numbers[key] = [n["value"] for n in items if str(n.get("value", "")).isdigit()]

    _validate(draw)
    return draw


def _validate(draw: Draw) -> None:
    expected = model.expected_counts(draw.ruleset)
    for key, want in expected.items():
        got = len(draw.numbers.get(key, []))
        if got != want:
            draw.anomalies.append(
                f"ปัญหา: {model.BY_KEY[key].th} คาด {want} รางวัล แต่พบ {got}"
            )
    for key, nums in draw.numbers.items():
        dupes = len(nums) - len(set(nums))
        if dupes:
            draw.anomalies.append(f"ข้อสังเกต: {model.BY_KEY[key].th} มีเลขซ้ำ {dupes} รายการ")


# ชื่อสาธารณะสำหรับโมดูลอื่นในแพ็กเกจ
validate = _validate
