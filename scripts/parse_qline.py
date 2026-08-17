"""פרסור נוטאמים גולמיים: שורת Q, פריטי A-G, זמנים, גבהים.

מודול טהור — בלי רשת, בלי תלויות חיצוניות. נבדק ב-scripts/test_parse.py.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# טבלאות פענוח קוד Q
# ---------------------------------------------------------------------------
# קוד Q בנוי: Q + שתי אותיות נושא + שתי אותיות מצב.
# הטבלאות חלקיות בכוונה — מכסות את מה שנפוץ במרחב LLLL. מה שלא מזוהה
# מוצג כקוד גולמי, לא נבלע.
#
# **כל תווית כאן אומתה מול הטקסט של הנוטאמים שנושאים את הקוד בפועל.**
# הגרסה הראשונה נכתבה מהזיכרון ונשאה שלוש טעויות אמיתיות:
#
#   AE — סומן "אזור בקרה מסוף (TMA)". בטבלת ICAO זהו CTA, ו-TMA הוא
#        AT. הטקסטים הכריעו: 19 ההודעות עם AE מדברות על בועות
#        מיקרולייט ואזורי אימון, ולא על מרחב מסוף של נמל תעופה.
#   WC — סומן "פעילות ימית / חילוץ". כל ארבע ההודעות פותחות במילים
#        "CAPTIVE BALLOON". זהו כדור פורח קשור.
#   CA — סומן "מרחב אווירי". ההודעות הן שינויי תדר של מגדל ופנייה
#        לבקרה, כלומר מתקן קשר אוויר-קרקע.
#
# קוד שהטקסט אינו מכריע לגביו נשאר בלי תווית בכוונה. תווית שגויה
# גרועה מקוד גולמי: הקורא סומך עליה ואינו קורא את הנוסח.

Q_SUBJECT = {
    "RA": "אזור שמור לפעילות",
    "RD": "אזור מסוכן",
    "RM": "אזור צבאי",
    "RO": "אזור מבצעי",
    "RP": "אזור אסור לטיסה",
    "RR": "אזור מוגבל",
    "RT": "אזור מוגבל זמנית",
    "WA": "פעילות אווירית",
    "WB": "אווירובטיקה",
    "WC": "כדור פורח קשור / עפיפון",
    "WD": "תרגיל צניחה",
    "WE": "תרגיל / אימון",
    "WF": "ירי תותחים",
    "WG": "ירי קרקע-אוויר",
    "WH": "ירי / חומרי נפץ",
    "WJ": "ירי טילים",
    "WL": "שיגור רקטות",
    "WM": "ירי טילים / רקטות",
    "WP": "צניחה חופשית",
    "WR": "פעילות רדיואקטיבית",
    "WS": "פעילות בליסטית",
    "WT": "פעילות דאונים / רחיפה",
    "WU": "כלי טיס בלתי מאויש (כטב\"ם)",
    "WV": "תעופת ראווה",
    "WW": "פעילות בגובה רב",
    "WZ": "מרחב שמור זמנית",
    "OB": "מכשול",
    "OL": "תאורת מכשול",
    "FA": "שדה תעופה",
    "FU": "דלק",
    "MR": "מסלול",
    "MT": "מנחת",
    "MX": "מסלול הסעה",
    "MP": "עמדת חניה למטוס",
    "NA": "עזרי ניווט",
    "NB": "משואת NDB",
    "NV": "משואת VOR",
    "ND": "משואת DME",
    "NI": "מערכת ILS",
    "NM": "משואת VOR/DME",
    "IS": "מערכת ILS",
    "LP": "מחוון זווית גישה (PAPI)",
    "CA": "מתקן קשר אוויר-קרקע",
    "GW": "שירותי GNSS — כלל אזוריים",
    "OA": "שירות מידע תעופתי (AIS)",
    "PD": "נוהל המראת מכשירים (SID)",
    "PO": "גובה עקיפת מכשולים (OCA/H)",
    # מרחב אווירי. ההבחנה בין השלושה אינה סמנטיקה: CTR מתחיל בקרקע
    # סביב שדה, CTA מתחיל בגובה מוגדר ומעלה, ו-TMA הוא מרחב המסוף
    # שמעל צומת שדות עמוס.
    "AA": "גובה מינימלי",
    "AC": "אזור בקרת שדה (CTR)",
    "AD": "אזור זיהוי הגנה אווירית (ADIZ)",
    "AE": "אזור בקרה (CTA)",
    "AF": "אזור מידע טיסה (FIR)",
    "AN": "נתיב ניווט שטח (RNAV)",
    "AR": "נתיב ATS",
    "AT": "אזור בקרה מסוף (TMA)",
    "KK": "רשימת בדיקה (CHECKLIST)",
}

# הסבר בשפה רגילה לקודים שהתווית שלהם היא מונח מקצועי או ראשי תיבות.
# התווית לבדה אומרת מה זה למי שכבר יודע; השורה הזאת אומרת את זה למי
# שלא. קוד שתוויתו מובנת מאליה — "מסלול", "דלק" — אינו מופיע כאן.
Q_SUBJECT_NOTE = {
    "AC": "מרחב מבוקר סביב שדה תעופה, מהקרקע ומעלה.",
    "AE": "מרחב מבוקר שמתחיל בגובה מוגדר ומעלה, לא מהקרקע.",
    "AT": "מרחב מבוקר מעל צומת שדות עמוס, שבו מתנקזות המראות ונחיתות.",
    "AD": "אזור שבו נדרש זיהוי כלי הטיס מטעמי ביטחון.",
    "AF": "האזור שבו ניתן שירות מידע טיסה. מרחב תל אביב כולו הוא LLLL.",
    "AN": "נתיב המוגדר בנקודות ציון ולא במשואות קרקע.",
    "AR": "נתיב תעופה מפורסם שבו זורמת תעבורה מבוקרת.",
    "AA": "הגובה הנמוך ביותר שמותר לטוס בו באזור.",
    "CA": "תדרי הרדיו שבהם מדברים עם הבקרה.",
    "GW": "שיבוש או תקלה בקליטת לוויין (GPS) בכל האזור, לא בנקודה אחת.",
    "IS": "מערכת נחיתה בהנחיית מכשירים — אלומות רדיו שמובילות למסלול.",
    "LP": "פנסים ליד המסלול שמראים לטייס אם הגישה גבוהה או נמוכה מדי.",
    "MP": "עמדת החניה של המטוס במנחת, לא המסלול עצמו.",
    "NM": "משואת ניווט שמוסרת גם כיוון וגם מרחק.",
    "NB": "משואת ניווט המשדרת בגלים בינוניים; כיוון בלבד.",
    "NV": "משואת ניווט המוסרת כיוון ביחס לצפון.",
    "ND": "משואה המוסרת מרחק בלבד.",
    "OA": "הודעה על שינוי בפמ\"ת עצמו. אינה מגבלה בשטח.",
    "PD": "מסלול ההמראה המפורסם של השדה.",
    "PO": "הגובה הנמוך ביותר שממנו מותר להמשיך בגישה בלי לראות את המסלול.",
    "RR": "אזור שהטיסה בו מותנית באישור מראש.",
    "WC": "בלון הקשור לקרקע בכבל. הכבל — לא הבלון — הוא המכשול.",
    "WP": "אזור שבו מתבצעות קפיצות צניחה.",
    "WU": "פעילות כלי טיס בלתי מאויש — רחפן או מזל\"ט.",
    "KK": "הודעה תקופתית שמונה את כל הנוטאמים בתוקף. אינה מגבלה בפני עצמה.",
}

Q_CONDITION = {
    "AC": "הופסק",
    "AD": "זמין לשימוש יומי",
    "AH": "פעיל בשעות שפורסמו",
    "AK": "חזר לפעילות רגילה",
    "AL": "פעיל בכפוף למגבלות",
    "AM": "פעיל בשעות צבאיות",
    "AN": "זמין לתעבורה לילית",
    "AO": "מבצעי",
    "AP": "פעיל — נדרשת בקשה מראש",
    "AR": "פעיל בשעות שפורסמו",
    "AS": "מושבת",
    "AU": "לא זמין",
    "AW": "הוסר לחלוטין",
    "AX": "פתוח מחדש",
    "CA": "מופעל",
    "CC": "הושלם",
    "CD": "מבוטל / מושבת",
    "CE": "הוקם",
    "CF": "פועל בתדר שונה",
    "CG": "פורק",
    "CH": "שונה",
    "CI": "מזוהה כעת כ-",
    "CL": "בוטל / חוסל",
    "CM": "הועבר למקום אחר",
    "CN": "מבוטל",
    "CO": "פועל",
    "CP": "פועל בהספק מופחת",
    "CR": "מוחלף ב-",
    "CS": "מותקן",
    "CT": "בבדיקה",
    "HV": "עבודות בעיצומן",
    "LC": "סגור",
    "LN": "סגור בשעות לילה",
    "LP": "אסור",
    "LR": "מוגבל",
    "LS": "לא בטוח לשימוש",
    "LT": "מוגבל ל-",
    "LV": "פעולה נורמלית חודשה",
    "LX": "פעיל",
    "TT": "שינוי זמני",
    "XX": "טקסט חופשי",
}

# היקף השפעה (שדה 5 בשורת Q)
Q_SCOPE = {
    "A": "שדה תעופה",
    "E": "נתיב טיסה",
    "W": "אזהרה למרחב",
    "K": "רשימת בדיקה",
}

# סימני נוטאם מנהלתי — לא מסננים אותם, רק מתייגים כדי שיירדו לתחתית הרשימה.
_ADMIN_MARKERS = ("CHECKLIST", "TRIGGER NOTAM", "TRIGGER-NOTAM")

# רדיוס 999 בשורת Q = כל ה-FIR. אין מצב שמציירים עיגול כזה.
FIR_WIDE_RADIUS_NM = 999

# רצפת גובה שמתחתיה נוטאם נחשב "נמוך" — רלוונטי לרחפנים.
LOW_ALTITUDE_FT = 3000

_COORD_RE = re.compile(r"^(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])(\d{3})$")
_HEADER_RE = re.compile(
    r"\b(?P<id>[A-Z]\d{1,4}/\d{2})\s+(?P<type>NOTAM[NRC])(?:\s+(?P<ref>[A-Z]\d{1,4}/\d{2}))?"
)
_ITEM_ORDER = ["Q", "A", "B", "C", "D", "E", "F", "G"]
_ITEM_RE = re.compile(r"(?:(?<=^)|(?<=[\s\)]))([QABCDEFG])\)")
_DATE_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})$")


class QLineError(ValueError):
    """שורת Q חסרה או פגומה. הרשומה נשמרת עם geo=None ולא נופלת."""


# ---------------------------------------------------------------------------
# קואורדינטות
# ---------------------------------------------------------------------------


def parse_coord_field(field: str) -> dict:
    """שדה 8 בשורת Q: DDMM[NS]DDDMM[EW]RRR.

    >>> parse_coord_field("3155N03518E010")["lat"]
    31.916666666666668
    """
    field = field.strip().upper()
    m = _COORD_RE.match(field)
    if not m:
        raise QLineError(f"שדה מיקום לא תקין: {field!r}")

    lat_d, lat_m, ns, lon_d, lon_m, ew, radius = m.groups()

    lat = int(lat_d) + int(lat_m) / 60.0
    lon = int(lon_d) + int(lon_m) / 60.0
    if int(lat_m) >= 60 or int(lon_m) >= 60:
        raise QLineError(f"דקות מחוץ לטווח: {field!r}")
    if ns == "S":
        lat = -lat
    if ew == "W":
        lon = -lon
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise QLineError(f"קואורדינטה מחוץ לטווח: {field!r}")

    radius_nm = int(radius)
    return {
        "lat": lat,
        "lon": lon,
        "radius_nm": radius_nm,
        # רדיוס 999 = כל המרחב. הדף לא יצייר עיגול, רק תג ברשימה.
        "fir_wide": radius_nm == FIR_WIDE_RADIUS_NM,
    }


# ---------------------------------------------------------------------------
# גבהים
# ---------------------------------------------------------------------------


def _fl_to_feet(value: str) -> int:
    """שדות 6/7 בשורת Q הם רמות טיסה — מאות רגל."""
    return int(value) * 100


def parse_altitudes(lower: str, upper: str) -> dict:
    """000/999 פירושו 'ללא הגבלת גובה', לא 0 עד 99,900 רגל."""
    lower = lower.strip()
    upper = upper.strip()
    if not (lower.isdigit() and upper.isdigit()):
        raise QLineError(f"גבהים לא תקינים: {lower!r}/{upper!r}")

    unlimited = lower == "000" and upper == "999"
    return {
        "lower_fl": int(lower),
        "upper_fl": int(upper),
        "lower_ft": _fl_to_feet(lower),
        "upper_ft": _fl_to_feet(upper),
        "unlimited": unlimited,
    }


def parse_limit_item(text: str | None) -> dict | None:
    """פריטי F)/G) — גבול תחתון/עליון בניסוח חופשי.

    מדויק יותר משורת Q כשהוא קיים. מחזיר None כשאין מה לפרסר.
    """
    if not text:
        return None
    raw = text.strip().upper()
    if not raw:
        return None

    result = {"raw": text.strip(), "feet": None, "reference": None}

    if re.match(r"^(?:SFC|GND|SURFACE|GROUND)", raw):
        result["feet"] = 0
        result["reference"] = "AGL"
        return result
    if raw.startswith("UNL"):
        result["feet"] = None
        result["reference"] = "UNLIMITED"
        return result

    m = re.match(r"^FL\s*(\d{2,3})", raw)
    if m:
        result["feet"] = int(m.group(1)) * 100
        result["reference"] = "FL"
        return result

    m = re.match(r"^(\d+(?:\.\d+)?)\s*(FT|M)\b", raw)
    if m:
        value = float(m.group(1))
        if m.group(2) == "M":
            value *= 3.28084
        result["feet"] = int(round(value))
        if "AGL" in raw or "GND" in raw or "SFC" in raw:
            result["reference"] = "AGL"
        elif "AMSL" in raw or "MSL" in raw:
            result["reference"] = "AMSL"
        return result

    return result


# ---------------------------------------------------------------------------
# שורת Q
# ---------------------------------------------------------------------------


def parse_q_line(q_line: str) -> dict:
    """מפרסר שורת Q שלמה לשמונת שדותיה.

    >>> q = parse_q_line("LLLL/QRTCA/IV/NBO/W/000/999/3155N03518E010")
    >>> q["subject_code"], q["geo"]["radius_nm"]
    ('RT', 10)
    """
    text = q_line.strip()
    if text.upper().startswith("Q)"):
        text = text[2:].strip()

    parts = [p.strip() for p in text.split("/")]
    if len(parts) < 8:
        raise QLineError(f"שורת Q חסרת שדות ({len(parts)}/8): {q_line!r}")
    # שדות עודפים מעבר ל-8 מתעלמים מהם — עדיף מלהפיל את הרשומה.
    fir, qcode, traffic, purpose, scope, lower, upper, coord = parts[:8]

    qcode = qcode.upper()
    if not re.match(r"^Q[A-Z]{4}$", qcode):
        raise QLineError(f"קוד Q לא תקין: {qcode!r}")
    subject, condition = qcode[1:3], qcode[3:5]

    return {
        "fir": fir.upper(),
        "q_code": qcode,
        "subject_code": subject,
        "subject": Q_SUBJECT.get(subject),
        "subject_note": Q_SUBJECT_NOTE.get(subject),
        "condition_code": condition,
        "condition": Q_CONDITION.get(condition),
        "traffic": traffic.upper(),
        "purpose": purpose.upper(),
        "scope_code": scope.upper(),
        "scope": Q_SCOPE.get(scope.upper()),
        "altitude": parse_altitudes(lower, upper),
        "geo": parse_coord_field(coord),
    }


# ---------------------------------------------------------------------------
# זמנים
# ---------------------------------------------------------------------------


def parse_notam_datetime(value: str | None) -> dict | None:
    """YYMMDDHHMM ב-UTC. מטפל ב-PERM, EST, WIE/IMMEDIATE.

    שומרים UTC בקובץ; ההמרה לזמן מקומי נעשית בדף.
    """
    if not value:
        return None
    raw = value.strip().upper()
    if not raw:
        return None

    result = {"raw": value.strip(), "iso": None, "permanent": False, "estimated": False}

    if raw.startswith("PERM"):
        result["permanent"] = True
        return result
    if raw.startswith(("WIE", "IMMEDIATE", "IMM")):
        return result

    if "EST" in raw:
        result["estimated"] = True
    digits = re.match(r"(\d{10})", raw)
    if not digits:
        return result

    m = _DATE_RE.match(digits.group(1))
    yy, mm, dd, hh, mi = (int(g) for g in m.groups())
    # נוטאמים לא חוזרים אחורה למאה הקודמת. חלון 2000-2099 מספיק בהחלט.
    try:
        dt = datetime(2000 + yy, mm, dd, hh, mi, tzinfo=timezone.utc)
    except ValueError:
        return result
    result["iso"] = dt.isoformat().replace("+00:00", "Z")
    return result


# ---------------------------------------------------------------------------
# פריטי A-G
# ---------------------------------------------------------------------------


def split_items(raw: str) -> dict:
    """חותך נוטאם גולמי לפריטים Q) A) B) C) D) E) F) G).

    סורק לפי הסדר הקנוני בלבד — כך ש-"B)" בתוך טקסט של E) לא שובר את החיתוך.
    """
    matches = [(m.group(1), m.start(), m.end()) for m in _ITEM_RE.finditer(raw)]

    chosen: list[tuple[str, int, int]] = []
    cursor = 0  # אינדקס בסדר הקנוני
    last_pos = -1
    for letter, start, end in matches:
        if letter not in _ITEM_ORDER[cursor:]:
            continue  # פריט מחוץ לסדר — כנראה חלק מטקסט חופשי
        if start < last_pos:
            continue
        cursor = _ITEM_ORDER.index(letter) + 1
        last_pos = start
        chosen.append((letter, start, end))

    items: dict[str, str] = {}
    for idx, (letter, _start, end) in enumerate(chosen):
        stop = chosen[idx + 1][1] if idx + 1 < len(chosen) else len(raw)
        items[letter] = raw[end:stop].strip()
    return items


def _is_administrative(raw: str, items: dict) -> bool:
    haystack = (items.get("E", "") + " " + raw[:200]).upper()
    return any(marker in haystack for marker in _ADMIN_MARKERS)


def parse_notam(raw: str, source: str | None = None) -> dict:
    """מפרסר נוטאם גולמי אחד. לעולם לא זורק — רשומה פגומה נשמרת עם geo=None."""
    raw = (raw or "").strip()
    items = split_items(raw)

    record: dict = {
        "id": None,
        "type": None,
        "replaces": None,
        "raw": raw,
        "source": source,
        "locations": [],
        "q": None,
        "geo": None,
        "altitude": None,
        "valid_from": None,
        "valid_to": None,
        "schedule": items.get("D") or None,
        "text": items.get("E") or None,
        "lower_limit": parse_limit_item(items.get("F")),
        "upper_limit": parse_limit_item(items.get("G")),
        "administrative": _is_administrative(raw, items),
        "parse_errors": [],
    }

    header = _HEADER_RE.search(raw)
    if header:
        record["id"] = header.group("id")
        record["type"] = header.group("type")
        record["replaces"] = header.group("ref")
    else:
        record["parse_errors"].append("כותרת הנוטאם לא זוהתה")

    # NOTAMR/NOTAMC לפעמים מופיעים בלי מזהה בכותרת אלא בגוף.
    if not record["replaces"]:
        ref = re.search(r"NOTAM[RC]\s+([A-Z]\d{1,4}/\d{2})", raw)
        if ref:
            record["replaces"] = ref.group(1)

    if items.get("A"):
        record["locations"] = re.findall(r"\b([A-Z]{4})\b", items["A"].upper())

    if items.get("Q"):
        try:
            q = parse_q_line(items["Q"])
            record["q"] = q
            record["altitude"] = q["altitude"]
            record["geo"] = q["geo"]
        except QLineError as exc:
            record["parse_errors"].append(str(exc))
    else:
        record["parse_errors"].append("שורת Q חסרה")

    record["valid_from"] = parse_notam_datetime(items.get("B"))
    record["valid_to"] = parse_notam_datetime(items.get("C"))

    # גבול מפורש בגוף ההודעה גובר על העיגול של שורת Q. העיגול הוא
    # מעטפת מעוגלת כלפי מעלה; רשימת הקודקודים היא האזור עצמו.
    record["area"] = extract_area(record["text"])

    record["floor_ft"] = _effective_floor(record)
    record["low_altitude"] = (
        record["floor_ft"] is not None and record["floor_ft"] < LOW_ALTITUDE_FT
    )
    return record


"""רצף נקודות בגוף הנוטאם, בשני הפורמטים שמופיעים בפועל.

    DDMMSS N DDDMMSS E   →   310714N0341759E
    DDMM   N DDDMM   E   →   3107N03417E

