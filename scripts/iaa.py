"""פרסור דפי רשות שדות התעופה — brin.iaa.gov.il/aeroinfo.

מודול טהור: מקבל HTML ומחזיר רשומות. בלי רשת, כדי שאפשר יהיה לבדוק
אותו על HTML שנשמר.

## המקור

זה המקור **הרשמי הישראלי**, והיחיד מבין כל מה שנבדק שמחזיר 200 בלי
אימות ובלי חסימה. הוא מגיש שני סוגי הודעות מאותו דף, לפי `msgType`:

    AeroInfo.aspx?msgType=Notam     רשימת נוטאמים
    AeroInfo.aspx?msgType=Weather   METAR ו-TAF

הוא גם מפרסם את **סדרה C** — הסדרה הפנים־ארצית — שאינה מופצת בהכרח
בערוץ הבינלאומי. זה בדיוק הפער שהבאנר באתר מזהיר מפניו.

## מה יש בדף ומה אין

כל שורה בטבלה נותנת מזהה, מיקום וטקסט ההודעה:

    <td class="NotamID">C1760/26</td>
    <td class="Location">LLLL</td>
    <td class="MsgText">E) AN AREA AT TLALIM WI 0.3NM RADIUS ...</td>

**הודעה ארוכה נשברת על פני כמה שורות טבלה**, ורק לראשונה יש מזהה. מי
שמסנן שורות בלי מזהה זורק את המשך ההודעה — ואיתו את הקואורדינטות,
שיושבות בדיוק אחרי המילה שבה השורה נגמרת:

    AN AREA AT TLALIM WI 0.3NM RADIUS CENTERED ON PSN     ← שורה 1
    3055N03446E IS CLSD                                    ← שורה 2

`merge_continuations` מאחד אותן. **אין בדף שורות Q** — הן נפתחות
בלחיצה על ה-`+` — ולכן הגיאומטריה מגיעה ממה שאפשר לחלץ מטקסט ההודעה,
בזהירות ורק כשהניסוח חד־משמעי.

## קידוד

הכותרת מצהירה utf-8 אבל התג במסמך אומר windows-1255. הולכים אחרי התג.
"""

from __future__ import annotations

import html as _html
import re

BASE = "https://brin.iaa.gov.il/aeroinfo"
NOTAM_URL = f"{BASE}/AeroInfo.aspx?msgType=Notam"
WEATHER_URL = f"{BASE}/AeroInfo.aspx?msgType=Weather"

# שורת טבלה שלמה. חותכים לפי <tr> ואז קוראים את התאים לפי שם המחלקה
# ולא לפי מיקום — שני הדפים משתמשים בשמות שונים לאותם שדות:
#
#   נוטאמים:    NotamID   Location          MsgText
#   מזג אוויר:  MsgType   weatherLocation   MsgText
#
# הניסיון הראשון קיבע את שמות הנוטאמים, ולכן דף מזג האוויר החזיר אפס
# שורות למרות שהיו בו 33.
_TR_RE = re.compile(r'<tr[^>]*class="tblBody"[^>]*>(.*?)</tr>', re.S | re.I)
_TD_RE = re.compile(r'<td[^>]*class="([^"]+)"[^>]*>(.*?)</td>', re.S | re.I)

_ID_CLASSES = ("NotamID", "MsgType")
_LOCATION_CLASSES = ("Location", "weatherLocation")

_MSGNUM_RE = re.compile(r'MoreImg_(\d+)')
_TAG_RE = re.compile(r"<[^>]+>")

# קואורדינטה בתוך טקסט ההודעה, בפורמט הנוטאמי הרגיל: 3155N03518E
_PSN_RE = re.compile(r"\b(\d{2})(\d{2})(\d{2})?([NS])\s*(\d{3})(\d{2})(\d{2})?([EW])\b")
# רדיוס בניסוח "WI 0.3NM RADIUS" / "RADIUS 5NM"
_RADIUS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*NM\b", re.I)


def decode(raw: bytes) -> str:
    """מפענח לפי התג במסמך ולא לפי כותרת ה-HTTP."""
    head = raw[:2000].decode("latin-1", errors="replace").lower()
    encoding = "cp1255" if "windows-1255" in head else "utf-8"
    return raw.decode(encoding, errors="replace")


