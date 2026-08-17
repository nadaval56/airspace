#!/usr/bin/env python3
"""אבחון: למה ההורדה של cvfr_mot.zip אינה ZIP.

הריצה הראשונה של `build_cvfr_geojson.py` הורידה 42,766 בתים והם לא
ארכיון. גודל כזה אינו שגיאת 404 — הוא בדיוק בסדר הגודל של דף אתגר של
שירות הגנה (Incapsula/Radware) או של דף "ההורדה מתחילה". צריך לראות
מה זה באמת לפני שמנחשים תיקון.

הסקריפט מדפיס מה שהשרת החזיר — סטטוס, כותרות, החתימה הבינארית והתחלת
הגוף — עבור כמה דרכי גישה, ובנוסף שואל את CKAN מה כתובת ההורדה הרשמית
של המשאב במקום להסתמך על כתובת שהעתקתי.

לא כותב כלום. כלי חקירה בלבד.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import zipfile
import io

BASE = "https://data.gov.il/api/3/action"
PACKAGE = "cvfr"

DIRECT_URL = (
    "https://e.data.gov.il/dataset/360fb8b4-ea71-4485-b80b-c5b996d25cae"
    "/resource/e5436712-2829-4079-982f-576195277766/download/cvfr_mot.zip"
)

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# חתימות שמזהות מה באמת ירד.
SIGNATURES = {
    b"PK\x03\x04": "ZIP",
    b"PK\x05\x06": "ZIP ריק",
    b"<!DO": "HTML",
    b"<htm": "HTML",
    b"<HTM": "HTML",
    b"{": "JSON",
}


def describe(blob: bytes) -> str:
    for prefix, name in SIGNATURES.items():
        if blob.startswith(prefix):
            return name
    return "לא מזוהה"


def attempt(label: str, url: str, headers: dict[str, str]) -> bytes | None:
    print(f"\n--- {label}")
    print(f"    {url[:120]}")
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            blob = resp.read()
            status, final, info = resp.status, resp.geturl(), resp.headers
    except urllib.error.HTTPError as exc:
        blob = exc.read()
        status, final, info = exc.code, url, exc.headers
    except Exception as exc:  # noqa: BLE001
        print(f"    כשל: {type(exc).__name__}: {exc}")
        return None

    print(f"    HTTP {status} · {len(blob):,} bytes · {describe(blob)}")
    if final != url:
        print(f"    הופנה אל: {final[:120]}")
    for key in ("Content-Type", "Content-Disposition", "Content-Length", "Server",
                "X-CDN", "X-Iinfo", "Set-Cookie"):
        if info.get(key):
            print(f"    {key}: {str(info.get(key))[:160]}")

    head = blob[:400].decode("utf-8", errors="replace").replace("\n", " ")
    print(f"    התחלה: {head[:300]}")

    if blob.startswith(b"PK"):
        try:
            names = zipfile.ZipFile(io.BytesIO(blob)).namelist()
            print(f"    תוכן הארכיון: {names}")
        except Exception as exc:  # noqa: BLE001
            print(f"    ארכיון פגום: {exc}")
    return blob


def api(url: str):
    request = urllib.request.Request(
        url, headers={"User-Agent": BROWSER_UA, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    print("=" * 70)
    print("אבחון: הורדת ה-shapefile של נתיבי CVFR")
    print("=" * 70)

    # 1. מה CKAN אומר שכתובת ההורדה — לא מה שהעתקתי.
    print("\n=== כתובות רשמיות מ-CKAN ===")
    urls: list[tuple[str, str]] = []
    pkg = api(f"{BASE}/package_show?id={PACKAGE}")
    if pkg.get("success"):
        for res in pkg["result"].get("resources", []):
            fmt = str(res.get("format") or "").upper()
            print(f"  {fmt:>6}  {res.get('name')}")
            print(f"          {res.get('url')}")
            print(f"          size={res.get('size')} last_modified={res.get('last_modified')}")
            if fmt in ("ZIP", "SHP", "KMZ") and res.get("url"):
                urls.append((f"{fmt} · {res.get('name')}", res["url"]))
    else:
        print(f"  package_show נכשל: {json.dumps(pkg, ensure_ascii=False)[:300]}")

    # 2. הכתובת שנכשלה, בדיוק כמו שהסקריפט שלח אותה.
    print("\n=== הניסיון שנכשל ===")
    attempt("UA של דפדפן בלבד (כמו בסקריפט)", DIRECT_URL, {"User-Agent": BROWSER_UA})

    # 3. אותה כתובת עם כותרות מלאות של דפדפן. אם שירות הגנה חוסם,
    #    לפעמים Accept/Referer הם ההבדל.
    attempt(
        "כותרות דפדפן מלאות",
        DIRECT_URL,
        {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "he-IL,he;q=0.9,en;q=0.8",
            "Referer": "https://data.gov.il/dataset/cvfr",
            "Upgrade-Insecure-Requests": "1",
        },
    )

    # 4. כל כתובת שהמאגר עצמו נותן.
    print("\n=== הכתובות שהמאגר נותן ===")
    for label, url in urls:
        if url == DIRECT_URL:
            continue
        attempt(label, url, {"User-Agent": BROWSER_UA, "Referer": "https://data.gov.il/dataset/cvfr"})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
