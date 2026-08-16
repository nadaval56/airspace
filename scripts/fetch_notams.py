#!/usr/bin/env python3
"""משיכת נוטאמים פעילים למרחב תל אביב (LLLL) ולשדות התעופה, וכתיבתם ל-data/notams.json.

עקרונות:
* כמה מקורות בשרשרת. כולם נמשכים ומאוחדים — חפיפה מטופלת ב-dedupe.
* אין סינון תוכן. כל מה שהמקור החזיר נשמר. סימון ויזואלי בלבד.
* אם הכל נכשל — לא דורסים את הקובץ הקיים. מעדכנים last_error ומסמנים stale.

שימוש:
    python3 scripts/fetch_notams.py                 # משיכה וכתיבה
    python3 scripts/fetch_notams.py --dry-run       # בלי לכתוב
    python3 scripts/fetch_notams.py --input raw.txt # פרסור קובץ מקומי (דיבוג)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parse_qline import dedupe_and_resolve, parse_notam, sort_for_display  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "notams.json")

FIR = "LLLL"
# שדות תעופה — נוטאם ברמת שדה לפעמים כולל הגבלה מקומית שלא עולה לרמת ה-FIR.
AIRPORTS = ["LLBG", "LLHA", "LLIB", "LLRD", "LLHZ"]

USER_AGENT = (
    "binyamin-airspace/1.0 (+https://github.com/nadaval56/airspace) "
    "static site data fetcher"
)
TIMEOUT = 30
RETRIES = 3

# כותרת נוטאם — משמשת לחיתוך גוש טקסט לרשומות בודדות.
_NOTAM_HEADER_RE = re.compile(r"(?m)^\s*([A-Z]\d{1,4}/\d{2}\s+NOTAM[NRC]\b)")
_LOOKS_LIKE_NOTAM_RE = re.compile(r"\bQ\)\s*\w{4}/|\b[A-Z]\d{1,4}/\d{2}\s+NOTAM[NRC]\b")
_TAG_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http_get(url: str, accept: str = "*/*") -> tuple[str, str]:
    """מחזיר (גוף, content-type). זורק אחרי RETRIES ניסיונות עם backoff."""
    last_exc: Exception | None = None
    for attempt in range(RETRIES):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": accept,
                    "Accept-Language": "en",
                },
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                ctype = resp.headers.get("Content-Type", "")
                body = resp.read().decode("utf-8", errors="replace")
                return body, ctype
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
            last_exc = exc
            if attempt < RETRIES - 1:
                time.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"{url} — {last_exc}")


# ---------------------------------------------------------------------------
# חילוץ נוטאמים מטקסט / JSON
# ---------------------------------------------------------------------------


def strip_html(html: str) -> str:
    """הופך HTML לטקסט. משתמש ב-BeautifulSoup אם זמין, אחרת נופל לרג'קס."""
    try:
        from bs4 import BeautifulSoup  # type: ignore

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style"]):
            tag.decompose()
        # שורות חדשות בין בלוקים — קריטי לחיתוך נכון של פריטי הנוטאם.
        return soup.get_text("\n")
    except ImportError:
        text = _TAG_RE.sub(" ", html)
        text = re.sub(r"<br\s*/?>|</(p|div|tr|li|pre)>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return _unescape(text)


def _unescape(text: str) -> str:
    import html as _html

    return _html.unescape(text)


def extract_notam_blocks(text: str) -> list[str]:
    """חותך גוש טקסט לרשומות נוטאם בודדות.

    ראשית לפי כותרות (XNNNN/YY NOTAMN). אם אין כותרות — לפי שורות Q).
    """
    text = _unescape(text).replace("\r\n", "\n").replace("\r", "\n")

    starts = [m.start() for m in _NOTAM_HEADER_RE.finditer(text)]
    if starts:
        blocks = []
        for idx, start in enumerate(starts):
            stop = starts[idx + 1] if idx + 1 < len(starts) else len(text)
            block = _tidy(text[start:stop])
            if block:
                blocks.append(block)
        return blocks

    # מקור בלי כותרות מפורשות — נופלים לחיתוך לפי שורת Q.
    q_starts = [m.start() for m in re.finditer(r"(?m)^\s*Q\)", text)]
    blocks = []
    for idx, start in enumerate(q_starts):
        stop = q_starts[idx + 1] if idx + 1 < len(q_starts) else len(text)
        block = _tidy(text[start:stop])
        if block:
            blocks.append(block)
    return blocks


def _tidy(block: str) -> str:
    """מנקה רווחים עודפים בלי לאבד את מבנה השורות שהפרסור נשען עליו."""
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in block.split("\n")]
    lines = [line for line in lines if line]
    block = "\n".join(lines).strip()
    if len(block) > 8000:  # הגנה מפני גוש שנחתך לא נכון
        block = block[:8000]
    return block if _LOOKS_LIKE_NOTAM_RE.search(block) else ""


