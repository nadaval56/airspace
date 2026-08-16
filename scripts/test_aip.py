"""בדיקות לפרסור נספחי הפמ"ת.

כל השורות כאן הועתקו מהפלט האמיתי של pdfplumber על א'-17 — כולל
ההיפוך של העברית. אין כאן דוגמאות מומצאות.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aip_annexes import (  # noqa: E402
    feature_extent,
    find_annex_pages,
    intersects_bbox,
    parse_annex_rows,
    parse_dms_pairs,
    radius_metres,
    reverse_hebrew,
)


class TestHebrewReversal(unittest.TestCase):
    def test_simple_name(self):
        self.assertEqual(reverse_hebrew("תיבה רה"), "הר הבית")
        self.assertEqual(reverse_hebrew("םילשורי"), "ירושלים")

    def test_digits_are_not_reversed(self):
        """תא שם שמשתרע על שתי שורות: '902' חייב להישאר 902, לא 209."""
        self.assertEqual(reverse_hebrew("שא חטש\n902"), "שטח אש 902")

    def test_blank_lines_dropped(self):
        self.assertEqual(reverse_hebrew("\n הלוחה \n\n"), "החולה")


class TestCoordinates(unittest.TestCase):
    def test_annex_b_row(self):
        pts = parse_dms_pairs("33° 07' 13.65\" N 35° 35' 13.44\" E")
        self.assertEqual(len(pts), 1)
        lon, lat = pts[0]
        self.assertAlmostEqual(lat, 33 + 7 / 60 + 13.65 / 3600, places=5)
        self.assertAlmostEqual(lon, 35 + 35 / 60 + 13.44 / 3600, places=5)

    def test_annex_c_row_without_spaces(self):
        pts = parse_dms_pairs("31°56'06\"N 34°52'50\"E")
        self.assertEqual(len(pts), 1)
        lon, lat = pts[0]
        self.assertAlmostEqual(lat, 31.935, places=3)
        self.assertAlmostEqual(lon, 34.880556, places=5)

    def test_jerusalem_sanity(self):
        """LLU07 ירושלים — נקודת ביקורת מול מיקום ידוע."""
        lon, lat = parse_dms_pairs("31°46'53\"N 35°13'24\"E")[0]
        self.assertAlmostEqual(lat, 31.781, places=2)
        self.assertAlmostEqual(lon, 35.223, places=2)

    def test_multiple_pairs_in_one_string(self):
        joined = "31°56'06\"N 34°52'50\"E 31°12'24\"N 34°48'37\"E"
        self.assertEqual(len(parse_dms_pairs(joined)), 2)

    def test_no_coordinates(self):
        self.assertEqual(parse_dms_pairs("GND 3000 הלוחה LLP01"), [])


class TestRadius(unittest.TestCase):
    def test_kilometres(self):
        self.assertEqual(radius_metres(':הדוקנב וזכרמו מ"ק 6 וסוידרש לגעמ'), 6000.0)

    def test_fractional_kilometres(self):
        self.assertEqual(radius_metres(':הדוקנב וזכרמו מ"ק 1.5 וסוידרש לגעמ'), 1500.0)

    def test_spelled_out_number(self):
        """'ק"מ אחד' — המספר מאוית במילה."""
        self.assertEqual(radius_metres(':הדוקנב וזכרמו דחא מ"ק וסוידרש לגעמ'), 1000.0)

    def test_spelled_half(self):
        self.assertEqual(radius_metres(':הדוקנב וזכרמו מ"ק יצח וסוידרש לגעמ'), 500.0)

    def test_metres_cell_from_annex_c(self):
        self.assertEqual(radius_metres("רטמ 1000"), 1000.0)

    def test_nautical_miles(self):
        self.assertEqual(radius_metres(':הדוקנב וזכרמו ימי ליימ 3 וסוידרש לגעמ'), 5556.0)

    def test_coordinates_are_not_read_as_radius(self):
        """ספרות של מעלות ודקות לא ייקראו כרדיוס — טעות שקטה ומסוכנת."""
        line = "31°56'06\"N 34°52'50\"E רטמ 1000"
        self.assertEqual(radius_metres(line), 1000.0)

    def test_no_unit_no_radius(self):
        self.assertIsNone(radius_metres("GND 3000"))

    def test_unit_without_number_is_rejected(self):
        self.assertIsNone(radius_metres("הריגסה סוידר"))


class TestAnnexRows(unittest.TestCase):
    """שורות טבלה כפי ש-extract_tables מחזיר אותן."""

    ANNEX_B = [
        [")Y( ןופצ", ")X( חרזמ", "", "הבוג", "", "", "הבוג\nיברמ", "רוזאה םש", "יוהיז דוק"],
        ["33° 07' 13.65\" N", "35° 35' 13.44\" E", "GND", "", "", "3000", "", "הלוחה", "LLP01"],
        ["33° 07' 05.65\" N", "35° 36' 43.44\" E", "", "", "", "", "", "", ""],
        ["33° 06' 35.65\" N", "35° 37' 30.44\" E", "", "", "", "", "", "", ""],
        ["32° 53' 47.65\" N", "35° 46' 29.46\" E", "GND", "", "", "3500", "", "אלמג", "LLP02"],
        ["32° 53' 16.65\" N", "35° 42' 43.46\" E", "", "", "", "", "", "", ""],
        ["32° 53' 50.65\" N", "35° 42' 29.46\" E", "", "", "", "", "", "", ""],
    ]

    def test_areas_split_by_designator_column(self):
        features, warnings = parse_annex_rows(self.ANNEX_B, "test")
        self.assertEqual([f["properties"]["id"] for f in features], ["LLP01", "LLP02"])
        self.assertEqual(warnings, [])

    def test_points_belong_to_their_own_area(self):
        """הבאג שהיה: נקודות של אזור אחד נספחו לקודמו ויצרו פוליגון ענק."""
        features, _ = parse_annex_rows(self.ANNEX_B, "test")
        for feature in features:
            width, height = feature_extent(feature)
            self.assertLess(width, 0.2, feature["properties"]["id"])
            self.assertLess(height, 0.2, feature["properties"]["id"])

    def test_names_and_altitudes(self):
        features, _ = parse_annex_rows(self.ANNEX_B, "test")
        first = features[0]["properties"]
        self.assertEqual(first["name"], "החולה")
        self.assertEqual(first["lower_limit"], "GND")
        self.assertEqual(first["upper_limit"], "3000")
        self.assertEqual(first["type"], "אסור")

    def test_ring_is_closed(self):
        features, _ = parse_annex_rows(self.ANNEX_B, "test")
        ring = features[0]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])

    def test_circle_row(self):
        """הגדרת העיגול יושבת באותה שורה של המזהה; המרכז בשורה שאחריה."""
        rows = [
            [':הדוקנב וזכרמו מ"ק 6 וסוידרש לגעמ', "", "GND", "", "", "4000", "", "", "םילשורי", "", "LLP13", "", ""],
            ["31° 47' 04.00\" N", "35° 12' 34.00\" E", "", "", "", "", "", "", "", "", "", "", ""],
        ]
        features, warnings = parse_annex_rows(rows, "test")
        self.assertEqual(warnings, [])
        self.assertEqual(len(features), 1)
        props = features[0]["properties"]
        self.assertEqual(props["id"], "LLP13")
        self.assertEqual(props["name"], "ירושלים")
        self.assertEqual(props["radius_m"], 6000.0)
        # עיגול של 6 ק"מ הוא כ-0.12° ברוחב
        width, height = feature_extent(features[0])
        self.assertAlmostEqual(width, 0.127, delta=0.02)

    def test_annex_c_row(self):
        rows = [[
            "31°56'06\"N", "34°52'50\"E", "רטמ 1000", "והישעמ-ןולייא", "LLU01",
        ]]
        features, warnings = parse_annex_rows(rows, "test")
        self.assertEqual(warnings, [])
        props = features[0]["properties"]
        self.assertEqual(props["id"], "LLU01")
        self.assertEqual(props["type"], "כטב\"ם")
        self.assertEqual(props["radius_m"], 1000.0)
        self.assertEqual(props["name"], "איילון-מעשיהו")
        # אין עמודות גובה בנספח ג' — הרדיוס לא ייקרא כגובה
        self.assertIsNone(props["lower_limit"])

    def test_single_point_without_radius_is_skipped(self):
        """מה שלא ברור מדווח ומדולג, לא מנוחש."""
        rows = [["31° 47' 04.00\" N", "35° 12' 34.00\" E", "GND", "4000", "םילשורי", "LLP99"]]
        features, warnings = parse_annex_rows(rows, "test")
        self.assertEqual(features, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("LLP99", warnings[0])

    def test_circle_without_numeric_radius_is_skipped(self):
        rows = [["הריגסה סוידר", "", "LLU58"], ["31°46'53\"N", "35°13'24\"E", ""]]
        features, warnings = parse_annex_rows(rows, "test")
        self.assertEqual(features, [])
        self.assertIn("LLU58", warnings[0])

    def test_rows_before_first_designator_are_ignored(self):
        rows = [["רוזאה םש", "יוהיז דוק"], ["33° 07' 13.65\" N", "35° 35' 13.44\" E"]]
        features, warnings = parse_annex_rows(rows, "test")
        self.assertEqual(features, [])
        self.assertEqual(warnings, [])

    def test_cross_reference_does_not_start_a_new_area(self):
        """'לאורך גבול LLP13' בתוך תיאור — התא אינו מזהה בפני עצמו."""
        rows = [
            ["33° 07' 13.65\" N", "35° 35' 13.44\" E", "GND", "3000", "הלוחה", "LLP01"],
            ["LLP13 לובג ךרואל תשקב תמדוקה הדוקנהמ", "", "", "", "", ""],
            ["33° 07' 05.65\" N", "35° 36' 43.44\" E", "", "", "", ""],
            ["33° 06' 35.65\" N", "35° 37' 30.44\" E", "", "", "", ""],
        ]
        features, _ = parse_annex_rows(rows, "test")
        self.assertEqual([f["properties"]["id"] for f in features], ["LLP01"])


class TestBbox(unittest.TestCase):
    def _feature(self, lon, lat):
        return {"geometry": {"coordinates": [[(lon, lat), (lon + 0.01, lat), (lon, lat + 0.01), (lon, lat)]]}}

    def test_binyamin(self):
        self.assertTrue(intersects_bbox(self._feature(35.2, 31.9)))

    def test_galilee_is_included_nationwide(self):
        self.assertTrue(intersects_bbox(self._feature(35.2, 33.0)))

    def test_eilat_is_included_nationwide(self):
        self.assertTrue(intersects_bbox(self._feature(34.95, 29.55)))

    def test_far_outside_country(self):
        self.assertFalse(intersects_bbox(self._feature(30.0, 31.9)))

    def test_touching_edge_is_kept(self):
        """אזור שנוגע בתיבה נשמר בשלמותו — לא מקצצים גיאומטריה."""
        self.assertTrue(intersects_bbox(self._feature(33.495, 31.9)))


class TestAnnexDetection(unittest.TestCase):
    def test_header_at_end_of_line(self):
        pages = [
            "הסיטל םינכוסמו םילבגומ ,םירוסא םירוזא תוטנידרואוק – *'ב חפסנ\nrows",
            'לקשמש ןסיטו ם"בטכל הסיטל םירוסא םירוזא תוטנידרואוק – *\'ג חפסנ',
        ]
        self.assertEqual(find_annex_pages(pages), {"b": (0, 1), "c": (1, 2)})

    def test_contents_page_is_not_an_annex(self):
        """עמוד עם כותרות של כמה נספחים הוא תוכן העניינים."""
        contents = (
            "הסיטל םינכוסמו םילבגומ ,םירוסא םירוזא תפמ - 'א חפסנ\n"
            "הסיטל םינכוסמו םילבגומ ,םירוסא םירוזא תוטאנידרואוק - *'ב חפסנ\n"
            "םיעובק םילושכמ - *'ד חפסנ"
        )
        real = "הסיטל םינכוסמו םילבגומ ,םירוסא םירוזא תוטנידרואוק – *'ב חפסנ"
        self.assertEqual(find_annex_pages([contents, real]), {"b": (1, 2)})

    def test_body_mention_is_not_a_header(self):
        """'כטבלת קואורדינטות בנספח ב'' בגוף הטקסט אינו כותרת."""
        body = ".הז קרפל 'ב חפסנב תוטאנידרואוק תלבטכו הז קרפל"
        self.assertEqual(find_annex_pages([body]), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
