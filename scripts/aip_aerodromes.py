"""שדות תעופה, מנחתים ומשטחי מסוקים — מפרקי ד', ה' ו-ו' של הפמ"ת.

מודול טהור: מקבל שורות עמוד **מיושרות** (ראו `aip_annexes.reverse_hebrew`)
ומחזיר רשומות. בלי רשת ובלי PDF.

## למה זו שכבה ולא עוד קטגוריה

עד עכשיו הדף ידע על שדות תעופה שני דברים בלבד: 24 נקודות ייחוס עם קוד
ICAO, שנשאבו מטבלת נתיבי התובלה כדי שיהיה איפה לסמן METAR ו-TAF. אין
בהן שם, אין סוג, ואין גובה — וגם לא היה להן ייצוג משלהן על המפה.

אבל הפמ"ת מקדיש לכל שדה **פרק שלם**, וההגדרה שם מסודרת:

    שדה התעופה ראש פינה )LLIB(
    .1 נקודת ציון מרכזית
    ברשת :WGS-84 035°34'19"E 32°58'51"N
    .3 גובה השדה
    884 רגל מעל פני הים.

## הסוג — נתון מהמקור, לא ניחוש

הפמ"ת מחלק את המנחתים לשלושה פרקים, וכל פרק נפתח בדף תוכן שמונה את
מה שבתוכו:

    פרק ד' – שדות תעופה            הרצליה · חיפה · ראש פינה
    פרק ה' – מנחתים                באר שבע · הבונים · מגידו · ...
    פרק ו' – משטחי נחיתה למסוקים    איכילוב · בלינסון · סורוקה · ...

**הסוג נגזר מהפרק שבו השדה יושב.** זו קריאה של מבנה המסמך, ולא ניתוח
של השם — "פוריה" אינו נראה כמו משטח מסוקים ואינו צריך להיראות: הוא
בפרק ו'.

בתוך פרק ה' יש רשימה נוספת, "מנחתים נוספים", שהיא **טבלה** של מנחתים
חקלאיים — שם, מפעיל, דואר ליצירת קשר ונ"צ. היא מקבלת סוג משלה: מנחת
חקלאי אינו מנחת מוסדר עם מסלול ותדר.

## מה שלא נגזר: גבולות

אזור השדה (ATZ) מתואר בפרקים **במילים** — "בצפון שדרות משה דיין,
במערב גבול שטח אש 24, בדרום נחל שורק". אין שם קואורדינטות, ולכן אין
כאן פוליגונים: מה שהמקור נותן הוא נקודה אחת (ARP), וזה מה שמצויר.
מי שממציא גבול מתיאור מילולי מצייר אזור תיאום שגוי, וזו טעות בכיוון
המסוכן. רדיוס שכן כתוב במפורש בפרק נשמר כנתון (`atz_radius_nm`).
"""

from __future__ import annotations

import math
import re

from aip_annexes import unmirror_brackets

# כותרות הפרקים בדף התוכן שלהם. המקף הוא en-dash במקור.
VOLUMES: list[tuple[str, str, str]] = [
    ("airport", "שדות תעופה", "שדות תעופה"),
    ("airstrip", "מנחתים", "מנחתים"),
    ("helipad", "משטחי מסוקים", "משטחי נחיתה למסוקים"),
]

_VOLUME_HEAD_RE = {
    key: re.compile(rf"^פרק\s+[א-ת]'\s*[-–]\s*{re.escape(heading)}\s*$")
    for key, _, heading in VOLUMES
}

VOLUME_LABELS = {key: label for key, label, _ in VOLUMES}
VOLUME_LABELS["agricultural"] = "מנחתים חקלאיים"
VOLUME_LABELS["reference"] = "שדות נוספים (נ\"צ בלבד)"

