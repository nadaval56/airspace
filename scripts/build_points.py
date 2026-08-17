#!/usr/bin/env python3
"""חילוץ נקודות הדיווח ונקודות הייחוס מהפמ"ת המלא ל-data/aip-points.json.

הטבלה "מפת נתיבי תובלה נמוכים" פותרת שתי בעיות שנתקענו בהן:

* **מיקום תחנות מזג האוויר** — LLBG, LLHA, LLER, LLIB, LLHZ מופיעות
  שם עם נקודת הייחוס שלהן. עד היום METAR ו-TAF הופיעו ברשימה בלבד,
  כי לא היה שום מקור אמין למיקום התחנה ולא הסכמנו להמציא אחד.
* **נקודות הדיווח** שהנוטאמים מפנים אליהן בשמן.

שימוש:
    python3 scripts/build_points.py                 # מוריד מה-Release
    python3 scripts/build_points.py --pdf a.pdf     # מקובץ מקומי
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aip_points  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "aip-points.json")

SOURCE_URL = "https://github.com/nadaval56/airspace/releases/download/aip-source/pamat.pdf"

# הטבלה יושבת בעמודים האלה. אומת מול המסמך, ונבדק בזמן ריצה.
PAGES = range(113, 116)
MIN_EXPECTED = 150

SOURCE_LABEL = 'פמ"ת — מפת נתיבי תובלה נמוכים'


def load_pdf(path: str | None):
    import pdfplumber

    if path:
        return pdfplumber.open(path)
    print(f"מוריד {SOURCE_URL}", file=sys.stderr)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "binyamin-airspace/1.0"})
    with urllib.request.urlopen(request, timeout=600) as resp:
        blob = resp.read()
    return pdfplumber.open(io.BytesIO(blob))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", help="קובץ מקומי במקום הורדה")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pdf = load_pdf(args.pdf)
    raw = []
    for number in PAGES:
        raw.extend(aip_points.parse_points(pdf.pages[number - 1].extract_text() or ""))
    points = aip_points.dedupe(raw)

    # אם המבנה ישתנה בעדכון הבא, עדיף שהסקריפט ייפול מאשר שיכתוב
    # קובץ חלקי שנראה תקין.
    if len(points) < MIN_EXPECTED:
        raise SystemExit(f"רק {len(points)} נקודות — צפויות לפחות {MIN_EXPECTED}. המבנה השתנה?")

    aerodromes = [p for p in points if p["icao"]]
    print(f"  {len(points)} נקודות, מהן {len(aerodromes)} שדות תעופה", file=sys.stderr)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": SOURCE_LABEL,
        "counts": {"total": len(points), "aerodromes": len(aerodromes)},
        # מפתח לפי ICAO, כדי שהדף ימצא תחנת מזג אוויר בלי לסרוק רשימה.
        "aerodromes": {p["icao"]: {"lat": p["lat"], "lon": p["lon"]} for p in aerodromes},
        "points": points,
    }

    if args.dry_run:
        print("--dry-run: לא נכתב קובץ.", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"נכתב {OUTPUT_PATH}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