def harvest_json_strings(payload) -> list[str]:
    """סורק JSON בכל מבנה ומלקט מחרוזות שנראות כמו נוטאם.

    מכוון להיות אגנוסטי למקור — כל API מחזיר שמות שדות אחרים.
    """
    found: list[str] = []

    def walk(node):
        if isinstance(node, str):
            if _LOOKS_LIKE_NOTAM_RE.search(node):
                found.append(node)
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    # מחרוזת אחת עשויה להכיל כמה נוטאמים משורשרים.
    blocks: list[str] = []
    for text in found:
        blocks.extend(extract_notam_blocks(text) or ([_tidy(text)] if _tidy(text) else []))
    return blocks


def extract_from_response(body: str, ctype: str) -> list[str]:
    stripped = body.lstrip()
    if "json" in ctype.lower() or stripped[:1] in ("{", "["):
        try:
            return harvest_json_strings(json.loads(body))
        except (json.JSONDecodeError, ValueError):
            pass
    if "<" in body[:2000]:
        return extract_notam_blocks(strip_html(body))
    return extract_notam_blocks(body)


# ---------------------------------------------------------------------------
# מקורות
# ---------------------------------------------------------------------------
# כל מקור מחזיר רשימת גושי טקסט גולמיים. השרשור מכוון: המקור הראשי הוא
# notams.online (אומת ידנית), והשאר גיבוי כדי שנפילה של אתר אחד לא תרוקן
# את הדף.


def source_notams_online(icao: str) -> tuple[list[str], str]:
    """notams.online — המקור הראשי לפי המפרט.

    התוכן נטען דינמית, אז מנסים קודם endpoint שמחזיר JSON. אם אין —
    נופלים לפרסור ה-HTML של הדף עצמו.
    """
    base = "https://notams.online"
    candidates = [
        f"{base}/api/icao/{icao}",
        f"{base}/api/notams/{icao}",
        f"{base}/api/v1/notams/{icao}",
        f"{base}/icao/{icao}?format=json",
        f"{base}/data/{icao}.json",
    ]
    for url in candidates:
        try:
            body, ctype = http_get(url, accept="application/json")
        except RuntimeError:
            continue
        blocks = extract_from_response(body, ctype)
        if blocks:
            return blocks, url

    url = f"{base}/icao/{icao}"
    body, ctype = http_get(url, accept="text/html")
    return extract_from_response(body, ctype), url


def source_autorouter(icao: str) -> tuple[list[str], str]:
    """autorouter.aero — API ציבורי שמחזיר JSON, בלי הרשמה."""
    url = (
        "https://api.autorouter.aero/v1.0/notam"
        f'?itemas=["{icao}"]&offset=0&limit=200'
    )
    body, ctype = http_get(url, accept="application/json")
    return extract_from_response(body, ctype), url


def source_faa_dins(icao: str) -> tuple[list[str], str]:
    """FAA DINS — שירות ציבורי, מחזיר HTML. גיבוי אחרון."""
    url = (
        "https://www.notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do"
        f"?reportType=Raw&retrieveLocId={icao}&actionType=notamRetrievalByICAOs"
        "&submit=View+NOTAMs"
    )
    body, ctype = http_get(url, accept="text/html")
    return extract_from_response(body, ctype), url


SOURCES = [
    ("notams.online", source_notams_online),
    ("autorouter", source_autorouter),
    ("faa-dins", source_faa_dins),
]


# ---------------------------------------------------------------------------
# איסוף
# ---------------------------------------------------------------------------


