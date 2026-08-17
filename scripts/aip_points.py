"""נקודות דיווח VFR ונקודות ייחוס של שדות תעופה, מהפמ"ת המלא.

מודול טהור: מקבל טקסט עמוד ומחזיר נקודות.

## מה זה

הטבלה "מפת נתיבי תובלה נמוכים" מרכזת את כל נקודות הדיווח בישראל —
198 נקודות — ובתוכן גם את **נקודות הייחוס של שדות התעופה עם קודי
ICAO**. שתי הבעיות שנתקענו בהן נפתרות מאותה טבלה:

* **מזג אוויר על המפה.** METAR ו-TAF מדווחים על תחנה, וחיפשנו את
  מיקומה בכל הפמ"ת הפנים־ארצי ולא מצאנו. כאן יש LLBG, LLHA, LLER,
  LLIB ו-LLHZ — בדיוק התחנות שבקובץ מזג האוויר.
* **נתיבי הטיסה.** הנוטאמים מפנים לנקודות בשמן —
  `EIRON-ARRAA-ZMGID-NIRYA-MRHVA-TAVOR` — ואלה הקודים בני חמש
  האותיות שבטבלה.

## הפרסור

השורה יוצאת מה-PDF כך:

    LLHZ 32° 10' 46" N 34° 50' 04" E ARP הילצרה OLGAH 32° 25' 53" N ...

כלומר **הקוד צמוד לקואורדינטות שלו**, וזה העוגן. הטבלה בנויה בארבע
עמודות ובעברית הפוכה, ואפשר היה לנסות לקרוא אותה לפי מיקום — אבל אין
צורך: `CODE lat lon` הוא רצף חד־משמעי שאינו תלוי בעמודות כלל.

**השמות העבריים לא נקראים כאן.** הגופן בעמוד מחזיר `(cid:17)` במקום
אותיות, והשם יוצא מקוטע. קוד בן חמש אותיות שלם עדיף על שם שבור, ובכל
מקרה הנוטאמים מפנים לקוד ולא לשם.
"""

from __future__ import annotations

import re

# `LLHZ 32° 10' 46" N 34° 50' 04" E` — הקוד ואחריו רוחב ואורך.
# בין ארבע לחמש אותיות: ICAO הוא ארבע, נקודת דיווח חמש.
_POINT_RE = re.compile(
    r"\b([A-Z]{4,5})\s+"
    r"(\d{1,2})°\s*(\d{1,2})'\s*(\d{1,2})\"\s*([NS])\s+"
    r"(\d{1,3})°\s*(\d{1,2})'\s*(\d{1,2})\"\s*([EW])"
)

# הסוג מופיע מיד אחרי אות הכיוון. "חובה" ו"דרישה" יוצאים הפוכים.
_KINDS = {
    "ARP": "שדה תעופה",
    "הבוח": "דיווח חובה",
    "השירד": "דיווח לפי דרישה",
}


def _dms(degrees: str, minutes: str, seconds: str, hemisphere: str) -> float:
    value = int(degrees) + int(minutes) / 60.0 + int(seconds) / 3600.0
    return -value if hemisphere in ("S", "W") else value


def parse_points(text: str) -> list[dict]:
    """מחזיר [{code, lat, lon, kind, icao}] לכל נקודה בטקסט.

    נקודה שיוצאת מחוץ לתיבה של ישראל נזרקת ומדווחת — קוד בן ארבע
    אותיות שנתפס בטעות באמצע מילה יכול לייצר נקודה באמצע הים.
    """
    points = []
    for match in _POINT_RE.finditer(text):
        code = match.group(1)
        lat = _dms(*match.group(2, 3, 4, 5))
        lon = _dms(*match.group(6, 7, 8, 9))
        if not (29.0 <= lat <= 33.5 and 34.0 <= lon <= 36.0):
            continue

        tail = text[match.end(): match.end() + 12].strip().split()
        kind = next((_KINDS[t] for t in tail[:1] if t in _KINDS), None)
        points.append({
            "code": code,
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "kind": kind,
            # קוד בן ארבע אותיות שמתחיל ב-LL הוא שדה תעופה.
            "icao": code if len(code) == 4 and code.startswith("LL") else None,
        })
    return points


def dedupe(points: list[dict]) -> list[dict]:
    """נקודה אחת לכל קוד. הטבלה חוזרת על עצמה בין עמודים."""
    seen: dict[str, dict] = {}
    for point in points:
        seen.setdefault(point["code"], point)
    return sorted(seen.values(), key=lambda p: p["code"])
