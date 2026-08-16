#!/usr/bin/env python3
"""אבחון מקורות הנוטאמים — מריצים ב-Actions כשמשיכה מחזירה ריק.

מדפיס לכל מועמד: קוד HTTP, סוג תוכן, גודל, האם נראה כמו נוטאם, וקטע.
עבור notams.online גם מחלץ מהדף כתובות שנראות כמו API — שם נמצא התוכן
שנטען דינמית.

הסקריפט לא כותב כלום. הוא כלי חקירה בלבד.
"""

from __future__ import annotations

import http.cookiejar
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


IAA_URL = "https://brin.iaa.gov.il/aeroinfo/AeroInfo.aspx?msgType=Notam"


def probe_iaa() -> None:
    """רשות שדות התעופה — מקור ישראלי רשמי.

    הדף הוא ASP.NET WebForms, אז צריך עוגיות ו-__VIEWSTATE. בודקים גם
    GET רגיל וגם POST חוזר, שהוא הדפוס שמפעיל טבלאות בדפים כאלה.
    """
    print(f"\n{'=' * 72}\n▶▶ רשות שדות התעופה — {IAA_URL}\n{'=' * 72}")

    # עוגיות נדרשות: ASP.NET מנהל session, ובלעדיה ה-POST ייכשל.
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
    }

    def fetch(url, data=None, extra=None):
        hdrs = dict(headers)
        hdrs.update(extra or {})
        req = urllib.request.Request(url, headers=hdrs, data=data)
        try:
            with opener.open(req, timeout=60) as resp:
                raw, status, ctype = resp.read(), resp.status, resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            raw, status, ctype = exc.read(), exc.code, ""
        except Exception as exc:
            print(f"  נכשל: {type(exc).__name__}: {exc}")
            return None, None, None
        # הכותרת מצהירה utf-8 אבל התג במסמך אומר windows-1255. הולכים
        # אחרי התג — פענוח שגוי הופך את העברית לג'יבריש.
        head = raw[:2000].decode("latin-1", errors="replace").lower()
        encoding = "cp1255" if "windows-1255" in head else "utf-8"
        return raw.decode(encoding, errors="replace"), status, ctype

    html, status, ctype = fetch(IAA_URL)
    if html is None:
        return

    blocks = extract_from_response(html, ctype)
    print(f"  GET → HTTP {status}  {ctype}  {len(html):,} bytes  →  {len(blocks)} נוטאמים")
    if blocks:
        print("  --- הראשון:")
        print("  " + blocks[0][:800].replace("\n", "\n  "))
        return

    # מה יש בדף: שדות טופס, סקריפטים, ורמזים לתוכן
    fields = dict(re.findall(
        r'<input[^>]+name="([^"]+)"[^>]*value="([^"]*)"', html, re.I))
    print(f"  --- {len(fields)} שדות טופס: {[k for k in fields][:20]}")

    action = re.search(r'<form[^>]+action="([^"]+)"', html, re.I)
    print(f"  --- action: {action.group(1) if action else 'לא נמצא'}")

    selects = re.findall(r'<select[^>]+name="([^"]+)"', html, re.I)
    print(f"  --- select: {selects[:15]}")

    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html, re.I)
    print(f"  --- {len(scripts)} סקריפטים: {scripts[:15]}")

    handlers = re.findall(r'["\']([^"\'\s]*\.(?:ashx|asmx|svc|json)[^"\'\s]*)["\']', html, re.I)
    print(f"  --- handlers אפשריים: {list(dict.fromkeys(handlers))[:15]}")

    for marker in ("NOTAM", "Q)", "NOTAMN", "iframe", "GridView", "RadGrid"):
        if marker in html:
            print(f"  --- הדף מכיל '{marker}'")

    frames = re.findall(r'<iframe[^>]+src="([^"]+)"', html, re.I)
    if frames:
        print(f"  --- iframes: {frames[:10]}")

    # איפה התוכן באמת יושב בדף
    for label, pattern in (
        ("מזהי נוטאם", r"\b[A-Z]\d{1,4}/\d{2}\b"),
        ("שורות Q", r"Q\)\s*\w{4}/"),
        ("המילה NOTAM", r"NOTAM"),
        ("METAR", r"METAR"),
        ("TAF", r"\bTAF\b"),
    ):
        hits = list(re.finditer(pattern, html))
        print(f"  --- {label}: {len(hits)} מופעים")
        for m in hits[:2]:
            excerpt = html[max(0, m.start() - 200): m.start() + 400]
            excerpt = re.sub(r"<[^>]+>", " ", excerpt)
            excerpt = re.sub(r"\s+", " ", excerpt).strip()
            print(f"      …{excerpt[:400]}…")

    options = re.findall(r"<option[^>]*value=\"([^\"]*)\"[^>]*>([^<]*)</option>", html, re.I)
    print(f"  --- {len(options)} אפשרויות ברשימות נפתחות (20 ראשונות):")
    for value, text in options[:20]:
        print(f"      {value!r} = {text.strip()!r}")

    # הדף מכיל מזהי נוטאם אבל לא שורות Q — כלומר זו רשימה, והטקסט המלא
    # נמשך בנפרד. מדפיסים HTML גולמי סביב המזהה הראשון כדי לראות איך
    # השורה בנויה ומה מפעיל את הטעינה.
    first = re.search(r"\b[A-Z]\d{1,4}/\d{2}\b", html)
    if first:
        print("  --- HTML גולמי סביב המזהה הראשון:")
        print("  " + html[max(0, first.start() - 900): first.start() + 900].replace("\n", "\n  "))

    # טקסט ההודעה בדף הרשימה **קטוע** — הוא נחתך בדיוק היכן שהקואורדינטות
    # אמורות להופיע ("CENTERED ON PSN"). ההודעה המלאה מגיעה משירות נפרד,
    # ולכן צריך את הבנייה המלאה של requestURL ולא רק את שם ה-op.
    js, status, _ = fetch("https://brin.iaa.gov.il/aeroinfo/JS/MoreInfo.js")
    if js:
        print(f"\n  --- MoreInfo.js ({status}, {len(js):,} bytes) — בניית הבקשה:")
        for m in re.finditer(r"^.*(?:requestURL|\.asmx|\.open\s*\(|responseXML|responseText).*$", js, re.M):
            print(f"      {m.group(0).strip()[:190]}")

    # (1) הבקשה שמביאה את ההודעה המלאה — שורת Q וזמני תוקף.
    js, status, _ = fetch("https://brin.iaa.gov.il/aeroinfo/JS/MoreInfo.js")
    if js:
        print(f"\n  --- MoreInfo.js ({status}, {len(js):,} bytes) — כל שורה עם requestURL/asmx:")
        for m in re.finditer(r"^.*(?:requestURL|asmx|\.open\s*\(|send\().*$", js, re.M):
            print(f"      {m.group(0).strip()[:200]}")

    # (3) קואורדינטות תחנות, כדי שאפשר יהיה לסמן מזג אוויר על המפה
    # בלי להמציא מיקומים.
    js, status, _ = fetch("https://brin.iaa.gov.il/aeroinfo/JS/Locations.js")
    if js:
        print(f"\n  --- Locations.js ({status}, {len(js):,} bytes):")
        print("      " + js[:1500].replace("\n", "\n      "))

    # (4) שכבות רט"ג — 542 שמורות טבע שאין להן קואורדינטות בפמ"ת.
    for name, url in (
        ("רט\"ג — דף טיסה", "https://www.parks.org.il/new/tisa/"),
        ("רת\"א — פרק 11", "https://www.gov.il/he/Departments/Guides/aip?chapterIndex=11"),
    ):
        page, status, _ = fetch(url)
        print(f"\n  --- {name} ({status}, {len(page):,} bytes)" if page else f"\n  --- {name}: נכשל")
        if not page:
            continue
        files = re.findall(r'href="([^"]*\.(?:kml|kmz|zip|geojson|json|shp|gpx)[^"]*)"', page, re.I)
        print(f"      {len(files)} קישורי שכבה:")
        for f in dict.fromkeys(files)[:20] if isinstance(files, list) else []:
            print(f"        {f}")
        for word in ("kml", "kmz", "geojson", "shapefile", "ArcGIS", "arcgis", "MapServer"):
            if word.lower() in page.lower():
                print(f"      הדף מזכיר '{word}'")

    # דף מזג האוויר החזיר 0 דיווחים — כנראה מבנה טבלה אחר. מדפיסים את
    # שמות המחלקות של התאים ואת השורה הראשונה בגולמי.
    wx, status, _ = fetch(
        "https://brin.iaa.gov.il/aeroinfo/AeroInfo.aspx?msgType=Weather",
        extra={"Referer": IAA_URL},
    )
    if wx:
        classes = {}
        for c in re.findall(r'<td[^>]*class="([^"]+)"', wx):
            classes[c] = classes.get(c, 0) + 1
        print(f"\n  --- msgType=Weather ({status}, {len(wx):,} bytes)")
        print(f"      מחלקות תאים: {sorted(classes.items(), key=lambda kv: -kv[1])[:12]}")
        m = re.search(r"METAR|TAF", wx)
        if m:
            start = wx.rfind("<tr", 0, m.start())
            print("      --- שורה גולמית סביב הדיווח הראשון:")
            print("      " + wx[max(0, start): m.start() + 700].replace("\n", "\n      ")[:2200])

    print("  --- 1,200 התווים הראשונים:")
    print("  " + html[:1200].replace("\n", "\n  "))

    # POST חוזר עם ה-VIEWSTATE — הדפוס שמפעיל טבלאות ב-WebForms
    if "__VIEWSTATE" in fields:
        payload = urllib.parse.urlencode(
            {k: v for k, v in fields.items() if k.startswith("__")}
        ).encode()
        body, status, ctype = fetch(
            IAA_URL, payload,
            {"Content-Type": "application/x-www-form-urlencoded", "Referer": IAA_URL},
        )
        if body is not None:
            found = extract_from_response(body, ctype)
            print(f"\n  POST → HTTP {status}  {len(body):,} bytes  →  {len(found)} נוטאמים")
            if found:
                print("  --- הראשון:")
                print("  " + found[0][:800].replace("\n", "\n  "))


def main() -> int:
    print("=" * 72)
    print("אבחון מקורות נוטאמים")
    print("=" * 72)

    probe_iaa()

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