def collect(icaos: list[str]) -> tuple[list[dict], list[dict]]:
    """מושך מכל המקורות ומחזיר (רשומות מפורסרות, דוח מקורות)."""
    records: list[dict] = []
    report: list[dict] = []

    for source_name, fetch in SOURCES:
        for icao in icaos:
            entry = {"source": source_name, "icao": icao, "ok": False, "count": 0}
            try:
                blocks, url = fetch(icao)
                entry["url"] = url
                entry["ok"] = True
                entry["count"] = len(blocks)
                for block in blocks:
                    records.append(parse_notam(block, source=f"{source_name}:{icao}"))
            except Exception as exc:  # מקור שנפל לא מפיל את השאר
                entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
            report.append(entry)
            print(
                f"  {source_name:14s} {icao}  "
                f"{'✓' if entry['ok'] else '✗'} {entry.get('count', 0):3d}"
                f"{'  ' + entry['error'] if entry.get('error') else ''}",
                file=sys.stderr,
            )
    return records, report


def summarise(notams: list[dict]) -> dict:
    return {
        "total": len(notams),
        "mapped": sum(1 for n in notams if n.get("geo") and not n["geo"]["fir_wide"]),
        "fir_wide": sum(1 for n in notams if n.get("geo") and n["geo"]["fir_wide"]),
        "no_geo": sum(1 for n in notams if not n.get("geo")),
        "low_altitude": sum(1 for n in notams if n.get("low_altitude")),
        "administrative": sum(1 for n in notams if n.get("administrative")),
    }


def load_existing() -> dict | None:
    try:
        with open(OUTPUT_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_output(payload: dict) -> None:
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=False)
        fh.write("\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="לא כותב לקובץ")
    ap.add_argument("--input", help="פרסור קובץ טקסט מקומי במקום משיכה מהרשת")
    ap.add_argument("--icao", nargs="*", help="דריסת רשימת ה-ICAO")
    args = ap.parse_args()

    existing = load_existing()
    timestamp = now_iso()

    if args.input:
        with open(args.input, encoding="utf-8") as fh:
            raw = fh.read()
        blocks = extract_from_response(raw, "text/plain")
        records = [parse_notam(b, source="local") for b in blocks]
        report = [{"source": "local", "icao": args.input, "ok": True, "count": len(blocks)}]
    else:
        icaos = args.icao if args.icao else [FIR] + AIRPORTS
        print(f"משיכה עבור: {', '.join(icaos)}", file=sys.stderr)
        records, report = collect(icaos)

    any_source_ok = any(entry["ok"] for entry in report)
    notams = sort_for_display(dedupe_and_resolve(records))

    if not any_source_ok:
        # כל המקורות נפלו. שומרים את הנתונים הישנים ומסמנים אותם כישנים —
        # נתון ישן עם חותמת זמן כנה עדיף על דף ריק.
        message = "; ".join(
            f"{e['source']}/{e['icao']}: {e.get('error', 'unknown')}" for e in report
        )[:1000]
        if existing:
            payload = dict(existing)
            payload["generated_at"] = timestamp
            payload["stale"] = True
            payload["last_error"] = {"at": timestamp, "message": message}
            payload["sources"] = report
        else:
            payload = {
                "generated_at": timestamp,
                "last_success": None,
                "last_error": {"at": timestamp, "message": message},
                "stale": True,
                "fir": FIR,
                "airports": AIRPORTS,
                "sources": report,
                "counts": summarise([]),
                "notams": [],
            }
        print("כל המקורות נכשלו — הקובץ הקיים נשמר ומסומן כישן.", file=sys.stderr)
    else:
        payload = {
            "generated_at": timestamp,
            "last_success": timestamp,
            "last_error": (existing or {}).get("last_error"),
            "stale": False,
            "fir": FIR,
            "airports": AIRPORTS,
            "sources": report,
            "counts": summarise(notams),
            "notams": notams,
        }

    print(json.dumps(payload["counts"], ensure_ascii=False), file=sys.stderr)

    if args.dry_run:
        print("--dry-run: לא נכתב קובץ.", file=sys.stderr)
        return 0

    write_output(payload)
    print(f"נכתב {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