הצמדות, בלי רווח בין קו הרוחב לקו האורך. הצורה הזאת נבדלת משדה 8
של שורת Q, שם אחרי קו האורך מגיע רדיוס בן שלוש ספרות.
"""
_AREA_PT_RE = re.compile(
    r"\b(\d{2})(\d{2})(\d{2})([NS])(\d{3})(\d{2})(\d{2})([EW])\b"
    r"|\b(\d{2})(\d{2})([NS])(\d{3})(\d{2})([EW])\b"
)

# פחות משלוש נקודות אינו מצולע. שתי נקודות הן קו, ואחת היא נקודה —
# ובשני המקרים העיגול משורת Q נשאר הייצוג הנכון היחיד שיש.
MIN_AREA_POINTS = 3


def extract_area(text: str | None) -> list[list[float]] | None:
    """מחלץ מצולע מגוף הנוטאם, אם הוא מונה נקודות במפורש.

    חלק מהנוטאמים מוסרים את הגבול המדויק בתוך פריט E), למשל:

        AN AREA AT GAZA-STRIP BTN FLW PSN CLSD TO ALL FLT …
        310714N0341759E 310818N0343709E 310550N0344003E …

    זה **הנתון האמיתי**, בניגוד לעיגול של שורת Q שהוא רק מעטפת. כשהוא
    קיים אין שום סיבה לצייר במקומו עיגול.

    מחזיר רשימת [lon, lat] בסדר GeoJSON, או None אם אין מספיק נקודות.
    """
    if not text:
        return None

    points: list[list[float]] = []
    for match in _AREA_PT_RE.finditer(text):
        groups = match.groups()
        if groups[0] is not None:
            dd, mm, ss, ns, ddd, mm2, ss2, ew = groups[:8]
        else:
            dd, mm, ns, ddd, mm2, ew = groups[8:]
            ss = ss2 = "0"
        lat = int(dd) + int(mm) / 60 + int(ss) / 3600
        lon = int(ddd) + int(mm2) / 60 + int(ss2) / 3600
        if ns == "S":
            lat = -lat
        if ew == "W":
            lon = -lon
        points.append([round(lon, 6), round(lat, 6)])

    if len(points) < MIN_AREA_POINTS:
        return None
    # סוגרים את הטבעת. הנוטאם מונה קודקודים ואינו חוזר על הראשון.
    if points[0] != points[-1]:
        points.append(points[0])
    return points


def _effective_floor(record: dict) -> int | None:
    """רצפת הגובה בפועל — F) מדויק יותר משורת Q, אז הוא קודם."""
    lower = record.get("lower_limit")
    if lower and lower.get("feet") is not None:
        return lower["feet"]
    alt = record.get("altitude")
    if alt and not alt.get("unlimited"):
        return alt.get("lower_ft")
    if alt and alt.get("unlimited"):
        return 0  # ללא הגבלת גובה — מתחיל מהקרקע
    return None


# ---------------------------------------------------------------------------
# איחוד ורפלייסמנטים
# ---------------------------------------------------------------------------


def dedupe_and_resolve(records: list[dict]) -> list[dict]:
    """מסיר כפילויות ומטפל ב-NOTAMR/NOTAMC.

    נוטאם שהוחלף או בוטל לא מוצג פעמיים. הודעת הביטול עצמה נשמרת ומתויגת
    כמנהלתית — לא מסננים כלום, רק מסדרים.
    """
    by_id: dict[str, dict] = {}
    unidentified: list[dict] = []

    for rec in records:
        nid = rec.get("id")
        if not nid:
            unidentified.append(rec)
            continue
        existing = by_id.get(nid)
        if existing is None:
            by_id[nid] = rec
            continue
        # אותו מזהה משני מקורות: מעדיפים את הרשומה העשירה יותר.
        if _richness(rec) > _richness(existing):
            rec["source"] = _merge_sources(existing, rec)
            by_id[nid] = rec
        else:
            existing["source"] = _merge_sources(existing, rec)

    superseded: set[str] = set()
    for rec in by_id.values():
        ref = rec.get("replaces")
        if ref and rec.get("type") in ("NOTAMR", "NOTAMC") and ref in by_id:
            superseded.add(ref)

    for nid in superseded:
        by_id[nid]["superseded"] = True

    for rec in by_id.values():
        if rec.get("type") == "NOTAMC":
            rec["administrative"] = True
            rec["cancellation"] = True

    live = [r for r in by_id.values() if not r.get("superseded")]
    return live + unidentified


def _richness(rec: dict) -> int:
    score = 0
    if rec.get("q"):
        score += 4
    if rec.get("geo"):
        score += 2
    if rec.get("text"):
        score += 1
    if rec.get("valid_from", {}) and (rec.get("valid_from") or {}).get("iso"):
        score += 1
    score -= len(rec.get("parse_errors") or [])
    return score


def _merge_sources(a: dict, b: dict) -> str:
    sources = []
    for rec in (a, b):
        src = rec.get("source")
        if src:
            sources.extend(s for s in str(src).split("+") if s)
    seen: list[str] = []
    for s in sources:
        if s not in seen:
            seen.append(s)
    return "+".join(seen)


def sort_for_display(records: list[dict]) -> list[dict]:
    """ממוין לפי זמן תחילת תוקף, החדש למעלה. מנהלתיים יורדים לתחתית.

    שתי מיונים בזה אחר זה — המיון של פייתון יציב, אז המפתח השני שומר על
    הסדר הכרונולוגי בתוך כל קבוצה.
    """
    ordered = sorted(
        records,
        key=lambda r: ((r.get("valid_from") or {}).get("iso") or "", r.get("id") or ""),
        reverse=True,
    )
    return sorted(ordered, key=lambda r: 1 if r.get("administrative") else 0)