# הכותרת הרצה של עמוד בפרק שדה: 'פמ"ת פנים ארצי ראש פינה - 3' או
# 'ראש פינה - 3 פמ"ת פנים ארצי'. המספר הוא מספר העמוד **בתוך הפרק**,
# ולכן שמו של הפרק הוא מה שמקבץ עמודים לשדה אחד.
_MASTHEAD = 'פמ"ת פנים ארצי'
# ההיפוך הדו־כיווני מזיז את המקף ואת המספר זה סביב זה, ולכן אותה
# כותרת מופיעה בארבע צורות: 'מגידו - 3', 'עין שמר 2-', 'פוריה- 1',
# ולפעמים המספר נשבר לשורה נפרדת ונשאר רק 'עין שמר -'.
_RUNNING_HEAD_RES = (
    re.compile(rf"^{re.escape(_MASTHEAD)}\s+(?P<name>.+?)\s*-\s*\d{{1,3}}\s*$"),
    re.compile(rf"^{re.escape(_MASTHEAD)}\s+(?P<name>.+?)\s*\d{{1,3}}\s*-\s*$"),
    re.compile(rf"^{re.escape(_MASTHEAD)}\s+(?P<name>.+?)\s*-\s*$"),
    re.compile(rf"^(?P<name>.+?)\s*-\s*\d{{1,3}}\s+{re.escape(_MASTHEAD)}\s*$"),
    re.compile(rf"^(?P<name>.+?)\s*\d{{1,3}}\s*-\s+{re.escape(_MASTHEAD)}\s*$"),
)

# שורת הכותרת של השדה עצמו, בעמוד הראשון של הפרק.
_TITLE_RE = re.compile(
    r"^(?:שדה התעופה|נמל התעופה|מנחת מסוקים|משטח נחיתה|מנחת)\b"
)

# קוד ICAO. ההיפוך הדו־כיווני מזיז את הסוגריים ואף הופך אותם
# (')LLAA)'), ולכן הקוד עצמו הוא העוגן ולא מה שעוטף אותו.
_ICAO_RE = re.compile(r"\b(LL[A-Z]{2})\b")

# שורת הנ"צ, וההפתעה הגדולה של הפרקים האלה.
#
# 14 מ-24 הפרקים אינם כותבים את סימן המעלות ב-"°" אלא בתו מהאזור הפרטי
# של יוניקוד — U+F0B0, מיפוי של גופן Symbol; השניות שם הן U+F0B2.
# במסוף שני התווים נראים כמו **כלום**, וכך נראית שורת חיפה:
#
#     מה שהעין רואה:   03502'38E 3248'35N
#     מה שכתוב באמת:   035<F0B0>02'38<F0B2>E 32<F0B0>48'35<F0B2>N
#
# מי שמפרסר את מה שהעין רואה בונה דפוס למספר דבוק ("03502"), ואז הוא
# צריך לנחש איפה נגמרות המעלות ומתחילות הדקות — ניחוש על הנתון היחיד
# שאסור לטעות בו. אחרי המיפוי כל 24 הפרקים כתובים באותה צורה אחת.
#
# שאר ההבדלים קוסמטיים ומכוסים בסימני הבחירה שלמטה: ˚ במקום °, שני
# גרשים במקום גרשיים, מרכאות מסולסלות, ושניות עשרוניות (ראשון לציון).
_PUA_MAP = {"": "°", "": '"'}
_PUA_RE = re.compile("[" + "".join(_PUA_MAP) + "]")

# אות הכיוון יכולה לשבת אחרי המספר (הרוב) או לפניו (קציעות:
# 'E034˚26\'36\'\' N30˚51\'33\'\''), ולכן שני דפוסים. הצמד הראשון
# שנופל בתוך תיבת ישראל מנצח.
_SEC_MARK = r"(?:''|\"|”|’’|״|׳׳)?"
_DEG_BODY = (
    r"(?P<deg>\d{1,3})\s*[°˚]\s*(?P<min>\d{1,2})\s*['’]\s*"
    rf"(?P<sec>\d{{1,2}}(?:\.\d+)?)\s*{_SEC_MARK}"
)

_DMS_PATTERNS = (
    re.compile(rf"{_DEG_BODY}\s*(?P<hemi>[NSEW])"),
    re.compile(rf"(?P<hemi>[NSEW])\s*{_DEG_BODY}"),
)

