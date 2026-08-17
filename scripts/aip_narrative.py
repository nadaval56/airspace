"""פרסור המלל של פמ"ת פרק א-17 — מה שהטבלאות לא אומרות.

## למה זה קיים

הסיווג המשני (`aip_classify`) נגזר עד עכשיו **משם האזור בלבד**, כי שתי
טבלאות הנספחים מוסרות קואורדינטות, גבהים, שם וקוד — ואין בהן עמודת
ייעוד. התוצאה: 89 מתוך 137 אזורים נפלו ל"ללא סיווג".

אבל הטבלאות אינן המקור היחיד, והן גם לא המקור **הקובע**. כך כתוב
בעמוד הראשון של הפרק:

    במקרה של סתירה בתחומי אזורים אסורים, מוגבלים ומסוכנים לטיסה בין
    פרסומי הפמ"ת יהווה פרק א-17 (מלל) הפרסום הקובע.

והמלל אומר על אזורים דברים שהטבלה משמיטה:

    LLP01  האזור האסור **מעל שמורת הטבע** "החולה"
    LLP09  האזור האסור "**המכון למחקר** ביולוגי" בנס ציונה
    LLD30  האזור המסוכן "טורבינות" **בעמק הבכא**
    LLD48  ...לתיאום טיסה במרחב זה יש ליצור קשר עם **נציג חברת קנדו**

זו עדיין קריאה של הכתוב ולא ניחוש לפי היכרות עם המקום — רק שהפעם
קוראים את כל מה שהמקור כתב על האזור, ולא את שמו בלבד.

## מבנה המלל, והכלל שנגזר ממנו

הפרק בנוי בסעיפים ממוספרים, וכל אזור הוא פריט ברשימה שנפתח בקוד שלו:

    ג.   LLP03, האזור האסור "מכון דוד": מגובה פני הקרקע ועד...
    1)   LLU01, האזור האסור "איילון-מעשיהו".

**פריט חדש מתחיל בשורה שבה סימן הפריט מלווה בקוד אזור, ונמשך עד
הפריט הבא.** שורת המשך שנפתחת במילה שנראית כמו סימן פריט ("הים.")
אינה פותחת פריט, כי אין אחריה קוד — וזה בדיוק ההבדל שמנע מחצי
המשפטים להיבלע.

## שב"ס — הקבוצה הגדולה, ולמה מותר לקרוא לה בשם

סעיף 1א, שתחתיו יושבים **כל** אזורי ה-LLU, פותח בהוראה:

    גורם המעוניין להגיש בקשה לטיסה בתוך מרחבים אלו מחויב ליצור קשר עם
    שירות בתי הסוהר (מטה ארצי...) ולקבל אישור בכתב...
    ב. אזורים שאינם תחת אחריות שירות בתי הסוהר, יש לתאם מול הגורם
    המצוין תחת האזור האסור הרלוונטי.

כלומר המקור עצמו מחלק את אזורי ה-LLU לשניים: מי שמצוין תחתיו גורם
תיאום, וכל השאר — שהתיאום עליהם מול שב"ס. זו חלוקה מבנית שכתובה
במסמך, ולכן `coordination` נשמר לכל פריט: קיומו הוא הנתון.

**מה שעדיין לא נגזר:** מה המתקן *הוא*. "אשל" נשאר "אשל". האמירה
היחידה שהקוד עושה עליו היא מה שהפרק אומר — שהתיאום עליו מול שב"ס.
"""

from __future__ import annotations

import re

# סימן פריט ברשימה: אות עברית ("ג.", "יז.") או מספר ("1)"). ההיפוך של
# ה-PDF מזיז את הסוגר לפני הספרה, ולכן שתי הצורות מתקבלות.
_ITEM_RE = re.compile(r"^(?:[א-ת]{1,3}[\"']?\.|[()]?\d{1,3}[()]?)\s*[,\s]*")

_CODE_RE = re.compile(r"LL[PRDU]\s?\d{1,4}")

# הקוד — או צמד קודים ("LLP171/LLP173") — **בראש** הפריט. עיגון לראש
# הוא מה שמבדיל פריט אמיתי משורה שמזכירה טווח קודים ("אזורים
# LLU59-LLU72 הינם בגובה מירבי..."), שאינה אזור אלא הערה על קבוצה.
_HEAD_CODES_RE = re.compile(
    r"^(LL[PRDU]\s?\d{1,4}(?:\s*[/,]\s*LL[PRDU]\s?\d{1,4})*)"
)

# כותרת סעיף ראשי — ".1 אזורים אסורים", "1א. אזורים אסורים לטיסה",
# ".4 מגבלות קרבה לגבול". סוגרת את הפריט הפתוח, כדי שסעיף שלם לא
# ייבלע לתוך האזור האחרון שקדם לו.
_SECTION_RE = re.compile(r"^\.?\d{1,2}(?:א)?\.?\s+(?:אזורים|מגבלות|בקשה|נספחים)")

