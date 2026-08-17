"""בדיקות לנספחים ד' ו-ה' של פרק א-17."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aip_annexes_de as ax  # noqa: E402


class UnmirrorTests(unittest.TestCase):
    def test_digits_survive(self):
        """הבאג שכבר עלה ביוקר: היפוך תו־תו הפך את 83 ל-38."""
        self.assertIn("3,400", ax.unmirror("3,400 שיבכמ"))

    def test_latin_untouched(self):
        self.assertIn("LLP3001", ax.unmirror("LLP3001 ןוגעמ ןולב"))


class ObstacleTests(unittest.TestCase):
    # שורה כפי שהיא יוצאת מה-PDF: עברית הפוכה, לטינית ומספרים תקינים.
    LINE = "LLP3001 ןגועמ ןולב שימלח 3,400 0.54 350800E 320042N"

    def test_parses_a_balloon(self):
        row = ax.parse_obstacles(self.LINE)[0]
        self.assertEqual(row["id"], "LLP3001")
        self.assertAlmostEqual(row["lat"], 32.011667, places=5)
        self.assertAlmostEqual(row["lon"], 35.133333, places=5)
        self.assertEqual(row["upper_ft"], 3400)
        self.assertEqual(row["radius_nm"], 0.54)

    def test_thousands_separator_is_not_a_radius(self):
        """'3,400' הוא גובה ו-'0.54' רדיוס. בלי ההפרדה הגובה יוצא 0."""
        row = ax.parse_obstacles(self.LINE)[0]
        self.assertNotEqual(row["upper_ft"], 0)
        self.assertLess(row["radius_nm"], 1)

    def test_line_without_coordinates_is_dropped(self):
        """בלי קואורדינטה אין מכשול. לא ממציאים מיקום."""
        self.assertEqual(ax.parse_obstacles("LLP3099 ןולב 2,000 0.5"), [])

    def test_line_without_code_is_ignored(self):
        self.assertEqual(ax.parse_obstacles("350800E 320042N 3,400"), [])


class ReserveTests(unittest.TestCase):
    # פלט extract_tables: [גובה, ריק..., סוג, שם, קוד]
    TABLE = [
        ["", "", 'גובה מירבי', "", "", 'רוזא גוס', 'רוזא םש', 'דוק'],
        ["300", "", "", "", "", 'עבט תרומש', 'הקובא', "LLP2329"],
        ["1000", "", "", "", "", 'ימואל ןג', 'הדצמ', "LLP1154"],
    ]

    def test_reads_columns(self):
        rows = ax.parse_reserves(self.TABLE)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "LLP2329")
        self.assertEqual(rows[0]["name"], "אבוקה")
        self.assertEqual(rows[0]["kind"], "שמורת טבע")
        self.assertEqual(rows[0]["upper_ft"], 300)
        self.assertEqual(rows[1]["upper_ft"], 1000)

    def test_header_row_has_no_code(self):
        self.assertNotIn("דוק", [r["id"] for r in ax.parse_reserves(self.TABLE)])

    def test_multiline_cell_keeps_line_order(self):
        """תא רב־שורתי חייב היפוך לכל שורה בנפרד, אחרת סדר השורות
        מתהפך ו'אתרי קינון של מינים בסכנת הכחדה' יוצא הפוך."""
        table = [["500", "", "", "", "",
                  "םינימ לש ןוניק ירתא\nהדחכה תנכסב", 'הלוחה', "LLP1046"]]
        self.assertEqual(ax.parse_reserves(table)[0]["kind"],
                         "אתרי קינון של מינים בסכנת הכחדה")

    def test_row_without_name_is_dropped(self):
        self.assertEqual(ax.parse_reserves([["300", "", "", "LLP2000"]]), [])


class NormaliseTests(unittest.TestCase):
    def test_only_quotes_and_spaces(self):
        from build_annexes_de import normalise

        self.assertEqual(normalise('נחל מהר"ל'), "נחל מהרל")
        self.assertEqual(normalise("  אום  זוקא "), "אום זוקא")
        # אותיות לא נוגעים בהן — נרמול אגרסיבי מייצר התאמות שגויות.
        self.assertEqual(normalise("אודים"), "אודים")


if __name__ == "__main__":
    unittest.main(verbosity=2)