def _text(fragment: str) -> str:
    """מנקה תגיות ורווחים מתא טבלה."""
    plain = _TAG_RE.sub(" ", fragment)
    return re.sub(r"\s+", " ", _html.unescape(plain)).strip()


def parse_rows(page: str) -> list[dict]:
    """מחזיר [{id, location, text, msg_num, expandable}] לכל שורה בטבלה."""
    rows = []
    for match in _TR_RE.finditer(page):
        block = match.group(1)
        cells = {name: _text(value) for name, value in _TD_RE.findall(block)}
        if not cells:
            continue

        identifier = next((cells[c] for c in _ID_CLASSES if cells.get(c)), None)
        location = next((cells[c] for c in _LOCATION_CLASSES if cells.get(c)), None)
        text = cells.get("MsgText") or None
        if not identifier and not text:
            continue

        number = _MSGNUM_RE.search(block)
        rows.append({
            "id": identifier,
            "location": location,
            "text": text,
            "msg_num": number.group(1) if number else None,
            # כפתור ההרחבה מוביל לפרטים נוספים באתר (שורת Q, זמני תוקף).
            # הטקסט עצמו שלם אחרי איחוד שורות ההמשך.
            "expandable": bool(number),
        })
    return rows


# ---------------------------------------------------------------------------
# נוטאמים
# ---------------------------------------------------------------------------


def extract_position(text: str) -> dict | None:
    """מחלץ מיקום מטקסט ההודעה, כשהניסוח חד־משמעי.

    הדף לא מגיש שורות Q, אז זה מה שיש. שמרני בכוונה: בלי קואורדינטה
    מפורשת אין גיאומטריה, והרשומה תופיע ברשימה בלי סמן על המפה.
    """
    m = _PSN_RE.search(text or "")
    if not m:
        return None
    lat_d, lat_m, lat_s, ns, lon_d, lon_m, lon_s, ew = m.groups()
    lat = int(lat_d) + int(lat_m) / 60.0 + (int(lat_s) / 3600.0 if lat_s else 0.0)
    lon = int(lon_d) + int(lon_m) / 60.0 + (int(lon_s) / 3600.0 if lon_s else 0.0)
    if ns == "S":
        lat = -lat
    if ew == "W":
        lon = -lon
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    radius = _RADIUS_RE.search(text or "")
    return {
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "radius_nm": float(radius.group(1)) if radius else 0.0,
        "fir_wide": False,
    }


def to_raw_notam(row: dict) -> str:
    """בונה גוש נוטאם גולמי כדי שהרשומה תזרום בצינור הפרסור הקיים."""
    parts = [f"{row['id']} NOTAMN"] if row.get("id") else []
    if row.get("location"):
        parts.append(f"A) {row['location']}")
    text = row.get("text") or ""
    # הטקסט מהאתר כבר פותח לרוב ב-'E)'. לא מכפילים.
    parts.append(text if text.upper().startswith("E)") else f"E) {text}")
    return "\n".join(parts)


def merge_continuations(rows: list[dict]) -> list[dict]:
    """מאחד שורות המשך אל ההודעה שלהן.

    הודעה ארוכה נשברת על פני כמה שורות טבלה, ורק לראשונה יש מזהה:

        TAF BEN GURION, VALID FROM 161800 TILL 171800, WIND 330 DEGREES, 7
        KNOTS, VISIBILITY 10 KILOMETERS OR MORE, CLOUD SCATTERED 2 THOUSAND 5

    הניסיון הראשון סינן שורות בלי מזהה, ובכך זרק את המשך ההודעה — ואיתו
    את הקואורדינטות, שיושבות בדיוק אחרי המילה שבה השורה נגמרת. זו הסיבה
    שאפס נוטאמים מופו, ולא קיטוע מצד המקור.
    """
    merged: list[dict] = []
    for row in rows:
        if row.get("id") or not merged:
            merged.append(dict(row))
            continue
        previous = merged[-1]
        extra = row.get("text")
        if extra:
            previous["text"] = f"{previous.get('text') or ''} {extra}".strip()
    return merged


def parse_notam_page(page: str) -> list[dict]:
    """שורות הנוטאמים מדף הרשימה, כולל שורות ההמשך."""
    return [row for row in merge_continuations(parse_rows(page)) if row.get("id")]


