"""פרסור נספחי ב' ו-ג' של פמ"ת פרק א-17.

מודול טהור — בלי רשת ובלי PDF. מקבל שורות טבלה ומחזיר Features.
נבדק ב-scripts/test_aip.py מול שורות אמיתיות מהמסמך.

## שני דברים שחשוב להבין לפני שקוראים את הקוד

**1. הטקסט יוצא הפוך.** pdfplumber מחלץ טקסט דו־כיווני, והתוצאה היא
שהעברית יוצאת הפוכה בעוד הלטינית והספרות יוצאות תקינות:

    'תיבה רה'  →  'הר הבית'        אבל  'LLP11' ו-'8000' תקינים כמו שהם

זה נוח דווקא: **הנתון הקריטי לבטיחות — הקואורדינטות — אינו עובר שום
טרנספורמציה.** רק השם, שאינו קריטי, צריך היפוך.

**2. חובה לקרוא את הטבלה כטבלה, לא כטקסט.** ניסיון ראשון קיבץ
קואורדינטות לפי טקסט שטוח, בהנחה שטבעת נסגרת כשהנקודה חוזרת לראשונה.
זה נתן פוליגונים "תקינים" לכאורה שנמתחו על 180 ק"מ — מטווח בגודל חצי
מדינה. `page.extract_tables()` מחזיר עמודות אמיתיות, ואז הכלל חד־משמעי:
**אזור חדש מתחיל בשורה שבה עמודת 'קוד זיהוי' מלאה, ונמשך עד הבאה.**
"""

from __future__ import annotations

import math
import re

# חיתוך לתיבה של מטה בנימין. כל הארץ תהפוך את המפה לבלתי קריאה.
BBOX = {"min_lon": 35.0, "min_lat": 31.7, "max_lon": 35.4, "max_lat": 32.1}

# סדרות המזהים בפמ"ת. הקידומת קובעת את הסיווג.
SERIES = {
    "LLP": "אסור",
    "LLR": "מוגבל",
    "LLD": "מסוכן",
    "LLU": "כטב\"ם",
}

# תא שהוא כולו מזהה אזור — עמודת "קוד זיהוי".
_CODE_CELL_RE = re.compile(r"^LL[PRDU]\s?\d{1,4}[A-Z]?$")

# זוג קואורדינטות DMS. הרווחים בין הרכיבים משתנים בין הנספחים, והצפון
# והמזרח יושבים בתאים נפרדים — לכן מחפשים על השורה המאוחדת.
_DMS_PAIR_RE = re.compile(
    r"""
    (?P<lat_d>\d{1,2})\s*°\s*(?P<lat_m>\d{1,2})\s*'\s*(?P<lat_s>\d{1,2}(?:\.\d+)?)\s*"\s*(?P<ns>[NS])
    \s*
    (?P<lon_d>\d{1,3})\s*°\s*(?P<lon_m>\d{1,2})\s*'\s*(?P<lon_s>\d{1,2}(?:\.\d+)?)\s*"\s*(?P<ew>[EW])
    """,
    re.X,
)

_ALT_CELL_RE = re.compile(r"^(?:GND|SFC|UNL|MSL|\d{3,5})$")

# יחידות מידה, בשתי הצורות (הפוכה ותקינה).
_UNIT_METRE = ("רטמ", "מטר", "'מ", "מ'")
_UNIT_KM = ('מ"ק', 'ק"מ')
_UNIT_NM = ("ימי ליימ", "מייל ימי", "NM")

# מספרים מאויתים במילים, כפי שמופיעים בהגדרות עיגול במסמך.
_SPELLED = {
    "יצח": 0.5, "חצי": 0.5,
    "דחא": 1, "אחד": 1,
    "םיינש": 2, "שניים": 2,
    "השולש": 3, "שלושה": 3,
}

_CIRCLE_MARKERS = ("לגעמ", "מעגל", "סוידר", "רדיוס")

_HEBREW_RE = re.compile(r"[֐-׿]")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


# ---------------------------------------------------------------------------
# עזרי טקסט
# ---------------------------------------------------------------------------


def reverse_hebrew(text: str) -> str:
    """מיישר טקסט שחולץ הפוך. שורות בלי עברית נשארות כמות שהן.

    תא שם יכול להשתרע על כמה שורות ('שטח אש' מעל '902'), ואת המספר
    אסור להפוך — 902 היה הופך ל-209.
    """
    parts = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        parts.append("".join(reversed(line)) if _HEBREW_RE.search(line) else line)
    return " ".join(parts).strip()


