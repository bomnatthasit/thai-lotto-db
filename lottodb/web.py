"""หน้าเว็บย้อนดูผลรางวัล รันที่เครื่องตัวเอง ไม่ต้องต่อเน็ต (หลัง sync แล้ว)"""

from __future__ import annotations

import json
import sqlite3
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import model, queries, store, thaidate

UI_PATH = Path(__file__).with_name("ui.html")


class _Handler(BaseHTTPRequestHandler):
    db_path: str | None = None
    server_version = "thai-lotto-db"

    def log_message(self, fmt: str, *args) -> None:  # เงียบกว่าเดิม
        if not str(args[1] if len(args) > 1 else "").startswith("2"):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802 - ชื่อที่ BaseHTTPRequestHandler กำหนด
        parsed = urlparse(self.path)
        route = unquote(parsed.path)
        params = {k: v[0] for k, v in parse_qs(parsed.query).items()}

        if route in {"/", "/index.html"}:
            self._send(200, UI_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if not route.startswith("/api/"):
            self._json({"error": "ไม่พบเส้นทางนี้"}, status=404)
            return

        conn = store.connect(self.db_path)
        try:
            self._json(self._api(route, params, conn))
        except KeyError as exc:
            self._json({"error": f"ขาดพารามิเตอร์ {exc}"}, status=400)
        except ValueError as exc:
            self._json({"error": str(exc)}, status=400)
        except Exception as exc:  # noqa: BLE001 - อย่าให้ server ล้มเพราะคำขอเดียว
            self._json({"error": f"{type(exc).__name__}: {exc}"}, status=500)
        finally:
            conn.close()

    # ------------------------------------------------------------ api

    def _api(self, route: str, params: dict, conn: sqlite3.Connection):
        if route == "/api/summary":
            return {
                "summary": queries.summary(conn),
                "years": queries.years(conn),
                "categories": [
                    {"key": c.key, "label": c.th, "digits": c.digits, "match": c.match}
                    for c in model.CATEGORIES
                ],
                "matrix_categories": list(queries.MATRIX_CATEGORIES),
                "matrix_groups": [list(row) for row in queries.MATRIX_GROUPS],
            }

        if route == "/api/matrix":
            return queries.monthly_matrix(
                conn,
                params.get("category", "last2"),
                slot=params.get("slot", "all"),
            )

        if route == "/api/schedule":
            return {"rows": queries.schedule_notes(conn)}

        if route == "/api/draws":
            year = params.get("year")
            return {
                "draws": queries.list_draws(
                    conn,
                    year=int(year) if year else None,
                    limit=min(int(params.get("limit", 40)), 500),
                    offset=int(params.get("offset", 0)),
                )
            }

        if route == "/api/draw":
            date = self._date(conn, params.get("date"))
            result = queries.get_draw(conn, date)
            if result is None:
                return {"error": f"ไม่มีงวดวันที่ {thaidate.to_thai(date)}"}
            return {**result, "nav": queries.neighbours(conn, date)}

        if route == "/api/check":
            ticket = _ticket(params["number"])
            date = self._date(conn, params.get("date"))
            result = queries.check_ticket(conn, ticket, date)
            if result is None:
                return {"error": f"ไม่มีงวดวันที่ {thaidate.to_thai(date)}"}
            return result

        if route == "/api/history":
            ticket = _ticket(params["number"])
            rows = queries.history(conn, ticket)
            info = queries.summary(conn)
            return {
                "ticket": ticket,
                "draws_total": info["draws"],
                "hits": len(rows),
                "rows": rows,
            }

        if route == "/api/search":
            return {
                "results": queries.search(
                    conn,
                    params["pattern"],
                    category=params.get("category") or None,
                    limit=min(int(params.get("limit", 150)), 1000),
                )
            }

        if route == "/api/freq":
            category = params.get("category", "last2")
            return {
                "rows": queries.frequency(
                    conn,
                    category,
                    since=thaidate.parse(params["since"]) if params.get("since") else None,
                    until=thaidate.parse(params["until"]) if params.get("until") else None,
                    top=min(int(params.get("top", 20)), 200),
                    ascending=params.get("low") == "1",
                ),
                "label": model.BY_KEY[category].th,
            }

        if route == "/api/gaps":
            category = params.get("category", "last2")
            return {
                "rows": queries.gaps(conn, category, top=min(int(params.get("top", 20)), 200)),
                "label": model.BY_KEY[category].th,
            }

        raise ValueError("ไม่รู้จักคำขอนี้")

    @staticmethod
    def _date(conn: sqlite3.Connection, text: str | None) -> str:
        if not text or text == "latest":
            row = conn.execute("SELECT MAX(draw_date) AS d FROM draws").fetchone()
            if not row or not row["d"]:
                raise ValueError("ฐานข้อมูลยังว่าง — สั่ง sync ก่อน")
            return row["d"]
        return thaidate.parse(text)

    # ------------------------------------------------------------ plumbing

    def _json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def _ticket(raw: str) -> str:
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 6:
        raise ValueError(f"เลขสลากต้องมี 6 หลัก (ได้ {raw!r})")
    return digits


def serve(
    *,
    db_path: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8777,
    open_browser: bool = True,
) -> None:
    handler = type("Handler", (_Handler,), {"db_path": db_path})
    httpd = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}/"
    print(f"เปิดหน้าเว็บที่ {url}   (กด Ctrl+C เพื่อหยุด)")
    if open_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nหยุดเซิร์ฟเวอร์แล้ว")
    finally:
        httpd.server_close()
