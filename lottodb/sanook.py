"""แหล่งข้อมูลสำรอง: หน้าตรวจหวยย้อนหลังของ sanook

ใช้เมื่อคลังหลักขาดงวด หรือข้อมูลงวดนั้นเสีย หรือข้อมูลงวดนั้นเสีย

หน้าเว็บฝัง JSON-LD ชนิด NewsArticle ที่มีผลรางวัลทั้งงวดอยู่ในฟิลด์ articleBody
ในรูปแบบ "บรรทัดหัวข้อ แล้วตามด้วยบรรทัดตัวเลข"
"""

from __future__ import annotations

import datetime as _dt
import html
import json
import re
import time
import urllib.error
import urllib.request

from . import model, thaidate
from .parse import Draw, _validate

ARCHIVE_INDEX = "https://news.sanook.com/lotto/archive/"
CHECK_URL = "https://news.sanook.com/lotto/check/{slug}/"
CREDIT = "https://news.sanook.com/lotto/"

_UA = "Mozilla/5.0 (compatible; thai-lotto-db/1.0)"
_TIMEOUT = 45

# เรียงลำดับสำคัญ: "ข้างเคียง" ต้องถูกตรวจก่อน "รางวัลที่ 1"
_LABEL_RULES: tuple[tuple[str, str], ...] = (
    ("ข้างเคียง", "near1"),
    ("เลขหน้า 3 ตัว", "front3"),
    ("เลขท้าย 3 ตัว", "back3"),
    ("เลขท้าย 2 ตัว", "last2"),
    ("รางวัลที่ 1", "first"),
    ("รางวัลที่ 2", "second"),
    ("รางวัลที่ 3", "third"),
    ("รางวัลที่ 4", "fourth"),
    ("รางวัลที่ 5", "fifth"),
)

_HEADLINE_RE = re.compile(r'"(?:alternativeHeadline|headline)":\s*"(.*?)"', re.S)
_BODY_RE = re.compile(r'"articleBody":\s*"((?:[^"\\]|\\.)*)"', re.S)
_PUBLISHED_RE = re.compile(r'"datePublished":\s*"(\d{4}-\d{2}-\d{2})')
_THAI_DATE_RE = re.compile(r"(\d{1,2})\s+([฀-๿]+)\s+(\d{4})")


def slug_for(iso_date: str) -> str:
    d = _dt.date.fromisoformat(iso_date)
    return f"{d.day:02d}{d.month:02d}{d.year + 543}"


def _get(url: str, *, attempts: int = 4) -> str:
    """sanook ตัดการเชื่อมต่อเป็นระยะเมื่อยิงถี่ จึงต้องลองซ้ำแบบถอยเวลา"""
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310
                return resp.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, ConnectionError, TimeoutError) as exc:
            last = exc
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    raise ConnectionError(f"ดึง {url} ไม่สำเร็จหลังลอง {attempts} ครั้ง: {last}")


def index_dates() -> list[str]:
    """วันที่ (ISO) ของงวดที่หน้าสารบัญของ sanook มีให้ — ใช้สอบทานว่างวดไหนมีจริง"""
    page = _get(ARCHIVE_INDEX)
    out: set[str] = set()
    for slug in re.findall(r"/lotto/check/(\d{8})/", page):
        day, month, year_be = int(slug[:2]), int(slug[2:4]), int(slug[4:])
        try:
            out.add(_dt.date(year_be - 543, month, day).isoformat())
        except ValueError:
            continue
    return sorted(out, reverse=True)


def fetch_draw(iso_date: str) -> Draw:
    """ดึงผลงวดหนึ่งจาก sanook

    sanook จะเด้งไปหน้างวดล่าสุดถ้าไม่มีงวดที่ขอ จึงต้องยืนยันว่าวันที่ในหน้า
    ตรงกับที่ขอก่อน ไม่งั้นจะเอาเลขงวดอื่นมาใส่ผิดงวด
    """
    page = _get(CHECK_URL.format(slug=slug_for(iso_date)))

    page_date = _page_date(page)
    if page_date != iso_date:
        raise LookupError(
            f"sanook ไม่มีงวดวันที่ {iso_date} (หน้าที่ได้คืองวด {page_date or 'ไม่ทราบ'})"
        )

    body_match = _BODY_RE.search(page)
    if body_match is None:
        raise LookupError(f"ไม่พบเนื้อหาผลรางวัลในหน้าของ sanook สำหรับ {iso_date}")
    body = html.unescape(json.loads('"' + body_match.group(1) + '"').replace("&nbsp;", " "))

    draw = parse_article_body(iso_date, body)
    draw.source_url = CHECK_URL.format(slug=slug_for(iso_date))
    return draw


def _page_date(page: str) -> str | None:
    headline = _HEADLINE_RE.search(page)
    if headline:
        text = json.loads('"' + headline.group(1) + '"')
        found = _THAI_DATE_RE.search(text)
        if found:
            try:
                return thaidate.parse(" ".join(found.groups()))
            except ValueError:
                pass
    published = _PUBLISHED_RE.search(page)
    return published.group(1) if published else None


def parse_article_body(iso_date: str, body: str) -> Draw:
    draw = Draw(draw_date=iso_date, source="sanook")
    current: str | None = None

    for line in (ln.strip() for ln in body.splitlines()):
        if not line:
            continue
        key = _label_key(line)
        if key is not None:
            current = key
            draw.numbers.setdefault(key, [])
            continue
        if current is None:
            continue
        want = model.BY_KEY[current].digits
        found = [n for n in re.findall(r"\d+", line) if len(n) == want]
        if found:
            draw.numbers[current].extend(found)
        elif not re.fullmatch(r"[\d\s]+", line):
            current = None  # ข้อความท้ายบทความ ไม่ใช่ตัวเลขรางวัลแล้ว

    draw.numbers = {k: v for k, v in draw.numbers.items() if v}
    _validate(draw)
    return draw


def _label_key(line: str) -> str | None:
    """บรรทัดนี้เป็นหัวข้อหมวดรางวัลไหน (None = ไม่ใช่บรรทัดหัวข้อ)"""
    if "บาท" not in line:
        return None
    for needle, key in _LABEL_RULES:
        if needle in line:
            return key
    return None
