#!/usr/bin/env python3
"""סיווג משני לאזורי הפמ"ת — נושא ורצפת גובה.

## למה זה קיים

הסיווג הראשי של הפמ"ת הוא ארבע קטגוריות: אסור, מוגבל, מסוכן, אסור
לכטב"ם. הוא מדויק אבל גס. מי שמטיס רחפן רוצה לדעת מה מתחיל בקרקע ומה
מתחיל ב-4,000 רגל; מי שמתכנן טיסה רוצה להפריד שטחי אש מאסדות גז.

## מה מותר לגזור, ומה לא

**רצפת הגובה** היא נתון מהטבלה. אין כאן פרשנות.

**הנושא** נגזר ממילים שכתובות **בשם הרשמי עצמו**. "שטח אש 209" נושא את
המילים "שטח אש"; "אסדת לוויתן" נושאת את המילה "אסדת". זו קריאה של
הכתוב, לא ניחוש לפי היכרות עם המקום.

**מה שלא נגזר:** סוג המתקן. בדקתי את שתי הטבלאות במקור —

    נספח ב': צפון )Y( · מזרח )X( · גובה מזערי · גובה מרבי · שם האזור · קוד זיהוי
    נספח ג': צפון )Y( · מזרח )X( · רדיוס הסגירה · שם האזור · קוד זיהוי

אין בהן עמודת סוג, ייעוד או הערות. לכן אי אפשר להפריד בית כלא ממתקן
משטרה מבלי להסתמך על היכרות שלי עם השמות — וזה בדיוק הסוג של ניחוש
שאסור לצייר על מפת בטיחות. אזור בלי מילת מפתח מקבל `אחר`, לא ניחוש.
"""

from __future__ import annotations

# סדר הבדיקה קובע: הראשון שמתאים מנצח. הרשימות מכילות מילים שמופיעות
# בשם הרשמי כלשונן.
THEME_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("firing", "שטחי אש ומטווחים", ("שטח אש", "מטווח", 'שט"ן')),
    ("drop", "גלילי הצנחה", ("גליל הצנחה",)),
    ("balloon", "בלונים", ("בלון",)),
    ("offshore", "אסדות ומתקנים ימיים", ("אסדת", "ים טטיס", "תמר/")),
    ("judea", "יהודה ושומרון", ("יהודה ושומרון",)),
    ("model", "אתרי רחפנים וטיסנים", ("הטסת רחפנים", "טיסנים")),
    ("police", "מתקני משטרה", (
        "מחוז", "מטה ארצי", "מפקדת", "משטרת", "אגף התנועה",
        "מכללה", "להב 433", "תחנת ראשון",
    )),
    ("transit", "מרחבים ומעברים", ("מרחב", "נקודת גשר")),
]

THEME_LABELS = {key: label for key, label, _ in THEME_RULES}
THEME_LABELS["other"] = "ללא מילת סיווג בשם"

# הסף שביקש המשתמש: אזור שרצפתו גבוהה פחות רלוונטי למי שטס נמוך.
FLOOR_SPLIT_FT = 4000

FLOOR_LABELS = {
    "ground": "מהקרקע",
    "low": f"עד {FLOOR_SPLIT_FT:,} רגל",
    "high": f"מעל {FLOOR_SPLIT_FT:,} רגל",
    "unknown": "ללא רצפה מוגדרת",
}

_GROUND_WORDS = ("GND", "MSL", "SFC")


def theme(name: str | None) -> str:
    """מפתח הנושא לפי מילים שבשם הרשמי. `other` כשאין התאמה."""
    text = name or ""
    for key, _, words in THEME_RULES:
        if any(word in text for word in words):
            return key
    return "other"


def floor_feet(lower_limit) -> int | None:
    """רצפת האזור ברגל. `None` כשאין נתון בטבלה."""
    if lower_limit is None:
        return None
    raw = str(lower_limit).strip().upper()
    if not raw or raw == "UNL":
        return None
    if raw in _GROUND_WORDS:
        return 0
    digits = "".join(ch for ch in raw if ch.isdigit())
    return int(digits) if digits else None


def floor_band(lower_limit) -> str:
    """קבוצת הרצפה, לסינון.

    אזורי הכטב"ם בנספח ג' אינם נושאים גובה כלל — ההגבלה שם אינה
    תחומה בגובה אלא ברדיוס. `unknown` הוא זה, ולא "לא ידוע".
    """
    feet = floor_feet(lower_limit)
    if feet is None:
        return "unknown"
    if feet <= 0:
        return "ground"
    return "low" if feet <= FLOOR_SPLIT_FT else "high"


def classify(properties: dict) -> dict:
    """מחזיר את שדות הסיווג שיש להוסיף לאזור."""
    return {
        "theme": theme(properties.get("name")),
        "floor_band": floor_band(properties.get("lower_limit")),
    }
