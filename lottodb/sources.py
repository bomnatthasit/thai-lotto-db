"""ดึงข้อมูลจากแหล่งต้นทาง — ใช้แต่ไลบรารีมาตรฐาน"""

from __future__ import annotations

import json
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from .parse import Draw, parse_archive_text, parse_glo_response

ARCHIVE_REPO = "vicha-w/thai-lotto-archive"
ARCHIVE_TARBALL = f"https://codeload.github.com/{ARCHIVE_REPO}/tar.gz/refs/heads/master"
ARCHIVE_CREDIT = f"https://github.com/{ARCHIVE_REPO}"

GLO_LATEST = "https://www.glo.or.th/api/lottery/getLatestLottery"

_UA = "thai-lotto-db/1.0 (+local archive tool)"
_TIMEOUT = 60


def _get(url: str, data: bytes | None = None, content_type: str | None = None) -> bytes:
    headers = {"User-Agent": _UA}
    if content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 - https ที่ตรึงไว้
        return resp.read()


def fetch_glo_latest() -> Draw:
    """งวดล่าสุดจาก API ของสำนักงานสลากกินแบ่งรัฐบาล (มีเงินรางวัลจริงมาด้วย)"""
    raw = _get(GLO_LATEST, data=b"{}", content_type="application/json")
    return parse_glo_response(json.loads(raw.decode("utf-8")))


def fetch_archive(work_dir: Path | None = None) -> list[Draw]:
    """ดาวน์โหลดคลังทั้งก้อน (ไฟล์เดียว ~300KB) แล้วอ่านทุกงวด"""
    tmp_parent = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="lottoarch-"))
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tarball = tmp_parent / "archive.tar.gz"
    tarball.write_bytes(_get(ARCHIVE_TARBALL))

    extract_to = tmp_parent / "extracted"
    extract_to.mkdir(exist_ok=True)
    with tarfile.open(tarball, "r:gz") as tf:
        # filter="data" กันไฟล์หลุดออกนอกโฟลเดอร์ (ข้อมูลจากอินเทอร์เน็ตถือว่าไม่น่าเชื่อถือ)
        tf.extractall(extract_to, filter="data")

    files = sorted(extract_to.glob("*/lottonumbers/*.txt"))
    draws: list[Draw] = []
    for path in files:
        draw_date = path.stem
        if len(draw_date) != 10 or draw_date[4] != "-":
            continue
        draws.append(parse_archive_text(draw_date, path.read_text(encoding="utf-8")))
    return draws
