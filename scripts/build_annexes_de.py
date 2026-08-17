#!/usr/bin/env python3
"""חילוץ נספחים ד' ו-ה' מהפמ"ת המלא.

שני פלטים:

1. `data/aip-obstacles.geojson` — **מכשולים קבועים** מנספח ד'. שמונה
   בלוני ריגול מעוגנים, עם מיקום, רדיוס וגובה. שכבה שלא הייתה כאן
   בכלל, ומסוכנת בדיוק בגלל שהיא קטנה: כבל של בלון בגובה 3,400 רגל
   אינו מופיע בשום מפה רגילה.

2. **העשרת `data/ratag-reserves.geojson`** בגובה המרבי מנספח ה'.
   לרט"ג יש הגבולות ולפמ"ת יש הגבהים, ורק החיבור ביניהם הופך פוליגון
   ירוק למגבלה עם מספר.

## על החיבור — למה רק התאמה מדויקת

542 רשומות בנספח ה', 926 פוליגונים אצל רט"ג, **395 מתחברים בהתאמה
מדויקת של השם** (72%). הפיתוי להוסיף התאמה מטושטשת ולהעלות את המספר
גדול, ומסוכן: התאמה שגויה מדביקה את הגובה של שמורה אחת לגבולות של
אחרת, והתוצאה היא מגבלה שנראית סמכותית ואינה נכונה. פוליגון בלי גובה
אומר "לא ידוע"; פוליגון עם גובה שגוי משקר.

לכן ההתאמה היחידה שמתבצעת היא על שם מנורמל — הסרת גרשיים וכיווץ
רווחים בלבד. השאר נשארים בלי גובה, והמספר מדווח.

שימוש:
    python3 scripts/build_annexes_de.py                # מוריד מה-Release
    python3 scripts/build_annexes_de.py --pdf a.pdf    # מקובץ מקומי
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aip_annexes_de as annexes  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBSTACLES_PATH = os.path.join(REPO_ROOT, "data", "aip-obstacles.geojson")
RESERVES_PATH = os.path.join(REPO_ROOT, "data", "ratag-reserves.geojson")

SOURCE_URL = "https://github.com/nadaval56/airspace/releases/download/aip-source/pamat.pdf"

# טווחי העמודים אומתו מול המסמך. הם נבדקים בזמן ריצה — אם המבנה
# ישתנה בעדכון הבא, הסקריפט יצעק ולא ימציא.
OBSTACLES_PAGE = 81
RESERVES_PAGES = range(82, 102)

SOURCE_LABEL = 'פמ"ת א-17, נספח ד\''


def load_pdf(path: str | None):
    import pdfplumber

    if path:
        return pdfplumber.open(path)
    print(f"מוריד {SOURCE_URL}", file=sys.stderr)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "binyamin-airspace/1.0"})
    with urllib.request.urlopen(request, timeout=600) as resp:
        blob = resp.read()
    print(f"  {len(blob):,} bytes", file=sys.stderr)
    return pdfplumber.open(io.BytesIO(blob))


# ---------------------------------------------------------------------------
# נספח ד' — מכשולים
# ---------------------------------------------------------------------------

# מספר הצלעות בקירוב העיגול. 48 נותן קו חלק בכל זום סביר, ומכשול
# ברדיוס 0.54 מייל הוא ממילא נקודה כמעט בכל קנה מידה.
CIRCLE_STEPS = 48
NM_TO_DEG_LAT = 1.0 / 60.0


def circle(lat: float, lon: float, radius_nm: float) -> list[list[float]]:
    """מקרב עיגול לפוליגון. הרוחב מתקצר עם הקוסינוס של קו הרוחב."""
    import math

    ring = []
    lat_rad = math.radians(lat)
    for step in range(CIRCLE_STEPS + 1):
        angle = 2 * math.pi * step / CIRCLE_STEPS
        d_lat = radius_nm * NM_TO_DEG_LAT * math.cos(angle)
        d_lon = radius_nm * NM_TO_DEG_LAT * math.sin(angle) / max(math.cos(lat_rad), 1e-6)
        ring.append([round(lon + d_lon, 6), round(lat + d_lat, 6)])
    return ring


def build_obstacles(pdf) -> dict:
    text = pdf.pages[OBSTACLES_PAGE - 1].extract_text() or ""
    rows = annexes.parse_obstacles(text)
    if not rows:
        raise SystemExit(f"נספח ד' לא נמצא בעמוד {OBSTACLES_PAGE} — המבנה השתנה?")

    features = []
    skipped = 0
    for row in rows:
        if not row.get("radius_nm"):
            # בלי רדיוס אין גיאומטריה, ולא ממציאים אחד.
            skipped += 1
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [circle(row["lat"], row["lon"], row["radius_nm"])]},
            "properties": {
                "id": row["id"],
                "name": row["name"],
                "type": "מכשול קבוע",
                "lower_limit": "GND",
                "upper_limit": str(row["upper_ft"]) if row["upper_ft"] else None,
                "radius_nm": row["radius_nm"],
                "source": SOURCE_LABEL,
            },
        })
    if skipped:
        print(f"  {skipped} מכשולים דולגו (בלי רדיוס)", file=sys.stderr)
    print(f"  {len(features)} מכשולים קבועים", file=sys.stderr)

    return {
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": SOURCE_LABEL,
        "features": features,
    }


# ---------------------------------------------------------------------------
# נספח ה' — גבהים לשמורות
# ---------------------------------------------------------------------------


def normalise(name: str) -> str:
    """נרמול שמרני: גרשיים ורווחים בלבד. בלי נגיעה באותיות."""
    return re.sub(r"\s+", " ", re.sub(r"[\"'’״׳]", "", name or "")).strip()


def enrich_reserves(pdf) -> tuple[int, int]:
    rows = []
    for number in RESERVES_PAGES:
        for table in pdf.pages[number - 1].extract_tables():
            rows.extend(annexes.parse_reserves(table))
    if not rows:
        raise SystemExit("נספח ה' לא נמצא — המבנה השתנה?")
    print(f"  {len(rows)} רשומות בנספח ה'", file=sys.stderr)

    by_name: dict[str, dict] = {}
    for row in rows:
        by_name.setdefault(normalise(row["name"]), row)

    with open(RESERVES_PATH, encoding="utf-8") as fh:
        reserves = json.load(fh)

    matched = 0
    for feature in reserves["features"]:
        properties = feature["properties"]
        entry = None
        for key in ("name", "name_full"):
            entry = by_name.get(normalise(properties.get(key) or ""))
            if entry:
                break
        # מנקים קודם, כדי שהרצה חוזרת אחרי שינוי לא תשאיר שאריות.
        properties.pop("aip_id", None)
        properties.pop("aip_upper_ft", None)
        if entry:
            properties["aip_id"] = entry["id"]
            properties["aip_upper_ft"] = entry["upper_ft"]
            matched += 1

    reserves["aip_annex"] = 'פמ"ת א-17, נספח ה\''
    reserves["aip_matched"] = matched
    reserves["aip_total"] = len(rows)
    with open(RESERVES_PATH, "w", encoding="utf-8") as fh:
        json.dump(reserves, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")

    return matched, len(reserves["features"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", help="קובץ מקומי במקום הורדה")
    parser.add_argument("--dry-run", action="store_true", help="לא כותב לקבצים")
    args = parser.parse_args()

    pdf = load_pdf(args.pdf)

    print("נספח ד' — מכשולים קבועים:", file=sys.stderr)
    obstacles = build_obstacles(pdf)

    if args.dry_run:
        print("--dry-run: לא נכתב קובץ.", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(OBSTACLES_PATH), exist_ok=True)
    with open(OBSTACLES_PATH, "w", encoding="utf-8") as fh:
        json.dump(obstacles, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"נכתב {OBSTACLES_PATH}", file=sys.stderr)

    print("נספח ה' — גבהים לשמורות:", file=sys.stderr)
    if os.path.exists(RESERVES_PATH):
        matched, total = enrich_reserves(pdf)
        print(f"  {matched}/{total} פוליגונים קיבלו גובה מהפמ\"ת", file=sys.stderr)
    else:
        print("  אין שכבת רט\"ג — מדלגים.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