# ---------------------------------------------------------------------------
# מזג אוויר
# ---------------------------------------------------------------------------

_WX_KIND_RE = re.compile(r"\b(METAR|SPECI|TAF|AIRMET|SIGMET)\b", re.I)
# "VALID FROM 161800 TILL 171800" — DDHHMM
_VALID_RE = re.compile(r"VALID\s+FROM\s+(\d{6})\s+TILL\s+(\d{6})", re.I)

# AIRMET ו-SIGMET הם היחידים מבין הודעות מזג האוויר שנושאים **גיאומטריה
# מפורשת**. METAR ו-TAF מדווחים על תחנה — נקודה — ומיקום התחנה אינו
# מופיע בשום מקום בדף, ולכן הם לא מסומנים על המפה. אבל אזור ה-AIRMET
# רשום בטקסט עצמו כרשימת קודקודים:
#
#   LLLL AIRMET 4 VALID 161900/162300 LLBD- LLLL TEL AVIV FIR MT OBSC
#   FCST WI N3321 E03548 - N3257 E03555 - N3018 E03435 - N3042 E03426
#   - N3321 E03548 STNR INTSF=
#
# זה פוליגון סגור, מהמקור הרשמי, בלי שום ניחוש. הוא נעצר בסימן `=` או
# במילת מצב כמו STNR/MOV/NC — ולכן חותכים שם ולא ממשיכים לבלוע מספרים.
_WX_AREA_RE = re.compile(r"\bWI\b(.*?)(?:\b(?:STNR|MOV|NC|INTSF|WKN|NO\s+SIG)\b|=|$)", re.I | re.S)
_WX_POINT_RE = re.compile(r"\b([NS])(\d{2})(\d{2})(\d{2})?\s+([EW])(\d{3})(\d{2})(\d{2})?\b")


def _dms(degrees: str, minutes: str, seconds: str | None, hemisphere: str) -> float:
    value = int(degrees) + int(minutes) / 60.0 + (int(seconds) / 3600.0 if seconds else 0.0)
    return -value if hemisphere in ("S", "W") else value


def extract_area(text: str) -> list[list[float]] | None:
    """טבעת [lon, lat] מתוך סעיף ה-WI של AIRMET/SIGMET.

    מחזיר None אם אין מספיק קודקודים לשטח. פחות משלוש נקודות אינו
    פוליגון, ואזור מזג אוויר שגוי מטעה בדיוק כמו אזור מגבלה שגוי.
    """
    section = _WX_AREA_RE.search(text or "")
    if not section:
        return None
    ring = []
    for ns, lat_d, lat_m, lat_s, ew, lon_d, lon_m, lon_s in _WX_POINT_RE.findall(section.group(1)):
        ring.append([
            round(_dms(lon_d, lon_m, lon_s, ew), 6),
            round(_dms(lat_d, lat_m, lat_s, ns), 6),
        ])
    # המקור סוגר את הטבעת בעצמו; אם לא — סוגרים.
    if len(ring) >= 2 and ring[0] == ring[-1]:
        ring = ring[:-1]
    if len(ring) < 3:
        return None
    return ring + [ring[0]]


def parse_weather_page(page: str) -> list[dict]:
    """הודעות מזג אוויר. אותו מבנה טבלה, תוכן אחר.

    TAF בשפה פתוחה נשבר על פני כמה שורות, ולכן אותו איחוד כמו בנוטאמים.
    """
    reports = []
    for row in merge_continuations(parse_rows(page)):
        text = row.get("text") or ""
        kind = _WX_KIND_RE.search(text) or _WX_KIND_RE.search(row.get("id") or "")
        valid = _VALID_RE.search(text)
        reports.append({
            "id": row.get("id"),
            "station": row.get("location"),
            "kind": kind.group(1).upper() if kind else None,
            "text": text or None,
            "truncated": row.get("expandable", False),
            "valid_from": valid.group(1) if valid else None,
            "valid_to": valid.group(2) if valid else None,
            # רק ל-AIRMET/SIGMET. אצל השאר זה None, וכך גם צריך להיות.
            "area": extract_area(text),
        })
    return [r for r in reports if r["text"]]
