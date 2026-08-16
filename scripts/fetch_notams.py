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
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iaa  # noqa: E402
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
TIMEOUT = 20
RETRIES = 3
# תקרה גלובלית. עדיף לחזור עם חלק מהמקורות מאשר להיתקע — ריצה שעתית
# שנמשכת חצי שעה חופפת את עצמה ושורפת דקות Actions.
DEADLINE_SECONDS = 240
_started_at = time.monotonic()


def _time_left() -> float:
    return DEADLINE_SECONDS - (time.monotonic() - _started_at)

# כותרת נוטאם — משמשת לחיתוך גוש טקסט לרשומות בודדות.
_NOTAM_HEADER_RE = re.compile(r"(?m)^\s*([A-Z]\d{1,4}/\d{2}\s+NOTAM[NRC]\b)")
_LOOKS_LIKE_NOTAM_RE = re.compile(r"\bQ\)\s*\w{4}/|\b[A-Z]\d{1,4}/\d{2}\s+NOTAM[NRC]\b")
_TAG_RE = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def http_get(
    url: str,
    accept: str = "*/*",
    extra_headers: dict | None = None,
    data: bytes | None = None,
) -> tuple[str, str]:
    """מחזיר (גוף, content-type).

    חוזר על הניסיון רק כשיש סיכוי שזה יעזור: תקלת רשת, timeout או 5xx.
    404 או 403 לא ישתנו בניסיון שני — חזרה עליהם רק מבזבזת את התקציב.
    """
    last_exc: Exception | None = None
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Accept-Language": "en",
    }
    headers.update(extra_headers or {})

    for attempt in range(RETRIES):
        if _time_left() <= 0:
            raise RuntimeError(f"{url} — חריגה מתקרת הזמן")
        try:
            req = urllib.request.Request(url, headers=headers, data=data)
            timeout = max(5, min(TIMEOUT, _time_left()))
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ctype = resp.headers.get("Content-Type", "")
                body = resp.read().decode("utf-8", errors="replace")
                return body, ctype
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise RuntimeError(f"{url} — HTTP {exc.code}") from exc
            last_exc = exc
        except (urllib.error.URLError, OSError) as exc:
            last_exc = exc
        if attempt < RETRIES - 1:
            time.sleep(min(2 ** (attempt + 1), max(0, _time_left())))
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
# כל מקור מחזיר רשימת גושי טקסט גולמיים. מקור שדורש אישורים ולא הוגדר
# מדלג על עצמו בהודעה ברורה, ולא נחשב ככשל.
#
# מצב המקורות נכון לאחרון שנבדק (ראו scripts/probe_sources.py):
#
#   FAA NOTAM API   דורש client_id/secret. הרשמה חינם ב-api.faa.gov.
#   autorouter      דורש client_id/secret. הרשמה חינם ב-autorouter.aero.
#   notams.online   הדף מחזיר HTML ריק. ה-endpoint שלו, api/notams.php,
#                   מחזיר תשובה מעורפלת שמפוענחת ב-notam-parser.js שלהם.
#                   זו הגנה מכוונת מפני גרידה ואנחנו לא עוקפים אותה.
#                   נשאר בשרשרת רק למקרה שיפרסמו תוכן קריא.
#   FAA DINS        מחזיר 403 לכל בקשה שאינה דפדפן.


class SourceUnconfigured(RuntimeError):
    """המקור דורש אישורים שלא הוגדרו. לא כשל — פשוט לא זמין."""


def _credentials(*names: str) -> list[str] | None:
    values = [os.environ.get(name, "").strip() for name in names]
    return values if all(values) else None


def source_faa_api(icao: str) -> tuple[list[str], str]:
    """FAA NOTAM API — המקור הרשמי. דורש הרשמה חינמית ב-api.faa.gov.

    האישורים מגיעים מ-secrets של ה-repo דרך משתני סביבה.
    """
    creds = _credentials("FAA_CLIENT_ID", "FAA_CLIENT_SECRET")
    if not creds:
        raise SourceUnconfigured(
            "חסרים FAA_CLIENT_ID ו-FAA_CLIENT_SECRET. הרשמה חינם ב-api.faa.gov."
        )
    client_id, client_secret = creds
    url = (
        "https://external-api.faa.gov/notamapi/v1/notams"
        f"?icaoLocation={icao}&pageSize=1000&pageNum=1"
    )
    body, ctype = http_get(
        url,
        accept="application/json",
        extra_headers={"client_id": client_id, "client_secret": client_secret},
    )
    return extract_from_response(body, ctype), url


_autorouter_token: str | None = None


def _autorouter_auth() -> str:
    """OAuth2 client_credentials. הטוקן נמשך פעם אחת לכל הריצה."""
    global _autorouter_token
    if _autorouter_token:
        return _autorouter_token

    creds = _credentials("AUTOROUTER_CLIENT_ID", "AUTOROUTER_CLIENT_SECRET")
    if not creds:
        raise SourceUnconfigured(
            "חסרים AUTOROUTER_CLIENT_ID ו-AUTOROUTER_CLIENT_SECRET. "
            "הרשמה חינם ב-autorouter.aero."
        )
    client_id, client_secret = creds
    payload = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    body, _ = http_get(
        "https://api.autorouter.aero/v1.0/oauth2/token",
        accept="application/json",
        extra_headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=payload,
    )
    token = (json.loads(body) or {}).get("access_token")
    if not token:
        raise RuntimeError("autorouter: לא התקבל access_token")
    _autorouter_token = token
    return token


