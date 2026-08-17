#!/usr/bin/env python3
"""אבחון: מאגר data.gov.il — האם יש שם נתיבי טיסה.

הכתובת שהתקבלה היא CKAN datastore. הסקריפט מושך דגימה, מדפיס את
שמות השדות ואת השורות הראשונות, ומחפש שדות שנראים כמו גיאומטריה.

הסקריפט לא כותב כלום. כלי חקירה בלבד.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

RESOURCE = "3811ad6d-ee91-4d18-87b4-c2f672f03a6a"
BASE = "https://data.gov.il/api/3/action"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def get(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace")), resp.status
    except urllib.error.HTTPError as exc:
        return {"error": exc.read().decode("utf-8", errors="replace")[:300]}, exc.code
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}, 0


def main() -> int:
    print("=" * 70)
    print("אבחון: data.gov.il")
    print("=" * 70)

    data, status = get(f"{BASE}/datastore_search?resource_id={RESOURCE}&limit=5")
    print(f"\ndatastore_search: HTTP {status}")
    if not data.get("success"):
        print("  ", json.dumps(data, ensure_ascii=False)[:400])
        return 1

    result = data["result"]
    print(f"  סה\"כ רשומות: {result.get('total'):,}")
    fields = [(f["id"], f["type"]) for f in result.get("fields", [])]
    print(f"  {len(fields)} שדות:")
    for name, kind in fields:
        print(f"    {name}  ({kind})")

    print("\n  --- שתי רשומות ראשונות:")
    for record in result.get("records", [])[:2]:
        for key, value in record.items():
            text = str(value)
            print(f"    {key}: {text[:150]}")
        print()

    # שם המאגר, כדי לדעת במה מדובר
    meta, status = get(f"{BASE}/resource_show?id={RESOURCE}")
    if meta.get("success"):
        r = meta["result"]
        print(f"  שם המשאב: {r.get('name')}")
        print(f"  פורמט: {r.get('format')} · תיאור: {str(r.get('description'))[:200]}")
        if r.get("package_id"):
            pkg, _ = get(f"{BASE}/package_show?id={r['package_id']}")
            if pkg.get("success"):
                p = pkg["result"]
                print(f"  מאגר: {p.get('title')}")
                print(f"  משאבים נוספים באותו מאגר:")
                for res in p.get("resources", [])[:12]:
                    print(f"    {res.get('format'):>8}  {res.get('name')}")
                    print(f"             {res.get('url')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
