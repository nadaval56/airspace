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

# מספר ההודעה לכפתור ההרחבה. ה-onclick של התמונה הוא:
#
#     f_getMoreInfo(this.parentNode…(x5).id.substr(12), 'more')
#
# והאב החמישי הוא `<div id="divMainInfo_2046996">`. ל-"divMainInfo_"
# יש בדיוק 12 תווים, כלומר msgNum = 2046996 — **מזהה הודעה אמיתי**.
#
# הניסיון הראשון קרא `MoreImg_(\d+)` והחזיר 0,1,2… — האינדקס של השורה
# ב-DataList, שאין לו שום קשר. עם המספר הזה ה-postback חזר עם הדף
# ההתחלתי בדיוק, בלי שום הרחבה, וזה נראה כאילו המנגנון לא עובד.
_MAININFO_RE = re.compile(r'id="(?:div|tbl)MainInfo_(\d+)"')
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
    """מחזיר [{id, location, text, msg_num, expandable}] לכל שורה בטבלה.

    `msg_num` נלקח מ-`divMainInfo_<n>` **העוטף** את השורה, ולכן הוא
    נמצא לפי מיקום בטקסט ולא בתוך ה-`<tr>` עצמו.
    """
    anchors = [(m.start(), m.group(1)) for m in _MAININFO_RE.finditer(page)]

    def msg_num_before(position: int) -> str | None:
        found = None
        for start, number in anchors:
            if start > position:
                break
            found = number
        return found

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

        number = msg_num_before(match.start())
        rows.append({
            "id": identifier,
            "location": location,
            "text": text,
            "msg_num": number,
            # כפתור ההרחבה מוביל לפרטים נוספים באתר (זמני תוקף, שדה
            # תעופה). הטקסט עצמו שלם אחרי איחוד שורות ההמשך.
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
# ההרחבה — הכפתור `+`
# ---------------------------------------------------------------------------
#
# דף הרשימה לא נותן זמני תוקף. הם נפתחים בלחיצה על ה-`+`, ולזה יש
# מנגנון מדויק ב-`MoreInfo.js`:
#
#     document.getElementById('hidMsgNum').value = msgNum;
#     document.getElementById('hidMode').value = mode;
#     document.getElementById('hidCurOrHist').value = CurrOrHist;
#     document.getElementById('hidTblClientId').value = "";
#     document.getElementById('btnMoreInfo').click();
#
# כלומר **postback רגיל של WebForms**, לא שירות אינטרנט. באותו קובץ יש
# גם נתיב ישן שקורא ל-`AeroInfo.asmx?op=getMoreMsgInfo` — אבל כל שורה
# בו מסומנת כהערה, וה-`?WSDL` שלו חסום מאחורי Radware. הנתיב הזנוח לא
# מעניין אותנו; משחזרים את מה שהדפדפן באמת עושה.
#
# `msgNum` הוא **אינדקס השורה בדף** (0..n), לא מזהה נוטאם. הוא משתנה
# בין טעינות, ולכן חייבים להשתמש באינדקס מאותו דף שממנו נלקח ה-VIEWSTATE.

_INPUT_RE = re.compile(r"<input\b([^>]*)>", re.I)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"', re.I)

_MORE_FIELDS = ("hidMsgNum", "hidMode", "hidCurOrHist", "hidTblClientId")


def form_fields(page: str) -> dict[str, str]:
    """כל שדות ה-input של הטופס, לשחזור ה-postback.

    כולל `__VIEWSTATE` ו-`__EVENTVALIDATION` — בלעדיהם WebForms דוחה
    את הבקשה. שדות בלי name נזרקים, ו-checkbox שאינו מסומן לא נשלח,
    בדיוק כמו בדפדפן.
    """
    fields: dict[str, str] = {}
    for raw in _INPUT_RE.findall(page):
        attrs = {k.lower(): v for k, v in _ATTR_RE.findall(raw)}
        name = attrs.get("name")
        if not name:
            continue
        if attrs.get("type", "").lower() in ("checkbox", "radio") and "checked" not in raw.lower():
            continue
        fields[name] = _html.unescape(attrs.get("value", ""))
    return fields


def more_info_payload(page: str, msg_num: str) -> dict[str, str]:
    """שדות ה-POST שפותחים את השורה מספר `msg_num`."""
    fields = form_fields(page)
    fields.update({
        "hidMsgNum": str(msg_num), "hidMode": "more",
        "hidCurOrHist": "Current", "hidTblClientId": "",
    })
    return fields


# השורות שנפתחות מסומנות במחלקות משלהן. `more_NotamInfo` נושא תוויות
# בשפה חופשית ("Valid From : 16/08/2026 19:00"), ומהן שולפים את הזמנים.
_MORE_CELL_RE = re.compile(
    r'<td[^>]*class="(more_NotamID|more_NotamInfo|more_MsgText)"[^>]*>(.*?)</td>',
    re.S | re.I,
)
_MORE_LABEL_RE = re.compile(
    r"(Valid From|Valid To|Created|Location Indicator|Location Description|Notam NO|Weather Type)"
    r"\s*:?\s*(.*)", re.I,
)
# "16/08/2026 19:00" — יום/חודש/שנה ושעה, כפי שהשרת מרכיב אותם.
_MORE_STAMP_RE = re.compile(r"(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2})")


def _iso_from_more(value: str) -> str | None:
    m = _MORE_STAMP_RE.search(value or "")
    if not m:
        return None
    day, month, year, hour, minute = m.groups()
    return f"{year}-{month}-{day}T{hour}:{minute}:00Z"


def parse_more_info(page: str) -> dict:
    """קורא את הבלוק שנפתח: זמני תוקף, שדה תעופה, וטקסט מלא.

    מחזיר מילון עם מה שנמצא בלבד. שדה חסר אינו שגיאה — הוא פשוט לא
    מופיע, וכך גם צריך להיות: עדיף בלי זמן תוקף מאשר עם זמן מנוחש.
    """
    found: dict[str, str] = {}
    texts: list[str] = []
    for kind, raw in _MORE_CELL_RE.findall(page):
        value = _text(raw)
        if kind == "more_MsgText":
            if value:
                texts.append(value)
            continue
        label = _MORE_LABEL_RE.match(value)
        if not label:
            continue
        key, rest = label.group(1).lower(), label.group(2).strip()
        if key == "valid from":
            found["valid_from"] = _iso_from_more(rest) or rest
        elif key == "valid to":
            found["valid_to"] = _iso_from_more(rest) or rest
        elif key == "created":
            found["created"] = _iso_from_more(rest) or rest
        elif key == "location description":
            found["airfield"] = rest
        elif key in ("notam no", "weather type"):
            found["id"] = rest
    if texts:
        found["text"] = " ".join(texts)
    return found


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
