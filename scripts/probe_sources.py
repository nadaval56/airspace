#!/usr/bin/env python3
"""אבחון מקורות הנוטאמים — מריצים ב-Actions כשמשיכה מחזירה ריק.

מדפיס לכל מועמד: קוד HTTP, סוג תוכן, גודל, האם נראה כמו נוטאם, וקטע.
עבור notams.online גם מחלץ מהדף כתובות שנראות כמו API — שם נמצא התוכן
שנטען דינמית.

הסקריפט לא כותב כלום. הוא כלי חקירה בלבד.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fetch_notams import extract_from_response  # noqa: E402

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

ICAO = "LLLL"


def probe(name: str, url: str, headers: dict | None = None, data: bytes | None = None):
    print(f"\n{'─' * 72}\n▶ {name}\n  {url}")
    req_headers = {"User-Agent": BROWSER_UA, "Accept": "*/*"}
    req_headers.update(headers or {})
    req = urllib.request.Request(url, headers=req_headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            ctype = resp.headers.get("Content-Type", "")
            status = resp.status
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        status = exc.code
        print(f"  HTTP {status}  {ctype}  {len(body):,} bytes  (שגיאה)")
        print("  " + body[:400].replace("\n", "\n  "))
        return None
    except Exception as exc:
        print(f"  נכשל: {type(exc).__name__}: {exc}")
        return None

    blocks = extract_from_response(body, ctype)
    print(f"  HTTP {status}  {ctype}  {len(body):,} bytes  →  {len(blocks)} נוטאמים חולצו")
    if blocks:
        print("  --- הראשון:")
        print("  " + blocks[0][:500].replace("\n", "\n  "))
    else:
        print("  --- 600 התווים הראשונים:")
        print("  " + body[:600].replace("\n", "\n  "))
    return body


def find_api_urls(html: str) -> None:
    """מחלץ מהדף כתובות שנראות כמו endpoint של נתונים."""
    print(f"\n{'─' * 72}\n▶ כתובות שנראות כמו API בתוך הדף")

    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)
    print(f"  {len(scripts)} קבצי script:")
    for s in scripts[:15]:
        print(f"    {s}")

    patterns = re.findall(
        r'["\'](/(?:api|data|json|v\d)[^"\'\s]{0,120})["\']', html, re.I
    )
    inline = re.findall(r'(?:fetch|axios\.\w+|XMLHttpRequest[^;]{0,80})\(["\']([^"\']+)', html)
    seen: list[str] = []
    for u in patterns + inline:
        if u not in seen:
            seen.append(u)
    print(f"  {len(seen)} מועמדים:")
    for u in seen[:40]:
        print(f"    {u}")

    # תוכן שהוטמע ישירות בדף כ-JSON (נפוץ ב-Next.js / Nuxt)
    for marker in ("__NEXT_DATA__", "__NUXT__", "window.__DATA__"):
        if marker in html:
            print(f"  נמצא {marker} בדף — התוכן עשוי להיות מוטמע ב-JSON.")


def inspect_scripts(html: str) -> None:
    """מוריד את קבצי ה-JS של הדף ומחפש בהם את הכתובת שממנה נמשכים הנתונים.

    זה הצעד המכריע: התוכן נטען דינמית, אז מקור האמת נמצא בקוד הלקוח.
    """
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)
    own = [s for s in scripts if "notams.online" in s or s.startswith("/")]

    for src in own:
        url = src if src.startswith("http") else "https://notams.online" + src
        print(f"\n{'─' * 72}\n▶ קוד לקוח: {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
            with urllib.request.urlopen(req, timeout=45) as resp:
                js = resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            print(f"  נכשל: {exc}")
            continue

        print(f"  {len(js):,} bytes")

        calls = re.findall(r'(?:fetch|axios(?:\.\w+)?)\s*\(\s*([^;\n]{0,200})', js)
        if calls:
            print(f"  --- {len(calls)} קריאות רשת:")
            for c in calls[:20]:
                print(f"    {c.strip()[:180]}")

        urls = re.findall(r'["\'`](https?://[^"\'`\s]{6,160}|/[a-z0-9_\-./]{3,120})["\'`]', js, re.I)
        interesting = [
            u for u in dict.fromkeys(urls)
            if not re.search(r'\.(png|jpg|svg|css|ico|woff2?)$', u, re.I)
            and not re.search(r'googletagmanager|googlesyndication|doubleclick|effectivegatecpm|highperformanceformat', u, re.I)
        ]
        print(f"  --- {len(interesting)} כתובות:")
        for u in interesting[:45]:
            print(f"    {u}")

        # תבניות שנבנות דינמית, למשל `${base}/notams/${icao}`
        templates = re.findall(r'`([^`\n]{4,160}\$\{[^`\n]{0,120})`', js)
        if templates:
            print(f"  --- {len(templates)} תבניות כתובת:")
            for t in dict.fromkeys(templates):
                print(f"    {t[:170]}")


def main() -> int:
    print("=" * 72)
    print("אבחון מקורות נוטאמים")
    print("=" * 72)

    # ה-endpoint שנמצא ב-app.js. מדפיסים ממנו הרבה, כי הוא המקור היחיד
    # שאינו חסום ואנחנו צריכים לראות בדיוק באיזה מבנה הוא מחזיר.
    body = probe(
        "notams.online — ה-endpoint מ-app.js",
        f"https://notams.online/api/notams.php?location={ICAO}",
        {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest",
         "Referer": f"https://notams.online/icao/{ICAO}"},
    )
    if body:
        print("  --- 2,500 התווים הראשונים של הגוף:")
        print("  " + body[:2500].replace("\n", "\n  "))
        try:
            payload = json.loads(body)
            print(f"  --- JSON תקין. סוג: {type(payload).__name__}")
            if isinstance(payload, dict):
                print(f"      מפתחות עליונים: {list(payload)[:25]}")
                for key, value in payload.items():
                    if isinstance(value, list) and value:
                        print(f"      {key}: רשימה של {len(value)}, "
                              f"מפתחות הפריט: {list(value[0])[:25] if isinstance(value[0], dict) else type(value[0]).__name__}")
            elif isinstance(payload, list) and payload:
                print(f"      רשימה של {len(payload)}, "
                      f"מפתחות הפריט: {list(payload[0])[:25] if isinstance(payload[0], dict) else type(payload[0]).__name__}")
                print(f"      פריט ראשון: {json.dumps(payload[0], ensure_ascii=False)[:1200]}")
        except (json.JSONDecodeError, ValueError):
            print("  --- לא JSON.")

    html = probe(
        "notams.online — הדף עצמו",
        f"https://notams.online/icao/{ICAO}",
        {"Accept": "text/html,application/xhtml+xml"},
    )
    if html:
        find_api_urls(html)
        inspect_scripts(html)
        for path in (
            f"/api/icao/{ICAO}",
            f"/api/notams/{ICAO}",
            f"/api/v1/notams/{ICAO}",
            f"/api/notam?icao={ICAO}",
            f"/notams/{ICAO}.json",
            f"/data/{ICAO}.json",
        ):
            probe(f"notams.online{path}", f"https://notams.online{path}",
                  {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"})

    itemas = urllib.parse.quote(f'["{ICAO}"]', safe="")
    probe(
        "autorouter — מקודד",
        f"https://api.autorouter.aero/v1.0/notam?itemas={itemas}&offset=0&limit=20",
        {"Accept": "application/json"},
    )
    probe(
        "autorouter — לא מקודד",
        f'https://api.autorouter.aero/v1.0/notam?itemas=["{ICAO}"]&offset=0&limit=20',
        {"Accept": "application/json"},
    )

    probe(
        "FAA DINS — GET",
        "https://www.notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do"
        f"?reportType=Raw&retrieveLocId={ICAO}&actionType=notamRetrievalByICAOs",
        {"Accept": "text/html"},
    )
    probe(
        "FAA DINS — POST",
        "https://www.notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do",
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html"},
        urllib.parse.urlencode({
            "reportType": "Raw",
            "retrieveLocId": ICAO,
            "actionType": "notamRetrievalByICAOs",
            "submit": "View NOTAMs",
        }).encode(),
    )

    probe(
        "FAA NOTAM API (ציבורי)",
        f"https://external-api.faa.gov/notamapi/v1/notams?icaoLocation={ICAO}",
        {"Accept": "application/json"},
    )
    probe(
        "notaminfo",
        f"https://www.notaminfo.com/api/notams?icao={ICAO}",
        {"Accept": "application/json"},
    )

    print("\n" + "=" * 72)
    print("סוף האבחון")
    return 0


if __name__ == "__main__":
    sys.exit(main())
