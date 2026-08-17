#!/usr/bin/env python3
"""בדיקות לפרסור מלל פרק א-17.

כל השורות כאן הן שורות **אמיתיות** מהמסמך, אחרי היישור של
`aip_annexes.reverse_hebrew`. בדיקה על טקסט מומצא הייתה מאמתת את
הדמיון שלי ולא את המקור.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aip_narrative import (  # noqa: E402
    authority_of,
    coordination_text,
    entry_title,
    parse_body,
)

# פריט אחד, שתי שורות — כפי שהוא יוצא מה-PDF אחרי יישור.
BALLOON = [
    'לב. ,LLP42 האזור אסור לטיסה "בלון צופר," מגובה פני הקרקע ועד לגובה',
    "2000 רגל מעל פני הים.",
]

RESERVE = [
    'א. ,LLP01 האזור האסור מעל שמורת הטבע "החולה:" מגובה פני הקרקע',
    "ועד גובה 3000 רגל מעל פני הים.",
]

WITH_CONTACT = [
    'ג. ,LLP03 האזור האסור "מכון דוד:" מגובה פני הקרקע ועד גובה 3000 רגל',
    'מעל פני הים, לתיאום טיסה במרחב זה יש ליצור קשר עם מב"ט אבטחה',
    "מכון דוד בטלפון .050-3384198",
]

# רשימת הכטב"ם: סימן הפריט הוא מספר, וההיפוך מקדים את הסוגר.
UAV_ITEMS = [
    ')1 ,LLU01 האזור האסור "איילון-מעשיהו."',
    ')2 ,LLU02 האזור האסור "אשל."',
    ')55 ,LLU55 האזור האסור "דור." לתיאום טיסה במרחב זה יש ליצור',
    'קשר עם נציג חברת "שברון" במייל: itzik.Sardinas@chevron.com',
]


class ItemBoundaryTest(unittest.TestCase):
    """פריט מתחיל בסימן פריט **שאחריו קוד**, ולא בכל דבר שנראה כמו סימן."""

    def test_two_line_item_is_joined(self):
        entries = parse_body(BALLOON)
        self.assertEqual(list(entries), ["LLP42"])
        self.assertIn("2000 רגל", entries["LLP42"]["text"])

    def test_continuation_that_looks_like_a_marker_is_not_a_new_item(self):
        """שורת המשך שנפתחת ב"הים." — שלוש אותיות ונקודה, בדיוק כמו
        סימן פריט. בלי דרישת הקוד, חצי המשפטים במסמך נבלעו."""
        lines = [
            'כד. ,LLP24 אזור אסור "שורק:" מגובה פני הים ועד גובה 4000 רגל מעל פני',
            "הים.",
        ]
        entries = parse_body(lines)
        self.assertEqual(list(entries), ["LLP24"])
        self.assertTrue(entries["LLP24"]["text"].endswith("הים."))

    def test_a_range_mention_is_not_an_item(self):
        """'אזורים LLU59-LLU72 הינם בגובה מירבי' היא הערה על קבוצה,
        ולא שני אזורים. הקוד חייב לשבת בראש הפריט."""
        entries = parse_body(['ג. אזורים LLU59-LLU72 הינם בגובה מירבי 300 רגל מעפ"ש.'])
        self.assertEqual(entries, {})

    def test_a_pair_of_codes_shares_one_entry(self):
        lines = ['יז. ,LLP173/LLP171 האזור האסור "יהודה ושומרון" (מקטע צפוני ומקטע']
        entries = parse_body(lines)
        self.assertEqual(set(entries), {"LLP171", "LLP173"})
        for code in entries:
            self.assertIn("יהודה ושומרון", entries[code]["title"])

    def test_section_header_closes_the_open_item(self):
        """סעיף חדש אינו המשך של האזור האחרון שלפניו."""
        lines = BALLOON + [".2 אזורים מוגבלים לטיסה )LLR(", "א. אין לבצע טיסה בשטחי אש"]
        entries = parse_body(lines)
        self.assertNotIn("אין לבצע טיסה", entries["LLP42"]["text"])

    def test_numbered_uav_items_are_parsed(self):
        entries = parse_body(UAV_ITEMS)
        self.assertEqual(set(entries), {"LLU01", "LLU02", "LLU55"})


class TitleTest(unittest.TestCase):
    """הכותרת היא מה שהמקור אומר שהאזור **הוא** — ולא כל הפריט."""

    def test_reserve_wording_survives(self):
        entries = parse_body(RESERVE)
        self.assertIn("שמורת הטבע", entries["LLP01"]["title"])

    def test_title_stops_before_altitudes(self):
        title = entry_title('LLP42 האזור אסור לטיסה "בלון צופר," מגובה פני הקרקע')
        self.assertEqual(title, 'האזור אסור לטיסה "בלון צופר')

    def test_title_stops_before_the_coordination_sentence(self):
        """"לתיאום טיסה **במרחב** זה" חוזר בעשרות פריטים. בלי החיתוך
        כל אזור עם טלפון היה מסווג כ"מרחב"."""
        title = entry_title('LLU59 האזור האסור "מישר." לתיאום טיסה במרחב זה יש ליצור קשר')
        self.assertNotIn("מרחב", title)

    def test_title_drops_a_cross_reference_to_another_zone(self):
        """המשך הפריט של LLP13 מזכיר את 'הר הבית'. מילה שנשאבת משם
        הייתה מסווגת את האזור הלא נכון."""
        entries = parse_body([
            'יג. ,LLP13 האזור האסור "ירושלים:" מגובה פני הקרקע ועד גובה 4000 רגל',
            'מעל פני הים. ▪ בחלק החופף לאזור האסור "הר הבית" LLP11 תהיה ההגבלה',
        ])
        self.assertNotIn("הר הבית", entries["LLP13"]["title"])


class CoordinationTest(unittest.TestCase):
    def test_sentence_is_kept_verbatim(self):
        entries = parse_body(WITH_CONTACT)
        coordination = entries["LLP03"]["coordination"]
        self.assertTrue(coordination.startswith("לתיאום טיסה"))
        self.assertIn("050-3384198", coordination)

    def test_authority_is_the_named_body(self):
        entries = parse_body(WITH_CONTACT)
        self.assertEqual(entries["LLP03"]["authority"], 'מב"ט אבטחה מכון דוד')

    def test_company_representative(self):
        entries = parse_body(UAV_ITEMS)
        self.assertEqual(entries["LLU55"]["authority"], 'נציג חברת "שברון"')

    def test_no_coordination_is_none_not_empty(self):
        entries = parse_body(BALLOON)
        self.assertIsNone(entries["LLP42"]["coordination"])
        self.assertIsNone(entries["LLP42"]["authority"])

    def test_punctuation_returns_to_its_place(self):
        """ההיפוך הדו־כיווני מוציא את הנקודה לפני הטלפון. הטקסט נשמר
        כלשונו, אבל טלפון שנראה כמו ".050-3384198" נראה שבור."""
        entries = parse_body(WITH_CONTACT)
        self.assertIn("050-3384198.", entries["LLP03"]["coordination"])
        self.assertNotIn(".050", entries["LLP03"]["coordination"])

    def test_a_phone_without_a_body_yields_no_authority(self):
        """'יש ליצור קשר בטלפון 04-6975253' — יש תיאום, אין גורם.
        המצאת שם למי שהמסמך לא נקב בו הייתה שקר."""
        text = "לתיאום טיסה במרחב זה יש ליצור קשר בטלפון .04-6975253"
        self.assertIsNotNone(coordination_text(text))
        self.assertIsNone(authority_of(text))


if __name__ == "__main__":
    unittest.main()
