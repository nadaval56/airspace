"""שמירה על טבלאות הפענוח מפני סטייה בין הפייתון לדפדפן.

עמוד הלימוד (`assets/learn.js`) נושא עותק של טבלאות קוד ה-Q, מפני
שהוא רץ בדפדפן ואין לו גישה למודול הפייתון. עותק הוא חוב: תיקון
בצד אחד שאינו מגיע לשני מייצר מצב שבו המפה אומרת דבר אחד והשיעור
מלמד אחר — וזה בדיוק ההפך ממה שהעמוד נועד לו.

הבדיקה קוראת את הטבלאות מתוך קובץ ה-JS ומשווה אותן למקור. חריג
אחד מותר ומתועד: הקוד LW, שאומת מול נוסחי ההודעות אך לא נכנס
לפרסור כדי לא לשנות את פלט המפה.
"""

from __future__ import annotations

import pathlib
import re
import unittest

from scripts import parse_qline

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEARN_JS = ROOT / "assets" / "learn.js"

# קוד שקיים בעמוד הלימוד ובכוונה אינו בפרסור. ראו את ההסבר בראש
# assets/learn.js: 27 הודעות בפיד נושאות אותו וכולן פותחות ב-
# "WILL TAKE PLACE", אבל הוספתו לפרסור הייתה משנה את מה שמוצג
# על המפה, וזה שינוי שאינו שייך לעמוד הזה.
LEARN_ONLY_CONDITIONS = {"LW": "יתקיים"}

_ENTRY_RE = re.compile(r"^\s{2}(?:'([^']+)'|([A-Z]{1,4})):\s*'((?:[^'\\]|\\.)*)',\s*$")


def js_table(name: str) -> dict[str, str]:
    """מחלץ אובייקט־קבוע פשוט מתוך קובץ ה-JS.

    מספיק לטבלאות שלנו: מפתח, נקודתיים, מחרוזת במרכאות בודדות, פסיק.
    כל צורה אחרת תיפול כאן ולא תיבלע בשקט.
    """
    text = LEARN_JS.read_text(encoding="utf-8")
    start = text.index("const %s = {" % name)
    end = text.index("\n};", start)
    table: dict[str, str] = {}
    for line in text[start:end].splitlines()[1:]:
        if not line.strip() or line.strip().startswith("//"):
            continue
        m = _ENTRY_RE.match(line)
        if not m:
            continue
        key = m.group(1) or m.group(2)
        value = m.group(3).replace("\\'", "'").replace('\\"', '"')
        table[key] = value
    return table


class LearnTablesTest(unittest.TestCase):
    def test_subjects_match_parser(self):
        self.assertEqual(js_table("Q_SUBJECT"), parse_qline.Q_SUBJECT)

    def test_subject_notes_match_parser(self):
        # לעמוד הלימוד מותר להסביר יותר, אבל לא להסביר **אחרת**.
        js = js_table("Q_SUBJECT_NOTE")
        for code, note in parse_qline.Q_SUBJECT_NOTE.items():
            self.assertEqual(js.get(code), note, "הערה שונה לקוד %s" % code)
        for code in js:
            self.assertIn(code, parse_qline.Q_SUBJECT, "הערה לקוד שאינו בטבלה: %s" % code)

    def test_conditions_match_parser(self):
        js = js_table("Q_CONDITION")
        expected = dict(parse_qline.Q_CONDITION)
        expected.update(LEARN_ONLY_CONDITIONS)
        self.assertEqual(js, expected)

    def test_scope_matches_parser(self):
        js = js_table("Q_SCOPE")
        for code, label in parse_qline.Q_SCOPE.items():
            self.assertEqual(js.get(code), label, "היקף שונה לקוד %s" % code)

    def test_tables_are_not_empty(self):
        # אם החילוץ יישבר, כל הבדיקות שלמעלה יעברו על מילון ריק.
        self.assertGreater(len(js_table("Q_SUBJECT")), 40)
        self.assertGreater(len(js_table("Q_CONDITION")), 30)


if __name__ == "__main__":
    unittest.main()
