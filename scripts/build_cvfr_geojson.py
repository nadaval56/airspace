#!/usr/bin/env python3
"""נתיבי CVFR מ-data.gov.il ל-data/cvfr-routes.geojson.

## מה זה פותר

עד עכשיו הנתיבים על המפה הגיעו **מהנוטאמים בלבד** — רצף נקודות
שנוטאם מנסח, כמו `EIRON-ZMGID-AFULA-TAVOR`. זה נתן 18 קווים, וכולם
נתיבים **סגורים**. הרשת עצמה, זו שטסים בה כשהכול פתוח, לא הייתה שם:
בפמ"ת היא מופיעה כמפה מצוירת ולא כנתונים.

המאגר "נתיבי טיסה" של משרד התחבורה מפרסם את הרשת כ-shapefile.

## הנתיבים הם **שטחים**, לא קווים

זה לא מה שהנחתי כשכתבתי את הגרסה הראשונה, וטוב שבדקתי: `shapeType`
של הקובץ הוא 5, כלומר POLYGON. נתיב CVFR אינו קו מרכז אלא **פרוזדור
עם רוחב**, והמאגר מוסר אותו ככזה. ציור קו מרכז היה מציג נתיב צר
פי כמה ממה שהוא, וטייס שסומך על זה חושב שהוא בתוך הנתיב כשהוא לא.

המבנה: רשומה אחת, 85 טבעות — טבעת חיצונית אחת של 21,570 קמ"ר
ו-84 חורים. זו רשת מחוברת של פרוזדורים, והחורים הם השטחים הכלואים
*בין* הפרוזדורים. ההפרש מאמת את עצמו מול ה-DBF:

    21,570 − 17,360 = 4,210 קמ"ר  =  Shape_Area שבקובץ, בדיוק

בלי הפרדת החורים היינו מציירים 21,570 קמ"ר של "מותר לטוס" במקום
4,210 — טעות פי חמישה, בכיוון המסוכן.

## למה לא ה-CSV

באותו מאגר יש גם `CVFR_csv`, והוא **חסר ערך**: רשומה אחת עם
`Shape_Length` ו-`Shape_Area` בלבד. הייצוא לטבלה איבד את הגיאומטריה,
כי פוליגון אינו נכנס לתא. ה-SHP הוא המשאב היחיד עם הצורות עצמן.

## למה לא מורידים ישירות מ-data.gov.il

ניסינו, ותיעדנו. `e.data.gov.il` ו-`data.gov.il` כאחד מחזירים לכל
כתובת הורדה **בדיוק** את אותם 42,766 בתים: HTTP 200, `text/html`,
דף אתגר JavaScript מעורפל — לא ארכיון. שינוי כותרות לא עוזר, ושני
המארחים מתנהגים זהה. במקביל `data.gov.il/api` מחזיר JSON תקין,
כלומר החסימה היא של נתיב ההורדה בלבד.

פתרון האתגר הוא עקיפה של הגנת בוטים, ואנחנו לא עושים את זה. במקום
זה אותו מסלול שכבר עובד לרט"ג ולפמ"ת: מורידים את הקובץ בדפדפן —
שם האתגר נפתר מעצמו כרגיל — ומעלים אותו כנכס ל-release. משם ההורדה
חופשית, גם מ-Actions וגם מכל רשת.

## מערכת קואורדינטות

המקור ב-Israel TM Grid, כמו שכבת רט"ג. אותה המרה ל-WGS84, ומאותה
סיבה: בלעדיה אי אפשר להציג על מפת רשת. שבע ספרות עשרוניות ≈ סנטימטר.

שימוש:
    python3 scripts/build_cvfr_geojson.py               # מה-release
    python3 scripts/build_cvfr_geojson.py --zip a.zip   # מקובץ מקומי
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_PATH = os.path.join(REPO_ROOT, "data", "cvfr-routes.geojson")

SOURCE_URL = "https://github.com/nadaval56/airspace/releases/download/cvfr/cvfr_mot.zip"

# הכתובת המקורית במאגר. נשמרת כתיעוד של המקור ושל מה שצריך להוריד
# כשמשרד התחבורה מפרסם עדכון — לא כתובת שהסקריפט מושך ממנה.
UPSTREAM_URL = (
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
    try:
        with urllib.request.urlopen(request, timeout=180) as resp:
            blob = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise SystemExit(
                f"הנכס אינו קיים בכתובת {SOURCE_URL}\n"
                f"יש להוריד את הארכיון בדפדפן מ-{UPSTREAM_URL}\n"
                "ולהעלות אותו כנכס ל-release עם התג cvfr, בשם cvfr_mot.zip."
            ) from exc
        raise
    print(f"  {len(blob):,} bytes", file=sys.stderr)
    if not blob.startswith(b"PK"):
        raise SystemExit(
            f"מה שירד אינו ארכיון ({len(blob):,} בתים, מתחיל ב-{blob[:16]!r}). "
            "לא ממשיכים על סמך ניחוש."
        )
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


def ring_area(ring: list[list[float]]) -> float:
    """שטח מסומן. חיובי = כיוון השעון = טבעת חיצונית; שלילי = חור."""
    return sum(
        (ring[i][0] - ring[i - 1][0]) * (ring[i][1] + ring[i - 1][1])
        for i in range(1, len(ring))
    ) / 2


def rings_to_geometry(shape, transformer) -> dict | None:
    """הופך פוליגון של shapefile ל-GeoJSON, כולל חורים.

    shapefile מפריד טבעות לפי `parts` ואינו מסמן מי חור — ההבחנה היא
    בכיוון בלבד. כאן זה קריטי: הרשת היא טבעת חיצונית אחת עם 84 חורים,
    ובלי ההפרדה היינו מציירים פי חמישה שטח "מותר לטוס" ממה שיש.
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
            for lon, lat in (transformer.transform(x, y) for x, y in ring)
        ]
        if converted[0] != converted[-1]:
            converted.append(converted[0])

        if ring_area(converted) > 0 or not polygons:
            polygons.append([converted])
        else:
            polygons[-1].append(converted)

    if not polygons:
        return None
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    return {"type": "MultiPolygon", "coordinates": polygons}


