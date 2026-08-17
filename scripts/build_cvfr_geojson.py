#!/usr/bin/env python3
"""נתיבי CVFR מ-data.gov.il ל-data/cvfr-routes.geojson.

## מה זה פותר

עד עכשיו הנתיבים על המפה הגיעו **מהנוטאמים בלבד** — רצף נקודות
שנוטאם מנסח, כמו `EIRON-ZMGID-AFULA-TAVOR`. זה נתן 18 קווים, וכולם
נתיבים **סגורים**. הרשת עצמה, זו שטסים בה כשהכול פתוח, לא הייתה שם:
בפמ"ת היא מופיעה כמפה מצוירת ולא כנתונים.

המאגר "נתיבי טיסה" של משרד התחבורה מפרסם את הרשת כ-shapefile.

## למה לא ה-CSV

באותו מאגר יש גם `CVFR_csv`, והוא **חסר ערך**: רשומה אחת עם
`Shape_Length` ו-`Shape_Area` בלבד. הייצוא לטבלה איבד את הגיאומטריה,
כי קו אינו נכנס לתא. ה-SHP הוא המשאב היחיד עם הקווים עצמם.

## מערכת קואורדינטות

המקור ב-Israel TM Grid, כמו שכבת רט"ג. אותה המרה ל-WGS84, ומאותה
סיבה: בלעדיה אי אפשר להציג על מפת רשת. שבע ספרות עשרוניות ≈ סנטימטר.

שימוש:
    python3 scripts/build_cvfr_geojson.py               # מוריד
    python3 scripts/build_cvfr_geojson.py --zip a.zip   # מקובץ מקומי
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "cvfr-routes.geojson")

SOURCE_URL = (
    "https://e.data.gov.il/dataset/360fb8b4-ea71-4485-b80b-c5b996d25cae"
    "/resource/e5436712-2829-4079-982f-576195277766/download/cvfr_mot.zip"
)
DATASET_URL = "https://data.gov.il/dataset/cvfr"

ITM = "EPSG:2039"
WGS84 = "EPSG:4326"
PRECISION = 7

ATTRIBUTION = "משרד התחבורה — מאגר נתיבי טיסה"

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def fetch_zip(path: str | None) -> zipfile.ZipFile:
    if path:
        return zipfile.ZipFile(path)
    print(f"מוריד {SOURCE_URL}", file=sys.stderr)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": BROWSER_UA})
    with urllib.request.urlopen(request, timeout=180) as resp:
        blob = resp.read()
    print(f"  {len(blob):,} bytes", file=sys.stderr)
    return zipfile.ZipFile(io.BytesIO(blob))


def extract(archive: zipfile.ZipFile) -> str:
    """מחלץ לתיקייה זמנית ומחזיר את נתיב ה-.shp הראשון."""
    directory = tempfile.mkdtemp(prefix="cvfr-")
    found = None
    for info in archive.infolist():
        name = info.filename
        # שמות עבריים בארכיון מקודדים בעברית של DOS.
        try:
            name = name.encode("cp437").decode("cp862")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
        destination = os.path.join(directory, os.path.basename(name))
        with open(destination, "wb") as fh:
            fh.write(archive.read(info))
        if destination.lower().endswith(".shp"):
            found = destination
    if not found:
        raise SystemExit("לא נמצא .shp בארכיון")
    return found


def clean(value) -> str | None:
    text = str(value or "").strip()
    return text if text and text.lower() not in ("none", "nan") else None


def build(shp_path: str) -> dict:
    import shapefile
    from pyproj import Transformer

    transformer = Transformer.from_crs(ITM, WGS84, always_xy=True)
    reader = shapefile.Reader(shp_path, encoding="utf-8")
    field_names = [f[0] for f in reader.fields[1:]]
    print(f"  שדות: {field_names}", file=sys.stderr)

    features = []
    skipped = 0
    for shape, record in zip(reader.shapes(), reader.records()):
        attrs = record.as_dict()
        parts = list(shape.parts) + [len(shape.points)]
        lines = []
        for index in range(len(parts) - 1):
            segment = shape.points[parts[index]: parts[index + 1]]
            if len(segment) < 2:
                continue
            lines.append([
                [round(lon, PRECISION), round(lat, PRECISION)]
                for lon, lat in (transformer.transform(x, y) for x, y in segment)
            ])
        if not lines:
            skipped += 1
            continue

        geometry = ({"type": "LineString", "coordinates": lines[0]} if len(lines) == 1
                    else {"type": "MultiLineString", "coordinates": lines})
        # שומרים כל שדה טקסטואלי שיש בו תוכן; שמות השדות משתנים בין
        # גרסאות המאגר, ועדיף לשמור מה שיש מאשר לקבע רשימה שתישבר.
        properties = {k: clean(v) for k, v in attrs.items() if clean(v)}
        properties["source"] = ATTRIBUTION
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})

    if skipped:
        print(f"  {skipped} רשומות דולגו (פחות משתי נקודות)", file=sys.stderr)
    vertices = sum(
        len(line)
        for feature in features
        for line in ([feature["geometry"]["coordinates"]]
                     if feature["geometry"]["type"] == "LineString"
                     else feature["geometry"]["coordinates"])
    )
    print(f"  {len(features)} נתיבים · {vertices:,} קודקודים", file=sys.stderr)

    return {
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": ATTRIBUTION,
        "source_url": DATASET_URL,
        "note": "הומר מ-Israel TM Grid ל-WGS84. ללא פישוט גיאומטריה.",
        "features": features,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", help="ארכיון מקומי במקום הורדה")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    payload = build(extract(fetch_zip(args.zip)))
    if not payload["features"]:
        raise SystemExit("אפס נתיבים — לא כותבים קובץ ריק על קובץ תקין")

    if args.dry_run:
        print("--dry-run: לא נכתב קובץ.", file=sys.stderr)
        return 0

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        fh.write("\n")
    print(f"נכתב {OUTPUT_PATH} ({os.path.getsize(OUTPUT_PATH):,} bytes)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