def parse_dms_pairs(text: str) -> list[tuple[float, float]]:
    """מחזיר [(lon, lat), ...] — סדר GeoJSON. הקואורדינטות תקינות בגולמי."""
    points: list[tuple[float, float]] = []
    for m in _DMS_PAIR_RE.finditer(text):
        lat = (
            int(m.group("lat_d"))
            + int(m.group("lat_m")) / 60.0
            + float(m.group("lat_s")) / 3600.0
        )
        lon = (
            int(m.group("lon_d"))
            + int(m.group("lon_m")) / 60.0
            + float(m.group("lon_s")) / 3600.0
        )
        if m.group("ns") == "S":
            lat = -lat
        if m.group("ew") == "W":
            lon = -lon
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            points.append((round(lon, 6), round(lat, 6)))
    return points


def is_circle_text(cell: str) -> bool:
    return any(marker in cell for marker in _CIRCLE_MARKERS)


def radius_metres(cell: str) -> float | None:
    """רדיוס במטרים מתוך הגדרת עיגול, או None כשאין מספר חד־משמעי."""
    if any(u in cell for u in _UNIT_NM):
        factor = 1852.0
    elif any(u in cell for u in _UNIT_KM):
        factor = 1000.0
    elif any(u in cell for u in _UNIT_METRE):
        factor = 1.0
    else:
        return None

    # מסירים קואורדינטות לפני חיפוש המספר, אחרת ספרות של מעלות ודקות
    # היו נקראות כרדיוס — טעות שקטה ומסוכנת.
    residual = _DMS_PAIR_RE.sub(" ", cell)
    numbers = _NUMBER_RE.findall(residual)
    if numbers:
        return float(numbers[0]) * factor
    for word, value in _SPELLED.items():
        if word in residual:
            return value * factor
    return None


# ---------------------------------------------------------------------------
# פרסור הטבלה
# ---------------------------------------------------------------------------


def _new_area(code: str) -> dict:
    return {
        "code": code,
        "name": None,
        "points": [],
        "altitudes": [],
        "radius_m": None,
        "circle_text": None,
    }


def parse_annex_rows(rows: list[list], source: str) -> tuple[list[dict], list[str]]:
    """מפרסר שורות טבלה לאזורים.

    אזור מתחיל בשורה שבה עמודת 'קוד זיהוי' מלאה, ונמשך עד המזהה הבא.
    זה כלל מבני ולא ניחוש, ולכן אין כאן היוריסטיקות סגירת טבעת.
    """
    areas: list[dict] = []
    current: dict | None = None

    for row in rows:
        cells = [(cell or "").strip() for cell in row]
        code = next(
            (c.replace(" ", "") for c in cells if _CODE_CELL_RE.match(c)), None
        )
        if code:
            current = _new_area(code)
            areas.append(current)
        if current is None:
            continue  # שורות כותרת שלפני האזור הראשון

        current["points"].extend(parse_dms_pairs(" ".join(c for c in cells if c)))

        for cell in cells:
            if not cell:
                continue
            # נספח ב' מגדיר עיגול במשפט ("מעגל שרדיוסו 6 ק"מ"); נספח ג'
            # נותן את הרדיוס בתא נפרד ("1000 מטר"), בלי המילה 'מעגל'.
            radius = radius_metres(cell)
            if radius is not None:
                current["radius_m"] = radius
                if is_circle_text(cell):
                    current["circle_text"] = cell
                continue
            if is_circle_text(cell):
                current["circle_text"] = cell
                continue
            if _ALT_CELL_RE.match(cell):
                current["altitudes"].append(cell)
            elif _HEBREW_RE.search(cell) and not current["name"]:
                current["name"] = reverse_hebrew(cell)

    features: list[dict] = []
    warnings: list[str] = []
    for area in areas:
        feature, warning = _build(area, source)
        if warning:
            warnings.append(warning)
        if feature:
            features.append(feature)
    return features, warnings


def _build(area: dict, source: str) -> tuple[dict | None, str | None]:
    """בונה גיאומטריה. מה שלא ברור מדווח ומדולג, לא מנוחש —
    אזור מגבלה שגוי מסוכן יותר מאזור חסר."""
    code = area["code"]
    points = area["points"]

    if area["radius_m"] and points:
        lon, lat = points[0]
        return _feature(area, circle_ring(lon, lat, area["radius_m"]), source), None

    if area["circle_text"] and not area["radius_m"]:
        return None, f"{code}: הגדרת עיגול בלי רדיוס מספרי — דולג. ({area['circle_text'][:90]})"

    if len(points) == 1:
        return None, f"{code}: נקודה בודדת בלי רדיוס — דולג."
    if len(points) < 3:
        return None, f"{code}: {len(points)} נקודות — דולג."

    ring = list(points)
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return _feature(area, [ring], source), None


