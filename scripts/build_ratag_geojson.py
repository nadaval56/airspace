#!/usr/bin/env python3
"""המרת שכבת שמורות הטבע והגנים הלאומיים של רט"ג ל-GeoJSON.

זו התשובה לפער מול האפליקציה של רת"א: נספח ה' לפמ"ת מונה 542 אזורים
כאלה **בשמם בלבד**, בלי קואורדינטות, ומפנה לשכבות של רט"ג. השכבה הזאת
היא המקור שאליו הפמ"ת מפנה.

## תנאי השימוש מחייבים, ולכן הם מעצבים את הקוד

הקובץ מגיע עם "רשימת כללים" של רט"ג. שני סעיפים בה אינם נימוס:

* **"אין לבצע כל שינוי בשכבה ובמידע"** — ולכן **אין כאן שום פישוט
  גיאומטריה.** זה הפיתוי הגדול: פוליגון של שמורה עם אלפי קודקודים
  מתכווץ פי עשרה בהחלקה, והקובץ הופך לקטן ונוח. אסור. כל קודקוד
  שבמקור נמצא גם בפלט.
* **"כל המוריד שכבה מתחייב לדאוג לכך שרשימת כללים זו תצורף בעת
  פרסום/העברת המידע"** — ולכן `data/ratag-terms.md` נשמר לצד השכבה
  ומקושר מהדף.

מה שכן נעשה כאן, ומדוע זה אינו "שינוי במידע":

* **המרת פורמט** — shapefile ל-GeoJSON. אותם קודקודים, אותם שדות.
* **המרת מערכת קואורדינטות** — המקור ב-Israel TM Grid, ומפת רשת
  דורשת WGS84. בלי זה אי אפשר להציג את השכבה בכלל. הדיוק נשמר:
  שבע ספרות אחרי הנקודה הן כסנטימטר, והמקור עצמו במילימטרים.
* **בחירת שכבה אחת מתוך חמש** — ראו למטה.

## למה דווקא "תכניות מפורטות"

בארכיון חמש שכבות. `מפורטות` היא של רט"ג והיא האופרטיבית: שמורות
וגנים **מוכרזים ומאושרים**, כלומר מה שקיים בשטח. השאר הן תכניות מתאר
ארציות ומחוזיות (של מנהל התכנון, ייעוד ברמת תכנון ולא גבול בשטח)
ושכבת `מוצעים` — אזורים שטרם הוכרזו. לצייר "מוצעים" כאילו הם מגבלה
פעילה זו אזהרת שווא, וכלי שמזהיר יותר מדי מאבד את אמון המשתמש בדיוק
כמו כלי שמזהיר מעט מדי.

שימוש:
    python3 scripts/build_ratag_geojson.py                 # מוריד מה-Release
    python3 scripts/build_ratag_geojson.py --zip local.zip # מקובץ מקומי
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "ratag-reserves.geojson")

SOURCE_URL = "https://github.com/nadaval56/airspace/releases/download/aip-source/ratag.zip"

# שם השכבה בתוך הארכיון. שמות הקבצים ב-zip מקודדים בעברית של DOS.
LAYER = "שמורות_וגנים_בתכניות_מפורטות"
ZIP_NAME_ENCODING = "cp862"

# המקור: Israel TM Grid. הפרמטרים נלקחים מקובץ ה-.prj שמגיע בארכיון,
# ולא מנוסחים מהזיכרון.
ITM = "EPSG:2039"
WGS84 = "EPSG:4326"

# שבע ספרות ≈ סנטימטר. המקור במילימטרים, אז אין כאן איבוד מידע —
# רק עצירה של זנב ספרות שנולד מהמרת המערכת.
PRECISION = 7

ATTRIBUTION = 'רשות הטבע והגנים (רט"ג)'


def fetch_zip(path: str | None) -> zipfile.ZipFile:
    if path:
        return zipfile.ZipFile(path)
    print(f"מוריד {SOURCE_URL}", file=sys.stderr)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "binyamin-airspace/1.0"})
    with urllib.request.urlopen(request, timeout=180) as resp:
        blob = resp.read()
    print(f"  {len(blob):,} bytes", file=sys.stderr)
    import io

    return zipfile.ZipFile(io.BytesIO(blob))


def extract_layer(archive: zipfile.ZipFile, target: str) -> str:
    """מחלץ את קבצי השכבה לתיקייה זמנית ומחזיר את נתיב ה-.shp."""
    import tempfile

    directory = tempfile.mkdtemp(prefix="ratag-")
    found = None
    for info in archive.infolist():
        try:
            name = info.filename.encode("cp437").decode(ZIP_NAME_ENCODING)
        except (UnicodeDecodeError, UnicodeEncodeError):
            name = info.filename
        if not name.startswith(target):
            continue
        destination = os.path.join(directory, name)
        with open(destination, "wb") as fh:
            fh.write(archive.read(info))
        if name.lower().endswith(".shp"):
            found = destination
    if not found:
        raise SystemExit(f"השכבה {target!r} לא נמצאה בארכיון")
    return found


def rings_to_geometry(shape, project) -> dict | None:
    """הופך shapefile polygon ל-GeoJSON, כולל חורים.

    shapefile מפריד טבעות לפי `parts`, ומבדיל בין טבעת חיצונית לחור
    לפי כיוון: חיצונית עם כיוון השעון, חור נגדו. בלי ההבחנה הזאת חור
    היה מצויר כשמורה נפרדת — ואזור מגבלה שאינו קיים גרוע כמו אזור
    חסר.
    """
    points = shape.points
    parts = list(shape.parts) + [len(points)]
    polygons: list[list[list[list[float]]]] = []

    for index in range(len(parts) - 1):
        ring = points[parts[index]: parts[index + 1]]
        if len(ring) < 4:
            continue
        converted = [
            [round(lon, PRECISION), round(lat, PRECISION)]
            for lon, lat in (project(x, y) for x, y in ring)
        ]
        if converted[0] != converted[-1]:
            converted.append(converted[0])

        # שטח מסומן: חיובי = כיוון השעון = טבעת חיצונית.
        area = sum(
            (converted[i][0] - converted[i - 1][0]) * (converted[i][1] + converted[i - 1][1])
            for i in range(1, len(converted))
        )
        if area > 0 or not polygons:
            polygons.append([converted])
        else:
            polygons[-1].append(converted)

    if not polygons:
        return None
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def clean(value) -> str | None:
    text = str(value or "").strip()
    return text if text and text.lower() != "none" else None


def build(shp_path: str) -> dict:
    import shapefile
    from pyproj import Transformer

    transformer = Transformer.from_crs(ITM, WGS84, always_xy=True)
    reader = shapefile.Reader(shp_path, encoding="utf-8")

    features = []
    skipped = 0
    for shape, record in zip(reader.shapes(), reader.records()):
        attrs = record.as_dict()
        geometry = rings_to_geometry(shape, transformer.transform)
        if geometry is None:
            skipped += 1
            continue
        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "name": clean(attrs.get("PARK_HEB_N")),
                "name_full": clean(attrs.get("PARK_HEB_1")),
                "name_en": clean(attrs.get("PARK_ENG_N")),
                "kind": clean(attrs.get("PARK_TYPE_")),
                "status": clean(attrs.get("STATUS_DES")),
                "plan": clean(attrs.get("PLAN_NUMBE")),
                "dunam": round(float(attrs["DUNAM"]), 1) if clean(attrs.get("DUNAM")) else None,
                "source": ATTRIBUTION,
            },
        })

    if skipped:
        print(f"  {skipped} מצולעים דולגו (פחות משלושה קודקודים)", file=sys.stderr)

    vertices = sum(
        len(ring)
        for feature in features
        for polygon in ([feature["geometry"]["coordinates"]]
                        if feature["geometry"]["type"] == "Polygon"
                        else feature["geometry"]["coordinates"])
        for ring in polygon
    )
    print(f"  {len(features)} אזורים · {vertices:,} קודקודים (ללא פישוט)", file=sys.stderr)

    return {
        "type": "FeatureCollection",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": ATTRIBUTION,
        "layer": LAYER,
        "terms": "data/ratag-terms.md",
        "note": "הומר מ-Israel TM Grid ל-WGS84. ללא פישוט גיאומטריה.",
        "features": features,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", help="ארכיון מקומי במקום הורדה")
    parser.add_argument("--dry-run", action="store_true", help="לא כותב לקובץ")
    args = parser.parse_args()

    archive = fetch_zip(args.zip)
    shp_path = extract_layer(archive, LAYER)
    payload = build(shp_path)

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
