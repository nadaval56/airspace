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

**אין בדף שורות Q.** הן נמשכות פר־הודעה משירות נפרד
(`getMoreMsgInfo`). לכן רשומה מכאן מגיעה בלי גיאומטריה מובנית, ומה
שאפשר לחלץ מגיע מטקסט ה-E עצמו — בזהירות, ורק כשהניסוח חד־משמעי.

## קידוד

הכותרת מצהירה utf-8 אבל התג במסמך אומר windows-1255. הולכים אחרי התג.
"""

from __future__ import annotations

import html as _html
import re

BASE = "https://brin.iaa.gov.il/aeroinfo"
NOTAM_URL = f"{BASE}/AeroInfo.aspx?msgType=Notam"
WEATHER_URL = f"{BASE}/AeroInfo.aspx?msgType=Weather"

# שורת טבלה אחת. התאים מרווחים בכבדות ולכן \s* בכל מקום.
_ROW_RE = re.compile(
    r'<td[^>]*class="NotamID"[^>]*>\s*(?P<id>[^<]*?)\s*</td>.*?'
    r'<td[^>]*class="Location"[^>]*>\s*(?P<loc>[^<]*?)\s*</td>.*?'
    r'<td[^>]*class="MsgText"[^>]*>\s*(?P<text>.*?)\s*</td>',
    re.S | re.I,
)

_MSGNUM_RE = re.compile(r'id="DataList1_MoreImg_(\d+)"')
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
    """מחזיר [{id, location, text, msg_num}] לכל שורה בטבלה."""
    numbers = _MSGNUM_RE.findall(page)
    rows = []
    for index, m in enumerate(_ROW_RE.finditer(page)):
        identifier = _text(m.group("id"))
        text = _text(m.group("text"))
        if not identifier and not text:
            continue
        rows.append({
            "id": identifier or None,
            "location": _text(m.group("loc")) or None,
            "text": text or None,
            "msg_num": numbers[index] if index < len(numbers) else None,
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


def parse_notam_page(page: str) -> list[dict]:
    """שורות הנוטאמים מדף הרשימה."""
    return [row for row in parse_rows(page) if row.get("id")]


# ---------------------------------------------------------------------------
# מזג אוויר
# ---------------------------------------------------------------------------

_WX_KIND_RE = re.compile(r"\b(METAR|SPECI|TAF)\b", re.I)
# "VALID FROM 161800 TILL 171800" — DDHHMM
_VALID_RE = re.compile(r"VALID\s+FROM\s+(\d{6})\s+TILL\s+(\d{6})", re.I)


def parse_weather_page(page: str) -> list[dict]:
    """הודעות מזג אוויר. אותו מבנה טבלה, תוכן אחר."""
    reports = []
    for row in parse_rows(page):
        text = row.get("text") or ""
        kind = _WX_KIND_RE.search(text) or _WX_KIND_RE.search(row.get("id") or "")
        valid = _VALID_RE.search(text)
        reports.append({
            "id": row.get("id"),
            "station": row.get("location"),
            "kind": kind.group(1).upper() if kind else None,
            "text": text or None,
            "valid_from": valid.group(1) if valid else None,
            "valid_to": valid.group(2) if valid else None,
        })
    return [r for r in reports if r["text"]]
