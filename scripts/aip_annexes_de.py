"""נספחים ד' ו-ה' של פמ"ת פרק א-17 — מכשולים קבועים ורשימת השמורות.

מודול טהור: מקבל טקסט עמוד ומחזיר רשומות. בלי רשת ובלי PDF, כדי
שאפשר יהיה לבדוק אותו על מחרוזות.

## נספח ד' — מכשולים קבועים

שמונה שורות, וכולן בלוני ריגול מעוגנים. זו שכבה שלא הייתה לנו בכלל,
והיא מסוכנת בדיוק בגלל שהיא קטנה: כבל של בלון מעוגן בגובה 3,400 רגל
אינו מופיע בשום מפה רגילה.

    קוד      סוג          שם האזור    גובה מרבי  רדיוס  מזרח (X)  צפון (Y)
    LLP3001  בלון מעוגן   חלמיש       3,400      0.54   350800E   320042N

הכותרת אומרת "מזרח (X) צפון (Y)" ומזמינה לחשוב על רשת ישראל, אבל
הערכים הם DDMMSS רגילים: `350800E` הוא 35°08'00"E. חלמיש אכן שם.

## נספח ה' — גנים לאומיים, אתרי קינון ושמורות טבע

עשרים עמודים, מאות שורות, ובכל אחת קוד, שם, סוג וגובה מרבי:

    LLP2329  אבוקה              שמורת טבע   300
    LLP1098  אבל בית מעכה       גן לאומי    500
    LLP1154  מצדה               גן לאומי    1000

**אין כאן קואורדינטות** — זה הפער שהוביל אותנו לשכבת רט"ג. אבל יש כאן
משהו שלרט"ג אין: **הגובה המרבי שמעליו מותר לטוס**. חיבור השניים לפי
שם הופך את פוליגוני רט"ג ממידע להתמצאות למגבלה עם מספר.

השם עלול להישבר על פני כמה שורות, כי עמודת "סוג אזור" מכילה ניסוחים
ארוכים ("אתרי קינון של מינים בסכנת הכחדה"). לכן שורה מזוהה לפי הקוד
ולא לפי מיקום, וכל מה שאחריה ועד הקוד הבא שייך לה.
"""

from __future__ import annotations

import re

_HEBREW = re.compile(r"[֐-׿]")

# קוד אזור. הקידומת מסמנת את הסוג:
#   LLP1xxx  גן לאומי / אתר קינון      LLP2xxx  שמורת טבע
#   LLP3xxx  מכשול קבוע
_CODE_RE = re.compile(r"\bLLP(\d{4})\b")

# DDMMSS עם אות כיוון, בכל סדר: "350800E 320042N" או ההפך.
_LON_RE = re.compile(r"\b(\d{2,3})(\d{2})(\d{2})([EW])\b")
_LAT_RE = re.compile(r"\b(\d{2})(\d{2})(\d{2})([NS])\b")

# "3,400" או "300" — גובה מרבי ברגל. הפסיק הוא מפריד אלפים.
_ALT_RE = re.compile(r"\b(\d{1,2},\d{3}|\d{3,5})\b")
# "0.54" — רדיוס במייל ימי.
_RADIUS_RE = re.compile(r"\b(\d+\.\d+)\b")


def unmirror(line: str) -> str:
    """מהפך ריצות עבריות שיוצאות הפוכות מחילוץ ה-PDF.

    pdfplumber מחזיר טקסט דו־כיווני כשהעברית הפוכה והלטינית תקינה.
    ההיפוך נעשה ברמת ריצה ולא ברמת תו, אחרת גם המספרים מתהפכים —
    וזה בדיוק הבאג שהפך את שט"ן 83 ל-38.
    """
    runs = re.findall(r"[֐-׿\"'’״׳]+|\s+|[^֐-׿\s]+", line)
    out = ["".join(reversed(run)) if _HEBREW.search(run) else run for run in reversed(runs)]
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _dms(degrees: str, minutes: str, seconds: str, hemisphere: str) -> float:
    value = int(degrees) + int(minutes) / 60.0 + int(seconds) / 3600.0
    return -value if hemisphere in ("S", "W") else value