# שם הרשת עצמו. 'WGS' נשלף מהשורה לפני הפרסור, אחרת ה-S שלו נקרא
# כ-South ומזיז את השדה לחצי הכדור השני.
#
# **רק שלוש האותיות.** נוסח כמו 'ברשת 1984 :WGS 034°43\'22"E' מפתה
# לשלוף גם את השנה, אבל ביטוי שמרשה ספרות אחרי WGS בולע את '03' של
# האורך שאחריו — ואז 034° נקרא 4°, והשדה נוחת במפרץ סואץ. הספרות
# שנשארות אינן מזיקות: אין אחריהן גרש, ולכן שום דפוס DMS אינו נתפס בהן.
_GRID_NAME_RE = re.compile(r"WGS")

# נ"צ בטבלת המנחתים החקלאיים: '323208/0352618' — DDMMSS/DDDMMSS.
_COMPACT_RE = re.compile(r"\b(?P<lat>\d{6})\s*/\s*(?P<lon>0?\d{6})\b")

_ELEV_HEADS = ("גובה השדה", "גובה המנחת", "גובה המשטח", "גובה משטח")

# הגובה בשורת המלל, וכאן צריך זהירות. ההיפוך הדו־כיווני מפרק מספר עם
# מפריד אלפים לשני רצפים ומחליף ביניהם:
#
#     מצדה   '233 1 )-( רגל'    כלומר 1,233 — או 233,1? הסדר אבד.
#     תפן    '183 2 רגל.'
#
# רצף אחד נקרא; **שניים — לא**. לנחש איזה מהם האלפים זה לנחש על גובה
# של מנחת, ומספר חסר עדיף על מספר הפוך. מפריד בתוך אסימון אחד ("2,088")
# תקין, כי שם לא אבד שום סדר.
_ELEV_TOKEN_RE = re.compile(r"\d+(?:,\d{3})*")
_ELEV_TAIL_RE = re.compile(r"(?P<head>[^:]{0,24})רגל")
_BELOW_SEA = ("מתחת לפני הים", "(-)", ")-(")

# הגובה בעמודי התרשימים — 'ELEV 884 ft', ובהיפוך 'ft 884 ELEV'. לטינית
# וספרות אינן עוברות שום טרנספורמציה, ולכן זה המקור **המהימן** לגובה,
# והוא זה שמכריע. ראו chart_elevation.
_CHART_ELEV_RE = re.compile(
    r"(?:ft\s*(?P<a>\(?-?\)?-?[\d,]+)\s*ELEV|ELEV\s*(?P<b>\(?-?\)?-?[\d,]+)\s*ft)"
)

# רדיוס אזור השדה. הניסוח הקנוני בפרקים: "אזור השדה של המנחת **מתוחם**
# ברדיוס 3 ק"מ מנקודת הציון המרכזית )ARP(". דרישת המילה "מתוחם" באותה
# שורה היא מה שמפריד את ההגדרה מאזכורי רדיוס אחרים — ריבוי מכשולים
# ברדיוס 1.5 מייל, פעילות מורשית ברדיוס 5 ק"מ, חצי מעגל ברדיוס 3 ק"מ.
_ATZ_RADIUS_RE = re.compile(
    r"מתוחם\s*ברדיוס(?:\s+של)?\s+(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>נ\"מ|מייל ימי|מייל|ק\"מ|מטר)"
)

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")

# תיבת ישראל. נקודה שיוצאת ממנה היא שגיאת פרסור ולא שדה תעופה.
BBOX = {"min_lat": 29.0, "max_lat": 33.5, "min_lon": 34.0, "max_lon": 36.0}

# כמה רחוקים יכולים להיות שני משטחי נחיתה **של אותו מתקן**.
#
# פרק אחד מתאר מתקן אחד: "בבית החולים הדסה עין כרם שני משטחי נחיתה,
# קרקעי ומוגבה על גג בניין". קמפוס של בית חולים אינו נמתח על קילומטר,
# וגם ראשון לציון — מסלול מטוסים ומשטח מסוקים — מרוחקים 135 מטר.
#
# בהדסה המקור נותן למשטח המוגבה 31°45'08"N, שהם 1,371 מטר **דרומה**
# מהמשטח הקרקעי, בשטח היישוב אורה. המשטח המוגבה יושב על גג בניין
# באותו בית חולים, ולכן אחד משני המספרים שגוי — ואי אפשר לדעת איזה.
# נקודה על גג במרחק קילומטר וחצי ממנו אינה "בערך נכונה" אלא פשוט
# מפנה טייס למקום אחר, ולכן היא אינה מצוירת והחוסר נאמר בקול.
SAME_SITE_LIMIT_M = 1000