def _feature(area: dict, coordinates: list, source: str) -> dict:
    code = area["code"]
    alts = area["altitudes"]
    return {
        "type": "Feature",
        "properties": {
            "id": code,
            "name": area["name"],
            "type": SERIES.get(code[:3], "לא מסווג"),
            "lower_limit": alts[0] if alts else None,
            "upper_limit": alts[1] if len(alts) > 1 else None,
            "radius_m": area["radius_m"],
            "source": source,
        },
        "geometry": {"type": "Polygon", "coordinates": coordinates},
    }


# ---------------------------------------------------------------------------
# גיאומטריה ותיבה
# ---------------------------------------------------------------------------


def circle_ring(lon: float, lat: float, radius_m: float, steps: int = 64) -> list:
    """מקרב עיגול לפוליגון. GeoJSON לא יודע עיגולים."""
    ring = []
    d = (radius_m / 1000.0) / 6371.0
    lat1, lon1 = math.radians(lat), math.radians(lon)
    for i in range(steps + 1):
        bearing = 2 * math.pi * i / steps
        lat2 = math.asin(
            math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(bearing)
        )
        lon2 = lon1 + math.atan2(
            math.sin(bearing) * math.sin(d) * math.cos(lat1),
            math.cos(d) - math.sin(lat1) * math.sin(lat2),
        )
        ring.append((round(math.degrees(lon2), 6), round(math.degrees(lat2), 6)))
    return [ring]


def feature_extent(feature: dict) -> tuple[float, float]:
    coords = feature["geometry"]["coordinates"]
    lons = [pt[0] for ring in coords for pt in ring]
    lats = [pt[1] for ring in coords for pt in ring]
    if not lons:
        return 0.0, 0.0
    return max(lons) - min(lons), max(lats) - min(lats)


def intersects_bbox(feature: dict) -> bool:
    """חפיפת מלבנים חוסמים לתיבת מטה בנימין.

    אזור שנוגע בתיבה נשמר בשלמותו ולא נחתך — קיצוץ גיאומטריה עלול
    להקטין אזור מגבלה, וזו טעות בכיוון המסוכן.
    """
    coords = feature["geometry"]["coordinates"]
    lons = [pt[0] for ring in coords for pt in ring]
    lats = [pt[1] for ring in coords for pt in ring]
    if not lons:
        return False
    return not (
        max(lons) < BBOX["min_lon"]
        or min(lons) > BBOX["max_lon"]
        or max(lats) < BBOX["min_lat"]
        or min(lats) > BBOX["max_lat"]
    )


# ---------------------------------------------------------------------------
# איתור הנספחים
# ---------------------------------------------------------------------------

# כותרת נספח בגולמי: "נספח ב'*" יוצא "*'ב חפסנ" — המילה 'נספח' ההפוכה
# **מסיימת** את השורה. חובה לעגן בסוף, אחרת כל אזכור של "בנספח ב'" בגוף
# הטקסט נתפס ככותרת.
_ANNEX_LETTERS = {"b": "ב", "c": "ג", "d": "ד", "e": "ה"}
_ANNEX_HEADERS = {
    key: re.compile(rf"\*?\s*'?{letter}\s+חפסנ\s*$")
    for key, letter in _ANNEX_LETTERS.items()
}


def find_annex_pages(pages: list[str]) -> dict[str, tuple[int, int]]:
    """מאתר את טווחי העמודים של הנספחים. מפתחות: b, c, d, e."""
    starts: dict[str, int] = {}
    for idx, text in enumerate(pages):
        found = {
            key
            for line in text.split("\n")
            for key, pattern in _ANNEX_HEADERS.items()
            if pattern.search(line.rstrip())
        }
        # עמוד שמכיל כותרות של כמה נספחים הוא תוכן העניינים, לא נספח.
        if len(found) != 1:
            continue
        starts.setdefault(found.pop(), idx)

    ordered = sorted(starts.items(), key=lambda kv: kv[1])
    ranges: dict[str, tuple[int, int]] = {}
    for pos, (key, start) in enumerate(ordered):
        end = ordered[pos + 1][1] if pos + 1 < len(ordered) else len(pages)
        ranges[key] = (start, end)
    return ranges