# כותרת תחתונה חוזרת בכל עמוד. אינה חלק משום פריט.
_FOOTER_RE = re.compile(r"רשות התעופה האזרחית")

# ניסוחי התיאום שמופיעים בפרק.
_COORDINATION_MARKERS = (
    "לתיאום טיסה",
    "לצורך תיאום טיסה",
    "יש ליצור קשר",
    "יש לתאם",
    "יש לפנות",
)

# היכן נגמר החלק שמתאר **מה** האזור. מילות הסיווג יושבות לפני הגבהים
# ולפני הוראת התיאום, ושתיהן עלולות להטעות: "לתיאום טיסה **במרחב** זה"
# הוא ניסוח קבוע שחוזר בעשרות פריטים, ולא אומר שהאזור הוא מרחב.
_TITLE_STOPS = (
    "מגובה",
    "בכל גובה",
    "למובילים אוויריים",
    ":",
) + _COORDINATION_MARKERS

# מי הגורם. שני הניסוחים היחידים שמופיעים במסמך, בדוקים מולו.
_AUTHORITY_RES = (
    re.compile(r"ליצור קשר עם\s+(?P<who>[^.:]+?)\s*(?:בטלפון|בדוא|במייל|$)"),
    re.compile(r"לפנות ל[־-]?\s*(?P<who>[^.:]+?)\s*(?:בטלפון|בדוא|במייל|$)"),
)


# סימן פיסוק שנדד לפני מספר. תוצר של ההיפוך הדו־כיווני: העברית
# יוצאת הפוכה והספרות תקינות, ולכן הנקודה שסוגרת "...בטלפון 050-1234567."
# יוצאת כ-".050-1234567". המשפט נשמר כלשונו, אבל הפיסוק חוזר למקומו —
# אחרת חלונית שמציגה טלפון נראית שבורה.
_STRAY_PUNCT_RE = re.compile(r"(?:(?<=\s)|^)([.,])(\d[\d\-/]*)")


def _restore_punctuation(text: str) -> str:
    return _STRAY_PUNCT_RE.sub(r"\2\1", text)


def _is_footer(line: str) -> bool:
    return bool(_FOOTER_RE.search(line))


def entry_title(text: str) -> str:
    """החלק שמתאר מה האזור — עד תחילת הגבהים.

    "LLP01 האזור האסור מעל שמורת הטבע "החולה"" ולא כל הפריט: המשך
    הפריט עשוי להזכיר אזור אחר ("בחלק החופף לאזור האסור 'הר הבית'"),
    ומילת סיווג שנשאבה משם הייתה מסווגת את האזור הלא נכון.
    """
    cut = len(text)
    for stop in _TITLE_STOPS:
        position = text.find(stop)
        if position != -1:
            cut = min(cut, position)
    return _CODE_RE.sub("", text[:cut]).strip(" ,:/\"'")


def coordination_text(text: str) -> str | None:
    """משפט התיאום כלשונו, או None כשאין כזה בפריט."""
    for marker in _COORDINATION_MARKERS:
        position = text.find(marker)
        if position != -1:
            return text[position:].strip()
    return None


def authority_of(coordination: str | None) -> str | None:
    """שם הגורם מתוך משפט התיאום. None כשהמשפט נותן טלפון בלבד."""
    if not coordination:
        return None
    for pattern in _AUTHORITY_RES:
        match = pattern.search(coordination)
        if match:
            who = re.sub(r"\s+", " ", match.group("who")).strip(" ,-–")
            # ניסוח כמו "יש ליצור קשר בטלפון" נותן שבר ריק או מספר.
            if len(who) >= 3 and not who[0].isdigit():
                return who
    return None


def parse_body(lines: list[str]) -> dict[str, dict]:
    """מפרסר את מלל הפרק לפריט לכל קוד אזור.

    מקבל שורות **מיושרות** (ראו `aip_annexes.reverse_hebrew`), כי
    המודול הזה אינו נוגע ב-PDF.
    """
    entries: dict[str, list[str]] = {}
    current: list[str] = []

    for raw in lines:
        line = raw.strip()
        if not line or _is_footer(line):
            continue
        if _SECTION_RE.match(line):
            current = []
            continue

        marker = _ITEM_RE.match(line)
        head = line[marker.end():] if marker else ""
        at_head = _HEAD_CODES_RE.match(head) if marker else None
        codes = (
            [c.replace(" ", "") for c in _CODE_RE.findall(at_head.group(1))]
            if at_head
            else []
        )
        if codes:
            current = codes
            for code in codes:
                entries.setdefault(code, []).append(head)
            continue

        # שורת המשך. גם כשהיא נפתחת במילה שנראית כמו סימן פריט.
        for code in current:
            entries[code].append(line)

    parsed: dict[str, dict] = {}
    for code, parts in entries.items():
        text = _restore_punctuation(re.sub(r"\s+", " ", " ".join(parts)).strip())
        coordination = coordination_text(text)
        parsed[code] = {
            "code": code,
            "text": text,
            "title": entry_title(text),
            "coordination": coordination,
            "authority": authority_of(coordination),
        }
    return parsed