def _feet(text: str) -> int | None:
    match = _ALT_RE.search(text.replace("‏", ""))
    return int(match.group(1).replace(",", "")) if match else None


# ---------------------------------------------------------------------------
# נספח ד' — מכשולים
# ---------------------------------------------------------------------------


def parse_obstacles(text: str) -> list[dict]:
    """מכשולים קבועים. מדלג על שורה בלי קואורדינטה — לא ממציא מיקום."""
    rows = []
    for raw in text.split("\n"):
        line = unmirror(raw)
        code = _CODE_RE.search(line)
        if not code or not line.count("LLP"):
            continue
        lat = _LAT_RE.search(line)
        lon = _LON_RE.search(line)
        if not (lat and lon):
            continue

        # הרדיוס נקרא לפני הגובה, אחרת "0.54" היה נבלע כמספר.
        radius = _RADIUS_RE.search(line)
        without_coords = _LAT_RE.sub(" ", _LON_RE.sub(" ", line))
        rows.append({
            "id": "LLP" + code.group(1),
            "name": _name_of(without_coords, code.group(1)),
            "lat": round(_dms(*lat.groups()), 6),
            "lon": round(_dms(*lon.groups()), 6),
            "radius_nm": float(radius.group(1)) if radius else None,
            "upper_ft": _feet(_RADIUS_RE.sub(" ", without_coords)),
        })
    return rows


def _name_of(line: str, digits: str) -> str:
    """הטקסט העברי שבשורה, בלי הקוד והמספרים."""
    cleaned = _CODE_RE.sub(" ", line)
    cleaned = re.sub(r"[\d,.]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


# ---------------------------------------------------------------------------
# נספח ה' — שמורות וגנים
# ---------------------------------------------------------------------------

def parse_reserves(rows: list[list]) -> list[dict]:
    """שורות נספח ה', **מטבלה ולא מטקסט שטוח**.

    זו אותה לקידה שכבר שילמנו עליה בנספחים ב' ו-ג': הטבלה מיושרת
    לעמודות, וטקסט ארוך בעמודת הסוג נשבר לשורות. בטקסט שטוח השם של
    רשומה אחת מופיע מעל ומתחת לשורת הקוד של רשומה אחרת, והתוצאה היא
    שמות מולחמים כמו "אבל בית מעכה סובב שמורת החולה". `extract_tables`
    מחזיר את התאים כמו שהם, והבעיה נעלמת.

    מקבל את פלט `page.extract_tables()[i]`.
    """
    out = []
    for row in rows:
        # תא רב־שורתי חייב היפוך **לכל שורה בנפרד**. היפוך של התא כולו
        # מהפך גם את סדר השורות, ו"אתרי קינון של מינים בסכנת הכחדה"
        # יוצא "בסכנת הכחדה אתרי קינון של מינים".
        cells = [
            " ".join(unmirror(part) for part in (cell or "").split("\n"))
            for cell in row
        ]
        code = next((_CODE_RE.search(c) for c in cells if _CODE_RE.search(c)), None)
        if not code:
            continue

        index = next(i for i, c in enumerate(cells) if _CODE_RE.search(c))
        # התא שלפני הקוד הוא השם, ולפניו הסוג. הגובה הוא התא המספרי.
        name = cells[index - 1].strip() if index >= 1 else ""
        kind = cells[index - 2].strip() if index >= 2 else ""
        altitude = next((_feet(c) for c in cells if _ALT_RE.fullmatch(c.strip())), None)
        if altitude is None:
            altitude = next((_feet(c) for c in cells if c.strip() and _feet(c)), None)

        if not name:
            continue
        out.append({
            "id": "LLP" + code.group(1),
            "name": re.sub(r"\s+", " ", name),
            "kind": re.sub(r"\s+", " ", kind) or None,
            "upper_ft": altitude,
        })
    return out