def distance_m(first: tuple[float, float], second: tuple[float, float]) -> float:
    """מרחק בין שתי נקודות במטרים (הברסין)."""
    lat1, lon1 = first
    lat2, lon2 = second
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


def in_israel(lat: float, lon: float) -> bool:
    return (
        BBOX["min_lat"] <= lat <= BBOX["max_lat"]
        and BBOX["min_lon"] <= lon <= BBOX["max_lon"]
    )


def running_head(line: str) -> str | None:
    """שם הפרק מתוך הכותרת הרצה, או None אם השורה אינה כותרת."""
    text = line.strip()
    if _MASTHEAD not in text:
        return None
    for pattern in _RUNNING_HEAD_RES:
        match = pattern.match(text)
        if match:
            name = match.group("name").strip(" -–")
            # 'פרק ד' – שדות תעופה' אינו שם של שדה.
            if name and not name.startswith("פרק"):
                return name
    return None


def volume_of(line: str) -> str | None:
    """מפתח הפרק אם השורה היא כותרת פרק, אחרת None."""
    text = line.strip()
    for key, pattern in _VOLUME_HEAD_RE.items():
        if pattern.match(text):
            return key
    return None


def _pair(text: str, pattern: re.Pattern) -> tuple[float, float] | None:
    """(lat, lon) לפי דפוס אחד, או None כשאין בו רוחב **ואורך**."""
    lat = lon = None
    for match in pattern.finditer(text):
        degrees, minutes = int(match.group("deg")), int(match.group("min"))
        seconds = float(match.group("sec"))
        if minutes > 59 or seconds >= 60:
            continue
        value = degrees + minutes / 60.0 + seconds / 3600.0
        hemi = match.group("hemi")
        if hemi in "NS" and lat is None:
            lat = -value if hemi == "S" else value
        elif hemi in "EW" and lon is None:
            lon = -value if hemi == "W" else value
    if lat is None or lon is None:
        return None
    return round(lat, 5), round(lon, 5)


def parse_dms_pair(text: str) -> tuple[float, float] | None:
    """(lat, lon) מתוך שורת נ"צ של פרק שדה.

    הרוחב והאורך מזוהים לפי **אות הכיוון** ולא לפי הסדר שבו הם
    כתובים: בפרקים המזרח מופיע לפני הצפון ('...E ...N'), הפוך
    מהנספחים, ולקרוא לפי מקום היה מחליף רוחב באורך — טעות שמעיפה שדה
    תעופה לאמצע סעודיה.

    שני הדפוסים נבדקים בסדר, ומי שנופל בתוך תיבת ישראל מנצח. צמד
    שנקרא במצוקה מוחזר גם כשהוא מחוץ לתיבה, כדי שהקורא ידווח עליו
    במקום להחזיר "לא נמצא" מטעה.
    """
    clean = _GRID_NAME_RE.sub(" ", _PUA_RE.sub(lambda m: _PUA_MAP[m.group(0)], text))
    fallback = None
    for pattern in _DMS_PATTERNS:
        found = _pair(clean, pattern)
        if not found:
            continue
        if in_israel(*found):
            return found
        fallback = fallback or found
    return fallback


def parse_compact_pair(text: str) -> tuple[float, float] | None:
    """(lat, lon) מצורת DDMMSS/DDDMMSS של טבלת המנחתים החקלאיים."""
    match = _COMPACT_RE.search(text)
    if not match:
        return None

    def unpack(digits: str) -> float:
        digits = digits[-6:]
        return int(digits[:2]) + int(digits[2:4]) / 60.0 + int(digits[4:6]) / 3600.0

    lat = unpack(match.group("lat"))
    raw_lon = match.group("lon")
    # אורך תלת־ספרתי: '0352618' → 035°26'18"
    lon = (
        int(raw_lon[:-4]) + int(raw_lon[-4:-2]) / 60.0 + int(raw_lon[-2:]) / 3600.0
        if len(raw_lon) == 7
        else unpack(raw_lon)
    )
    return round(lat, 5), round(lon, 5)


