#!/usr/bin/env python3
"""בדיקת עשן על האתר החי.

רצה מ-GitHub Actions, כי משם יש רשת פתוחה. פותחת את הדף בדפדפן אמיתי
ובודקת שהוא **עובד**, לא רק שהוא נטען: שהשכבות צוירו, שהעץ מסנן,
שהרשימה מלאה, ושאין שגיאות JavaScript.

הבדיקה נכשלת בקול. אתר שנשבר בשקט גרוע מאתר שלא עלה.

שימוש:
    python3 scripts/check_live.py https://nadaval56.github.io/airspace/
"""

from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

# ספי מינימום. לא מספרים מדויקים — הנתונים זזים כל שעה — אלא הרף
# שמתחתיו ברור שמשהו נשבר.
MIN_AIP_SHAPES = 100
MIN_NOTAMS = 20
MIN_CHIPS = 15

PROBE = """() => {
  const q = (s) => document.querySelector(s);
  const all = (s) => [...document.querySelectorAll(s)];
  const parent = q('#toggle-aip');
  const panel = parent && parent.closest('.ctl');
  return {
    title: (q('h1') || {}).textContent,
    freshness: (q('#freshness-value') || {}).textContent,
    aipCount: (q('#count-aip') || {}).textContent,
    notamCount: (q('#count-notam') || {}).textContent,
    mapShapes: all('#map path').length,
    listItems: all('#notam-list > li').length,
    listCollapsed: !q('#notam-fold').closest('details').open,
    foldLabel: (q('#notam-fold') || {}).textContent,
    chips: all('input[data-layer]').length,
    axisToggles: all('.axis__toggle').length,
    columns: all('.controls__col').length,
    panelsPerColumn: all('.controls__col').map((c) => c.querySelectorAll('.ctl').length),
    limitsHeading: (q('#limits-heading') || {}).textContent,
    cvfrEnabled: q('#toggle-cvfr') ? !q('#toggle-cvfr').disabled : false,
    parentChecked: parent ? parent.checked : null,
    leaves: panel ? panel.querySelectorAll('input[data-layer]').length : 0
  };
}"""


def fail(message: str) -> None:
    print(f"  ✗ {message}")
    fail.count += 1


fail.count = 0


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://nadaval56.github.io/airspace/"
    print(f"בודק {url}\n")

    with sync_playwright() as play:
        # ב-Actions מתקינים דפדפן רגיל; בסביבות שבהן הוא כבר קיים
        # במקום אחר, `CHROMIUM_PATH` מצביע עליו.
        browser = play.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_PATH") or None)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        console: list[str] = []
        page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)

        response = page.goto(url, wait_until="networkidle", timeout=60000)
        print(f"HTTP {response.status if response else '—'}")
        page.wait_for_timeout(4000)

        state = page.evaluate(PROBE)
        print(json.dumps(state, ensure_ascii=False, indent=2))
        print()

        if state["mapShapes"] < MIN_AIP_SHAPES:
            fail(f"רק {state['mapShapes']} צורות על המפה")
        if state["listItems"] < MIN_NOTAMS:
            fail(f"רק {state['listItems']} פריטים ברשימה")
        if not state["listCollapsed"]:
            fail("הרשימה אינה מקופלת בטעינה")
        if state["chips"] < MIN_CHIPS:
            fail(f"רק {state['chips']} תיבות סינון")
        if state["columns"] != 2:
            fail(f"{state['columns']} טורים במקום 2")
        if state["axisToggles"] < 5:
            fail(f"רק {state['axisToggles']} תיבות ציר")
        if "איפה" not in (state["title"] or ""):
            fail(f"כותרת לא צפויה: {state['title']}")
        if state["limitsHeading"] != "מגבלות האפליקציה":
            fail(f"כותרת המגבלות: {state['limitsHeading']}")
        if not state["cvfrEnabled"]:
            fail("שכבת ה-CVFR מושבתת — הקובץ חסר?")
        if "טוען" in (state["freshness"] or "") or "לא נטען" in (state["freshness"] or ""):
            fail(f"חותמת הזמן: {state['freshness']}")

        # העץ: כיבוי אב חייב לכבות את כל הבנים ולהוריד צורות מהמפה.
        before = state["mapShapes"]
        page.evaluate("document.getElementById('toggle-aip').click()")
        page.wait_for_timeout(700)
        after = page.evaluate("document.querySelectorAll('#map path').length")
        leaves_on = page.evaluate(
            "[...document.getElementById('toggle-aip').closest('.ctl')"
            ".querySelectorAll('input[data-layer]')].filter(i=>i.checked).length"
        )
        print(f"כיבוי שכבת הפמ\"ת: {before} → {after} צורות · בנים דלוקים: {leaves_on}")
        if after >= before:
            fail("כיבוי השכבה לא הוריד צורות")
        if leaves_on:
            fail(f"{leaves_on} בנים נשארו דלוקים אחרי כיבוי האב")

        # והרשימה לא הושפעה — זה הכלל שאסור לו להישבר.
        still = page.evaluate("document.querySelectorAll('#notam-list > li').length")
        if still != state["listItems"]:
            fail(f"הרשימה השתנתה עם הסינון: {state['listItems']} → {still}")

        page.evaluate("document.getElementById('toggle-aip').click()")
        page.wait_for_timeout(700)
        restored = page.evaluate("document.querySelectorAll('#map path').length")
        print(f"הדלקה חוזרת: {after} → {restored} צורות")
        if restored != before:
            fail(f"ההדלקה לא החזירה את המצב: {before} → {restored}")

        # קיפול הרשימה
        page.evaluate("document.getElementById('notam-fold').click()")
        page.wait_for_timeout(500)
        label = page.evaluate("document.getElementById('notam-fold').textContent")
        print(f"תווית אחרי פתיחה: {label.strip()}")
        if "הסתר" not in label:
            fail("תווית הכפתור לא התחלפה ל'הסתר'")

        if errors:
            fail(f"שגיאות JavaScript: {errors}")
        # 404 של אריחי מפה אינו שבר באתר; שאר שגיאות הקונסולה כן מעניינות.
        real = [c for c in console if "tile" not in c.lower() and "basemaps" not in c.lower()]
        if real:
            print(f"  הערות קונסולה: {real[:5]}")

        browser.close()

    print()
    if fail.count:
        print(f"נכשל: {fail.count} בדיקות")
        return 1
    print("הכול תקין.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