def build(shp_path: str) -> dict:
    import shapefile
    from pyproj import Transformer

    transformer = Transformer.from_crs(ITM, WGS84, always_xy=True)
    reader = shapefile.Reader(shp_path, encoding="utf-8")
    field_names = [f[0] for f in reader.fields[1:]]
    kind = shapefile.SHAPETYPE_LOOKUP.get(reader.shapeType, reader.shapeType)
    print(f"  סוג: {kind} · שדות: {field_names}", file=sys.stderr)

    # הגרסה הראשונה הניחה קווים והייתה מציירת קו מרכז במקום פרוזדור.
    # אם המאגר יעבור יום אחד לקווים, עדיף להיעצר מאשר להמשיך בשקט.
    if reader.shapeType not in (5, 15, 25):
        raise SystemExit(
            f"הקובץ אינו פוליגון אלא {kind}. הנתיבים הם פרוזדורים עם רוחב, "
            "ושינוי כזה במקור מחייב בדיקה ולא המרה אוטומטית."
        )

    features = []
    skipped = 0
    for shape, record in zip(reader.shapes(), reader.records()):
        geometry = rings_to_geometry(shape, transformer)
        if not geometry:
            skipped += 1
            continue
        # שומרים כל שדה טקסטואלי שיש בו תוכן; שמות השדות משתנים בין
        # גרסאות המאגר, ועדיף לשמור מה שיש מאשר לקבע רשימה שתישבר.
        properties = {k: clean(v) for k, v in record.as_dict().items() if clean(v)}
        properties["source"] = ATTRIBUTION
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})

    if skipped:
        print(f"  {skipped} רשומות דולגו (ללא טבעת תקינה)", file=sys.stderr)

    rings = holes = vertices = 0
    for feature in features:
        coords = feature["geometry"]["coordinates"]
        polys = [coords] if feature["geometry"]["type"] == "Polygon" else coords
        for poly in polys:
            rings += 1
            holes += len(poly) - 1
            vertices += sum(len(ring) for ring in poly)
    print(
        f"  {len(features)} רשומות · {rings} טבעות חיצוניות · "
        f"{holes} חורים · {vertices:,} קודקודים",
        file=sys.stderr,
    )

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