def _feet(text: str) -> tuple[int | None, bool]:
    """(גובה, האם הנתון דו־משמעי) מתוך קטע טקסט שמסתיים ב"רגל".

    דו־משמעי = שני רצפי ספרות לפני "רגל", כלומר מספר שההיפוך פירק
    למפריד אלפים והחליף את סדר החלקים. במקרה כזה מוחזר None ודגל, כדי
    שהקורא ידווח ולא ינחש.
    """
    match = _ELEV_TAIL_RE.search(text)
    if not match:
        return None, False
    head = match.group("head")
    tokens = _ELEV_TOKEN_RE.findall(head)
    if not tokens:
        return None, False
    if len(tokens) > 1:
        return None, True
    feet = int(tokens[0].replace(",", ""))
    if any(mark in text for mark in _BELOW_SEA):
        feet = -feet
    return feet, False


def text_elevation(lines: list[str], label: str | None = None) -> tuple[int | None, bool]:
    """הגובה כפי שכתוב במלל הפרק, ודגל דו־משמעות.

    כשלפרק יש כמה משטחים, הגבהים מפורטים תחת אותה כותרת ומסומנים בשם
    המשטח ("א. מנחת קרקעי: 2,088 רגל"), ולכן `label` מכריע איזה מהם.
    """
    ambiguous = False
    for index, line in enumerate(lines):
        if not any(head in line for head in _ELEV_HEADS):
            continue
        window = lines[index: index + 6]
        if label:
            for candidate in window:
                if not _shares_words(candidate, label):
                    continue
                feet, flag = _feet(candidate)
                ambiguous = ambiguous or flag
                if feet is not None:
                    return feet, False
            continue
        for candidate in window[:3]:
            feet, flag = _feet(candidate)
            ambiguous = ambiguous or flag
            if feet is not None:
                return feet, False
    return None, ambiguous


def chart_elevation(lines: list[str]) -> int | None:
    """הגובה מעמוד התרשים — 'ELEV 884 ft'.

    זה המקור המכריע. הספרות שם לטיניות ואופקיות, ולכן אינן עוברות את
    ההיפוך שמשבש את שורות המלל: קציעות כתוב במלל "כ- 099 רגל" ובתרשים
    "ELEV 900 ft", ורק אחד מהשניים יכול להיות גובה של מנחת בנגב.
    """
    for line in lines:
        match = _CHART_ELEV_RE.search(line)
        if not match:
            continue
        raw = match.group("a") or match.group("b")
        digits = _ELEV_TOKEN_RE.findall(raw)
        if len(digits) != 1:
            continue
        feet = int(digits[0].replace(",", ""))
        if "(" in raw or "-" in raw:
            feet = -feet
        return feet
    return None


def _shares_words(text: str, label: str) -> bool:
    """האם השורה נושאת את שם המשטח. שתי מילים ראשונות מספיקות."""
    words = [w for w in re.split(r"\s+", label) if len(w) > 1][:2]
    return bool(words) and all(word in text for word in words)


def atz_radius_nm(lines: list[str]) -> tuple[float | None, str | None]:
    """(רדיוס במייל ימי, אזהרה). None כשהפרק אינו מגדיר אזור שדה.

    רדיוס אפס אינו רדיוס: בפרק קציעות כתוב "מתוחם ברדיוס 0 מייל ימי",
    עוד קורבן של ההיפוך. הוא מדווח ולא מצויר.
    """
    for line in lines:
        match = _ATZ_RADIUS_RE.search(line)
        if not match:
            continue
        value = float(match.group("value"))
        unit = match.group("unit")
        if value <= 0:
            return None, f'רדיוס אזור שדה לא תקין במקור ("{line.strip()[:60]}") — לא מצויר.'
        if unit in ('נ"מ', "מייל", "מייל ימי"):
            return round(value, 2), None
        if unit == 'ק"מ':
            return round(value / 1.852, 2), None
        return round(value / 1852.0, 3), None
    return None, None