def source_autorouter(icao: str) -> tuple[list[str], str]:
    """autorouter.aero — JSON. דורש הרשמה חינמית."""
    token = _autorouter_auth()
    # הסוגריים והמרכאות בפרמטר חייבים קידוד — בלעדיו השרת מחזיר שגיאה.
    itemas = urllib.parse.quote(f'["{icao}"]', safe="")
    url = f"https://api.autorouter.aero/v1.0/notam?itemas={itemas}&offset=0&limit=200"
    body, ctype = http_get(
        url,
        accept="application/json",
        extra_headers={"Authorization": f"Bearer {token}"},
    )
    return extract_from_response(body, ctype), url


def source_iaa(icao: str) -> tuple[list[str], str]:
    """רשות שדות התעופה — המקור הרשמי הישראלי.

    נמשך פעם אחת בלבד: הדף מגיש את כל ההודעות יחד ואינו מסונן לפי ICAO,
    אז משיכה לכל שדה בנפרד הייתה מביאה את אותו תוכן שוב ושוב.

    הדף לא מגיש שורות Q. רשומה שאין בטקסט שלה קואורדינטה מפורשת תגיע
    בלי גיאומטריה ותופיע ברשימה בלבד — וזה בסדר, זה מה שהמקור נותן.
    """
    global _iaa_blocks
    if icao != FIR:
        return [], iaa.NOTAM_URL
    if _iaa_blocks is None:
        req = urllib.request.Request(
            iaa.NOTAM_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Language": "he-IL,he;q=0.9"},
        )
        with urllib.request.urlopen(req, timeout=max(5, min(TIMEOUT, _time_left()))) as resp:
            page = iaa.decode(resp.read())
        # parse_notam_page מאחד שורות המשך, אחרת הטקסט נקטע בדיוק היכן
        # שהקואורדינטות יושבות.
        rows = iaa.parse_notam_page(page)
        _iaa_blocks = [iaa.to_raw_notam(row) for row in rows]
        print(f"  רשות שדות התעופה: {len(_iaa_blocks)} הודעות", file=sys.stderr)
    return _iaa_blocks, iaa.NOTAM_URL


_iaa_blocks: list[str] | None = None


def source_notams_online(icao: str) -> tuple[list[str], str]:
    """notams.online — המקור שאומת ידנית במפרט.

    התוכן נטען דינמית. ה-endpoint שלו מחזיר מטען מעורפל שמפוענח בקוד
    הלקוח שלהם — הגנה מכוונת מפני גרידה, ואנחנו לא מפענחים אותה.
    לכן נשארת רק קריאת הדף עצמו, שכיום מחזיר HTML בלי תוכן.
    """
    url = f"https://notams.online/icao/{icao}"
    body, ctype = http_get(url, accept="text/html")
    return extract_from_response(body, ctype), url


def source_faa_dins(icao: str) -> tuple[list[str], str]:
    """FAA DINS — מחזיר 403 לכל בקשה שאינה דפדפן. נשאר כגיבוי."""
    url = (
        "https://www.notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do"
        f"?reportType=Raw&retrieveLocId={icao}&actionType=notamRetrievalByICAOs"
        "&submit=View+NOTAMs"
    )
    body, ctype = http_get(url, accept="text/html")
    return extract_from_response(body, ctype), url


SOURCES = [
    ("iaa", source_iaa),
    ("faa-api", source_faa_api),
    ("autorouter", source_autorouter),
    ("notams.online", source_notams_online),
    ("faa-dins", source_faa_dins),
]


# ---------------------------------------------------------------------------
# איסוף
# ---------------------------------------------------------------------------


def collect(icaos: list[str]) -> tuple[list[dict], list[dict]]:
    """מושך מכל המקורות ומחזיר (רשומות מפורסרות, דוח מקורות)."""
    records: list[dict] = []
    report: list[dict] = []

    unconfigured: set[str] = set()

    for source_name, fetch in SOURCES:
        for icao in icaos:
            entry = {"source": source_name, "icao": icao, "ok": False, "count": 0}
            if source_name in unconfigured:
                entry["unconfigured"] = True
                entry["error"] = "דולג — המקור לא הוגדר"
                report.append(entry)
                continue
            if _time_left() <= 0:
                entry["error"] = "דולג — חריגה מתקרת הזמן"
                report.append(entry)
                continue
            try:
                blocks, url = fetch(icao)
                entry["url"] = url
                entry["ok"] = True
                entry["count"] = len(blocks)
                for block in blocks:
                    record = parse_notam(block, source=f"{source_name}:{icao}")
                    if record["geo"] is None and record.get("text"):
                        # אין שורת Q במקור הישראלי; מנסים מטקסט ההודעה.
                        record["geo"] = iaa.extract_position(record["text"])
                    records.append(record)
            except SourceUnconfigured as exc:
                # לא כשל — פשוט אין אישורים. מדלגים על שאר ה-ICAO של המקור.
                unconfigured.add(source_name)
                entry["unconfigured"] = True
                entry["error"] = str(exc)[:300]
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

    notams = sort_for_display(dedupe_and_resolve(records))

    # מקור שמחזיר 200 ריק אינו הצלחה. במרחב LLLL יש תמיד נוטאמים פעילים,
    # אז אפס רשומות מכל המקורות פירושו שהגרידה נשברה — לא ששמי המרחב פנויים.
    # הצגת "0 נוטאמים" כעובדה היא בדיוק סוג השקר שהכלי הזה אמור למנוע.
    any_source_ok = any(entry["ok"] and entry.get("count") for entry in report)

    if not any_source_ok:
        # כל המקורות נפלו. שומרים את הנתונים הישנים ומסמנים אותם כישנים —
        # נתון ישן עם חותמת זמן כנה עדיף על דף ריק.
        message = "; ".join(
            f"{e['source']}/{e['icao']}: "
            f"{e.get('error') or ('החזיר 200 אך ללא נוטאמים' if e['ok'] else 'unknown')}"
            for e in report
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