# הקוד שבכותרת, על הסוגריים שסביבו. הוא מוצג בחלונית בשורה משלו
# ("קוד ICAO"), ובכותרת הוא רק גורר איתו את הסוגריים המהופכים של
# ההיפוך הדו־כיווני — ")LLHA(", ")LLAA)", "( )" ריקים כשהקוד עצמו
# יצא מגופן סימבולי.
_TITLE_CODE_RE = re.compile(r"[(\)]?\s*(?:LL[A-Z]{2})?\s*[(\)]?\s*$")
_INLINE_CODE_RE = re.compile(r"\s*[(\)]\s*LL[A-Z]{2}\s*[(\)]\s*")


def _clean_title(text: str) -> str | None:
    """כותרת הפרק בלי הקוד ובלי סוגריים פתוחים.

    "מנחת מסוקים תפן (ישקר – )LLIS" הוא המקרה הקשה: הקוד יושב **בתוך**
    הסוגריים שפתחו שם נוסף, וכשמסירים אותו נשאר סוגר פתוח. סוגר בלי בן
    זוג נסגר, וסוגר סוגר בלי פותח נמחק.
    """
    text = unmirror_brackets(text)
    text = _INLINE_CODE_RE.sub(" ", text)
    text = _TITLE_CODE_RE.sub("", text)
    text = re.sub(r"\bLL[A-Z]{2}\b", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -–,:")

    opens, closes = text.count("("), text.count(")")
    if opens > closes:
        text = text.rstrip(" -–,:") + ")"
    elif closes > opens:
        text = text.replace(")", "", closes - opens)
    return text.strip(" -–,:") or None


def _title(lines: list[str]) -> str | None:
    for line in lines[:12]:
        text = line.strip()
        if _TITLE_RE.match(text):
            return _clean_title(text)
    return None


# שורת הנ"צ עצמה. "ברשת" הוא העוגן היחיד שחוזר בכל 24 הפרקים —
# הכותרת שמעליה מתחלפת בין "נקודת ציון מרכזית )ARP(" ל"נקודת
# התייחסות המנחת )HRP(", והמילה WGS מופיעה בארבעה איותים.
_GRID_RE = re.compile(r"ברשת")

# תיאור המשטח, כשיש בפרק יותר מאחד. מופיע בתוך שורת הנ"צ עצמה
# ("א. מנחת קרקעי, ברשת...") או בכותרת שמעליה ("ב. משטח הנחיתה -
# מסוקים").
_SURFACE_WORDS = ("מנחת", "משטח", "מסלול")
_ITEM_PREFIX_RE = re.compile(r"^(?:[א-ת]{1,2}[\"']?\.|\(?\d{1,2}\)?\)?)\s*")


def _surface_label(lines: list[str], index: int) -> str | None:
    """שם המשטח שאליו שייכת שורת הנ"צ, או None כשהפרק חד־משטחי."""
    inline = _GRID_RE.split(lines[index])[0].strip(" ,:-")
    candidate = _ITEM_PREFIX_RE.sub("", inline).strip(" ,:-")
    if candidate and any(word in candidate for word in _SURFACE_WORDS):
        return candidate

    # אחורה עד הכותרת הקרובה שמדברת על משטח — "ב. משטח הנחיתה - מסוקים".
    for line in reversed(lines[max(0, index - 5): index]):
        text = _ITEM_PREFIX_RE.sub("", line.strip()).strip(" ,:-")
        if text and any(word in text for word in _SURFACE_WORDS) and len(text) < 40:
            if "נקודת" in text or "גובה" in text:
                continue
            return text
    return None


def parse_field(
    name: str,
    lines: list[str],
    kind: str,
    pages: list[int],
    chart_lines: list[str] | None = None,
) -> tuple[list[dict], list[str]]:
    """(משטחי הנחיתה שבפרק, אזהרות).

    רשימה ולא רשומה, כי הפמ"ת מתאר לפעמים שני משטחים באותו פרק, כל
    אחד עם נ"צ וגובה משלו — הדסה עין כרם ("מנחת קרקעי" ו"מנחת מוגבה
    על גג בניין") וראשון לציון (מסלול מטוסים, ובנוסף "משטח הנחיתה -
    מסוקים"). לאחד אותם לנקודה אחת היה מוחק משטח קיים.

    רשימה ריקה כשאין בפרק נ"צ קריא. הקורא מדווח ומדלג, ולא ממציא
    מיקום — נקודה שגויה על מפה תעופתית גרועה מנקודה חסרה.
    """
    warnings: list[str] = []
    title = _title(lines)
    text = " ".join(lines)
    icao = None
    for source in (title or "", text):
        match = _ICAO_RE.search(source)
        if match:
            icao = match.group(1)
            break

    anchors = [
        (index, parse_dms_pair(line))
        for index, line in enumerate(lines)
        if _GRID_RE.search(line)
    ]
    anchors = [(index, coords) for index, coords in anchors if coords]
    if not anchors:
        return [], warnings

    radius, radius_warning = atz_radius_nm(lines)
    if radius_warning:
        warnings.append(f"{name}: {radius_warning}")

    # התרשים יכול לשבת בעמוד עם כותרת רצה ובלעדיה, ולכן שני המקורות
    # נסרקים. הדפוס הלטיני צר מדי מכדי להיתפס בטקסט עברי.
    from_chart = chart_elevation(list(chart_lines or []) + lines)

    records = []
    for position, (index, coords) in enumerate(anchors):
        label = _surface_label(lines, index) if len(anchors) > 1 else None
        # הנתונים של משטח הם מה שכתוב **בינו לבין המשטח הבא**.
        stop = anchors[position + 1][0] if position + 1 < len(anchors) else len(lines)
        window = lines[index:stop]

        # שם המשטח מכריע כשיש כמה, כי לפעמים הגבהים מרוכזים תחת כותרת
        # אחת ומסומנים בשם ("א. מנחת קרקעי: 2,088 רגל"). כשאין סימון כזה
        # — ראשון לציון נותן לכל משטח עמוד משלו — הקטע שבין שני המשטחים
        # הוא התשובה.
        feet, ambiguous = text_elevation(lines, label) if label else (None, False)
        if feet is None:
            feet, ambiguous = text_elevation(window)
        if feet is None and not label:
            feet, ambiguous = text_elevation(lines)

        # התרשים מכריע. הוא נקרא רק כשאין בפרק כמה משטחים — לשניים אין
        # דרך לדעת לאיזה מהם התרשים מתייחס.
        elevation = feet
        if from_chart is not None and len(anchors) == 1:
            if feet is not None and feet != from_chart:
                warnings.append(
                    f"{name}: גובה במלל {feet:,} רגל מול {from_chart:,} בתרשים — "
                    f"נלקח זה שבתרשים."
                )
            elevation = from_chart
        elif elevation is None and ambiguous:
            warnings.append(
                f"{name}: הגובה במלל מפורק לשני רצפי ספרות ואין תרשים להכריע — "
                f"לא פורסם גובה."
            )

        # משטח שני שרחוק מהראשון יותר מקילומטר אינו יכול להיות באותו
        # מתקן. ראו SAME_SITE_LIMIT_M — זה בדיוק המקרה של הגג בהדסה.
        if records:
            gap = distance_m((records[0]["lat"], records[0]["lon"]), coords)
            if gap > SAME_SITE_LIMIT_M:
                note = (
                    f'הפרק מתאר גם "{label or "משטח נוסף"}", אבל הנ"צ שלו במקור '
                    f'רחוק {gap / 1000:.1f} ק"מ מזה של {records[0]["surface"] or name} '
                    f"— רחוק מדי לשני משטחים באותו מתקן, ולכן הוא אינו מסומן."
                )
                warnings.append(f"{name}: {note}")
                records[0]["note"] = note
                continue

        surface_kind = kind
        if label and "מסוק" in label:
            surface_kind = "helipad"

        records.append({
            "name": f"{name} — {label}" if label else name,
            "surface": label,
            "title": title,
            "icao": icao,
            "kind": surface_kind,
            "lat": coords[0],
            "lon": coords[1],
            "elevation_ft": elevation,
            "atz_radius_nm": radius,
            "note": None,
            "pages": [min(pages), max(pages)],
        })
    return records, warnings


def parse_agricultural(rows: list[list[str]]) -> tuple[list[dict], list[str]]:
    """(מנחתים חקלאיים, אזהרות) מתוך טבלת "מנחתים נוספים".

    העמודות נקראות **לפי שורת הכותרת** ולא לפי מקומן:

        נ"צ מרכזי )ARP( · פרטי יצירת קשר · מפעילי מנחת · שם מנחת

    זה גם מה שהופך את הפרסור לבטוח — שורה שאין בה נ"צ דחוס אינה מנחת,
    ואם שורת הכותרת השתנתה הקורא אומר זאת במקום להמציא מיפוי.
    """
    warnings: list[str] = []
    columns = _agricultural_columns(rows)
    if not columns:
        return [], ["מנחתים נוספים: לא זוהתה שורת הכותרת של הטבלה — המבנה השתנה?"]

    fields_out: list[dict] = []
    for row in rows:
        cells = [re.sub(r"\s+", " ", (cell or "")).strip() for cell in row]
        coords = None
        for index in columns["arp"], None:
            if index is not None and index < len(cells):
                coords = parse_compact_pair(cells[index])
            if coords:
                break
        if not coords:
            continue
        if not in_israel(*coords):
            warnings.append(
                f'מנחתים נוספים: נ"צ מחוץ לתיבת ישראל בשורה "{" ".join(cells)[:50]}" — דולג.'
            )
            continue

        def cell(key: str) -> str | None:
            index = columns.get(key)
            if index is None or index >= len(cells) or not cells[index]:
                return None
            return cells[index]

        name = cell("name")
        if not name:
            warnings.append(
                f'מנחתים נוספים: שורה בלי שם מנחת ({cells[columns["arp"]]}) — דולגה.'
            )
            continue

        fields_out.append({
            "name": _tidy_name(name),
            "surface": None,
            "title": None,
            "icao": None,
            "kind": "agricultural",
            "lat": coords[0],
            "lon": coords[1],
            "elevation_ft": None,
            "atz_radius_nm": None,
            "operator": cell("operator"),
            "contact": _single_email(cell("contact")),
        })
    if not fields_out:
        warnings.append(
            "מנחתים נוספים: נמצאה שורת כותרת אבל אף שורה לא הניבה מנחת — "
            "המבנה השתנה?"
        )
    return fields_out, warnings


def _agricultural_columns(rows: list[list[str]]) -> dict[str, int] | None:
    """מיפוי שם עמודה לאינדקס, מתוך שורת הכותרת של הטבלה."""
    keys = (
        ("arp", ("נ\"צ", "ARP")),
        ("contact", ("יצירת קשר",)),
        ("operator", ("מפעילי",)),
        ("name", ("שם",)),
    )
    for row in rows:
        cells = [(cell or "") for cell in row]
        found = {}
        for key, needles in keys:
            for index, text in enumerate(cells):
                if any(needle in text for needle in needles):
                    found[key] = index
                    break
        if "arp" in found and "name" in found:
            return found
    return None


def _tidy_name(name: str) -> str:
    """מחזיר שם בסוגריים לסופו — "(חפציבה) אליעז" הוא "אליעז (חפציבה)"."""
    match = re.match(r"^\(([^)]+)\)\s*(.+)$", name)
    if match:
        return f"{match.group(2).strip()} ({match.group(1).strip()})"
    return name


def _single_email(text: str | None) -> str | None:
    """כתובת דואר אחת ונקייה, או None.

    התא בטבלה נשבר לשורות ולפעמים מכיל **שתי** כתובות שנדבקו
    ("ops@chimnir.co.iletzionia@gmail.com"). אין דרך חד־משמעית לפצל
    אותן, וכתובת שגויה גרועה מכתובת חסרה — אז מפרסמים רק כשיש בדיוק
    אחת, והשאר נקרא בפמ"ת.
    """
    if not text:
        return None
    joined = re.sub(r"\s+", "", text)
    # שתי כתובות שנדבקו נראות כמו אחת ארוכה, וגם הרג'קס קורא אותן
    # כאחת ("ops@chimnir.co.iletzionia"). ספירת ה-@ היא הבדיקה שתופסת זאת.
    if joined.count("@") != 1:
        return None
    matches = _EMAIL_RE.findall(joined)
    return matches[0] if len(matches) == 1 else None
