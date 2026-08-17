#!/usr/bin/env python3
"""בדיקות לפרסור פרקי השדות, המנחתים ומשטחי המסוקים.

כל השורות כאן הן שורות **אמיתיות** מהפמ"ת, אחרי היישור של
`aip_annexes.reverse_hebrew`. הבדיקות המעניינות הן אלה שנועלות את
המקרים שהמקור עצמו מקלקל: סימן מעלות מגופן סימבולי, אות כיוון לפני
המספר, גובה שההיפוך פירק לשניים, ורדיוס אפס.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aip_aerodromes as fields  # noqa: E402

DEG = ""   # סימן המעלות כפי שהוא יוצא מ-14 מהפרקים
SEC = ""   # תו השניות מאותו גופן


class CoordinateTest(unittest.TestCase):
    def test_plain_degree_sign(self):
        """ראש פינה — הצורה ה"נורמלית", עם '°' אמיתי."""
        line = 'ברשת :WGS-84 035°34\'19"E 32°58\'51"N'
        self.assertEqual(fields.parse_dms_pair(line), (32.98083, 35.57194))

    def test_symbol_font_degree_sign(self):
        """חיפה — המעלות והשניות בתווים מהאזור הפרטי של יוניקוד.

        בלי המיפוי השורה נראית כמו '03502'38E' ואי אפשר לדעת איפה
        נגמרות המעלות. זו הבדיקה שנועלת את הבאג המסוכן ביותר כאן.
        """
        line = f"ברשת :WGS-84 035{DEG}02'38{SEC}E 32{DEG}48'35{SEC}N"
        self.assertEqual(fields.parse_dms_pair(line), (32.80972, 35.04389))

    def test_hemisphere_before_the_number(self):
        """קציעות — 'E034˚26'36'' N30˚51'33''', הפוך מכל השאר."""
        line = "ברשת :WGS84 E034˚26'36'' N30˚51'33''"
        self.assertEqual(fields.parse_dms_pair(line), (30.85917, 34.44333))

    def test_decimal_seconds(self):
        """משטח המסוקים בראשון לציון — שניות עשרוניות."""
        line = "ברשת :WGS-84 034˚45'07.92''E 31˚58'02.2''N"
        self.assertEqual(fields.parse_dms_pair(line), (31.96728, 34.7522))

    def test_east_before_north_does_not_swap(self):
        """בפרקים המזרח כתוב לפני הצפון. קריאה לפי מקום הייתה מחליפה."""
        lat, lon = fields.parse_dms_pair('ברשת 1984 :WGS 034°43\'22"E 31°17\'13"N')
        self.assertAlmostEqual(lat, 31.28694, places=5)
        self.assertAlmostEqual(lon, 34.72278, places=5)

    def test_wgs_is_not_read_as_south(self):
        """ה-S של WGS אינו חצי כדור, וגם אינו בולע את '03' של האורך."""
        pair = fields.parse_dms_pair('ברשת 1984 :WGS 035°12\'11"E 30°37\'18"N')
        self.assertEqual(pair, (30.62167, 35.20306))

    def test_line_without_coordinates(self):
        self.assertIsNone(fields.parse_dms_pair(".2 מיקום המנחת"))

    def test_compact_pair_from_the_agricultural_table(self):
        """'323208/0352618' — DDMMSS/DDDMMSS, בלי שום מפריד."""
        self.assertEqual(fields.parse_compact_pair("323208/0352618"), (32.53556, 35.43833))
        self.assertEqual(fields.parse_compact_pair("311339/0342737"), (31.22750, 34.46028))


class TitleTest(unittest.TestCase):
    """הסוגריים בכותרות — התהפכו בהיפוך הדו־כיווני, וכאן הם חוזרים."""

    def test_mirrored_brackets_are_flipped_back(self):
        self.assertEqual(
            fields._clean_title("נמל התעופה חיפה )LLHA("), "נמל התעופה חיפה"
        )

    def test_code_leaves_no_dangling_bracket(self):
        """אסותא: ")LLAA)" — שני סוגרים סוגרים, בלי פותח בכלל."""
        self.assertEqual(
            fields._clean_title("מנחת מסוקים אסותא אשדוד )LLAA)"),
            "מנחת מסוקים אסותא אשדוד",
        )

    def test_a_second_name_in_brackets_survives(self):
        """תפן: הקוד יושב בתוך הסוגריים של השם השני, והם נסגרים."""
        self.assertEqual(
            fields._clean_title("מנחת מסוקים תפן (ישקר – )LLIS"),
            "מנחת מסוקים תפן (ישקר)",
        )

    def test_code_without_brackets(self):
        self.assertEqual(fields._clean_title("מנחת קציעות - LLKZ"), "מנחת קציעות")

    def test_empty_brackets_from_a_symbol_font(self):
        self.assertEqual(fields._clean_title("מנחת עין שמר ( )"), "מנחת עין שמר")


class ElevationTest(unittest.TestCase):
    def test_single_run_is_read(self):
        lines = [".3 גובה השדה", "884 רגל מעל פני הים."]
        self.assertEqual(fields.text_elevation(lines), (884, False))

    def test_below_sea_level(self):
        lines = [".3 גובה המנחת", "177 )-( רגל (מתחת לפני הים.)"]
        self.assertEqual(fields.text_elevation(lines), (-177, False))

    def test_thousands_separator_inside_one_token_is_fine(self):
        lines = [".3 גובה המנחת", "א. מנחת קרקעי: 2,088 רגל."]
        self.assertEqual(fields.text_elevation(lines), (2088, False))

    def test_two_runs_are_ambiguous_and_not_guessed(self):
        """מצדה: '233 1' הוא 1,233 שההיפוך פירק. הסדר אבד, ולא ננחש."""
        feet, ambiguous = fields.text_elevation(
            [".3 גובה המנחת", "233 1 )-( רגל (מתחת לפני הים.)"]
        )
        self.assertIsNone(feet)
        self.assertTrue(ambiguous)

    def test_label_picks_the_right_surface(self):
        """להדסה שני משטחים, והגבהים מפורטים תחת כותרת אחת."""
        lines = [
            ".3 גובה המנחת",
            "א. מנחת קרקעי: 2,088 רגל.",
            "ב. מנחת מוגבה: 2,379 רגל.",
        ]
        self.assertEqual(fields.text_elevation(lines, "מנחת קרקעי")[0], 2088)
        self.assertEqual(
            fields.text_elevation(lines, "מנחת מוגבה על גג בניין")[0], 2379
        )

    def test_chart_elevation_in_both_directions(self):
        self.assertEqual(fields.chart_elevation(["ft 884 ELEV AD"]), 884)
        self.assertEqual(fields.chart_elevation(["ELEV 1218 ft"]), 1218)
        self.assertEqual(fields.chart_elevation(["ft (-)177 ELEV CHART"]), -177)

    def test_chart_elevation_ignores_a_split_number(self):
        """גם התרשים סובל מההיפוך: 'ft 233 (-)1 ELEV' אינו נקרא."""
        self.assertIsNone(fields.chart_elevation(["ft 233 (-)1 ELEV AD 31°19’45”N"]))

    def test_chart_elevation_ignores_a_legend_line(self):
        self.assertIsNone(fields.chart_elevation(["FEET IN ALT ELEV,"]))


class AtzTest(unittest.TestCase):
    def test_canonical_phrasing(self):
        line = "א. אזור השדה של המנחת מתוחם ברדיוס 3 ק\"מ מנקודת הציון"
        radius, warning = fields.atz_radius_nm([line])
        self.assertEqual(radius, 1.62)
        self.assertIsNone(warning)

    def test_zero_radius_is_reported_not_drawn(self):
        """קציעות: 'מתוחם ברדיוס 0 מייל ימי'. אפס אינו רדיוס."""
        radius, warning = fields.atz_radius_nm(
            ["א. אזור השדה של המנחת מתוחם ברדיוס 0 מייל ימי מנקודת הציון"]
        )
        self.assertIsNone(radius)
        self.assertIsNotNone(warning)

    def test_other_radii_in_the_chapter_are_not_the_field_area(self):
        """ריבוי מכשולים ופעילות מורשית מוגדרים גם הם ברדיוס — ואינם ATZ."""
        for line in (
            "יג. תשומת לב נדרשת לריבוי מכשולים ברדיוס של 1.5 מייל ימי ממרכז",
            "בזמן אמת עם מגדל קדם. פעילות זו מורשית ברדיוס של 5 ק\"מ ממרכז",
            "כחצי מעגל מצפון לנ.צ ברדיוס 3 ק\"מ וקטום",
        ):
            self.assertEqual(fields.atz_radius_nm([line]), (None, None), line)


class StructureTest(unittest.TestCase):
    def test_volume_headings(self):
        self.assertEqual(fields.volume_of("פרק ד' – שדות תעופה"), "airport")
        self.assertEqual(fields.volume_of("פרק ה' – מנחתים"), "airstrip")
        self.assertEqual(
            fields.volume_of("פרק ו' – משטחי נחיתה למסוקים"), "helipad"
        )
        self.assertIsNone(fields.volume_of("פרק א-17 – אזורים אסורים"))

    def test_running_head_forms(self):
        """ההיפוך מזיז את המספר והמקף, ולכן אותה כותרת בחמש צורות."""
        cases = {
            'פמ"ת פנים ארצי ראש פינה - 3': "ראש פינה",
            'ראש פינה - 2 פמ"ת פנים ארצי': "ראש פינה",
            'עין שמר 2- פמ"ת פנים ארצי': "עין שמר",
            'פמ"ת פנים ארצי עין שמר -': "עין שמר",
            'פמ"ת פנים ארצי פוריה- 1': "פוריה",
            'פמ"ת פנים ארצי אסותא-אשדוד 1-': "אסותא-אשדוד",
            'פמ"ת פנים ארצי תפן (ישקר) - 1': "תפן (ישקר)",
        }
        for line, expected in cases.items():
            self.assertEqual(fields.running_head(line), expected, line)

    def test_running_head_ignores_other_lines(self):
        for line in (".9 נתוני המסלולים", 'פמ"ת פנים ארצי', "ELEV 884 ft"):
            self.assertIsNone(fields.running_head(line), line)


class ChapterTest(unittest.TestCase):
    """פרק שלם, מקוצר — הכותרת, הנ"צ והגובה כפי שהם בעמוד הראשון."""

    ROSH_PINA = [
        'פמ"ת פנים ארצי ראש פינה - 1',
        "שדה התעופה ראש פינה )LLIB(",
        ".1 נקודת ציון מרכזית",
        'ברשת :WGS-84 035°34\'19"E 32°58\'51"N',
        ".2 מיקום השדה",
        "10 ק\"מ צפונית לכנרת, צמוד לקיבוץ מחניים.",
        ".3 גובה השדה",
        "884 רגל מעל פני הים.",
    ]

    def test_single_surface(self):
        records, warnings = fields.parse_field(
            "ראש פינה", self.ROSH_PINA, "airport", [268]
        )
        self.assertEqual(warnings, [])
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["icao"], "LLIB")
        self.assertEqual(record["kind"], "airport")
        self.assertEqual(record["elevation_ft"], 884)
        self.assertEqual((record["lat"], record["lon"]), (32.98083, 35.57194))
        self.assertIsNone(record["surface"])

    def test_two_surfaces_in_one_chapter(self):
        """ראשון לציון: מסלול מטוסים, ובנוסף משטח מסוקים עם נ"צ משלו.

        המשטח השני מקבל סוג `helipad` — כי כך **כתוב** בכותרת שלו, גם
        אם הפרק כולו יושב תחת "מנחתים".
        """
        lines = [
            "מנחת ראשון לציון )LLRS(",
            "א. מנחת מז\"מ",
            ".1 נקודת ציון מרכזית )ARP(",
            "ברשת :WGS-84 034˚45'13''E 31˚58'03''N",
            ".3 גובה המנחת",
            "60 רגל.",
            "ב. משטח הנחיתה - מסוקים",
            ".1 נקודת ציון מרכזית )ARP(",
            "ברשת :WGS-84 034˚45'07.92''E 31˚58'02.2''N",
            ".3 גובה המנחת",
            "60 רגל.",
        ]
        records, _ = fields.parse_field("ראשון לציון", lines, "airstrip", [377])
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["kind"], "airstrip")
        self.assertEqual(records[1]["kind"], "helipad")
        self.assertIn("מסוקים", records[1]["name"])
        self.assertNotEqual(records[0]["lon"], records[1]["lon"])

    def test_a_second_surface_too_far_away_is_not_drawn(self):
        """הדסה: הגג יושב במקור 1.4 ק"מ מהמשטח הקרקעי, בשטח אורה.

        שני משטחים של אותו בית חולים אינם רחוקים קילומטר וחצי, ולכן
        אחד המספרים שגוי — ואי אפשר לדעת איזה. מסומן הראשון בלבד,
        והחוסר נאמר גם באזהרה וגם בהערה שנשמרת על הנקודה.
        """
        lines = [
            "מנחת מסוקים הדסה עין כרם (LLHD)",
            ".1 נקודת התייחסות המנחת (HRP)",
            "א. מנחת קרקעי, ברשת 1984 :WGS 035°08'50\"E 31°45'52\"N",
            "ב. מנחת מוגבה על גג בניין, ברשת 1984 :WGS 035°08'57\"E 31°45'08\"N",
            ".3 גובה המנחת",
            "א. מנחת קרקעי: 2,088 רגל.",
            "ב. מנחת מוגבה: 2,379 רגל.",
        ]
        records, warnings = fields.parse_field(
            "הדסה עין כרם", lines, "helipad", [414]
        )
        self.assertEqual(len(records), 1)
        self.assertIn("קרקעי", records[0]["name"])
        self.assertTrue(records[0]["note"])
        self.assertTrue(any("רחוק" in w for w in warnings), warnings)

    def test_two_surfaces_on_the_same_site_are_both_drawn(self):
        """ראשון לציון: 135 מטר בין המסלול למשטח. אותו מתקן, שתי נקודות."""
        lines = [
            "מנחת ראשון לציון )LLRS(",
            "א. מנחת מז\"מ",
            "ברשת :WGS-84 034˚45'13''E 31˚58'03''N",
            "ב. משטח הנחיתה - מסוקים",
            "ברשת :WGS-84 034˚45'07.92''E 31˚58'02.2''N",
        ]
        records, warnings = fields.parse_field("ראשון לציון", lines, "airstrip", [377])
        self.assertEqual(len(records), 2)
        self.assertEqual(warnings, [])

    def test_chart_overrides_a_mangled_text_elevation(self):
        """קציעות: במלל 'כ- 099 רגל', בתרשים 'ELEV 900 ft'."""
        lines = [
            "מנחת קציעות - LLKZ",
            ".1 נקודת ציון מרכזית )ARP(",
            "ברשת :WGS84 E034˚26'36'' N30˚51'33''",
            ".3 גובה המנחת",
            "כ- 099 רגל מעפ\"י.",
        ]
        records, warnings = fields.parse_field(
            "קציעות", lines, "airstrip", [364], chart_lines=["(LLKZ) KZIOTH ft 900 ELEV"]
        )
        self.assertEqual(records[0]["elevation_ft"], 900)
        self.assertTrue(any("בתרשים" in w for w in warnings), warnings)

    def test_chapter_without_coordinates_yields_nothing(self):
        records, _ = fields.parse_field("שדה", [".3 גובה השדה", "100 רגל."], "airport", [1])
        self.assertEqual(records, [])


class AgriculturalTest(unittest.TestCase):
    """טבלת "מנחתים נוספים" — שורות אמיתיות, אחרי יישור לפי תא."""

    HEADER = [')ARP( נ"צ מרכזי', "פרטי יצירת קשר", "מנחת מפעילי", "מנחת שם"]

    def test_columns_are_read_from_the_header(self):
        rows = [
            self.HEADER,
            ["323208/0352618", "ops@chimnir.co.il", "חברת כים- ניר אחזקות", "אליעז (חפציבה)"],
        ]
        parsed, warnings = fields.parse_agricultural(rows)
        self.assertEqual(warnings, [])
        self.assertEqual(len(parsed), 1)
        field = parsed[0]
        self.assertEqual(field["name"], "אליעז (חפציבה)")
        self.assertEqual(field["operator"], "חברת כים- ניר אחזקות")
        self.assertEqual(field["contact"], "ops@chimnir.co.il")
        self.assertEqual(field["kind"], "agricultural")
        self.assertEqual((field["lat"], field["lon"]), (32.53556, 35.43833))

    def test_leading_parenthetical_moves_to_the_end(self):
        rows = [self.HEADER, ["311339/0342737", "", "", "(אשכול) גבולות"]]
        parsed, _ = fields.parse_agricultural(rows)
        self.assertEqual(parsed[0]["name"], "גבולות (אשכול)")

    def test_email_broken_across_lines_is_rejoined(self):
        rows = [
            self.HEADER,
            ["314152/0344610", "tomer.dahari@elbits ystems.com", "סנונית בע\"מ", "קדמה"],
        ]
        parsed, _ = fields.parse_agricultural(rows)
        self.assertEqual(parsed[0]["contact"], "tomer.dahari@elbitsystems.com")

    def test_two_glued_addresses_are_not_published(self):
        """'ops@chimnir.co.iletzionia@gmail.com' — שתי כתובות שנדבקו."""
        rows = [
            self.HEADER,
            ["330652/0353452", "ops@chimnir.co.ilet zionia@gmail.com", "חברת תלם", "רשות החולה"],
        ]
        parsed, _ = fields.parse_agricultural(rows)
        self.assertIsNone(parsed[0]["contact"])
        self.assertEqual(parsed[0]["name"], "רשות החולה")

    def test_rows_without_coordinates_are_skipped(self):
        rows = [self.HEADER, ["", "", "", "מנחת בלי נ\"צ"]]
        parsed, warnings = fields.parse_agricultural(rows)
        self.assertEqual(parsed, [])
        self.assertTrue(warnings)   # הטבלה לא הניבה כלום — נאמר בקול

    def test_missing_header_is_reported(self):
        parsed, warnings = fields.parse_agricultural([["323208/0352618", "x"]])
        self.assertEqual(parsed, [])
        self.assertTrue(any("הכותרת" in w for w in warnings), warnings)


class LiveDataTest(unittest.TestCase):
    """הקובץ שבמאגר — מה שהדף באמת טוען."""

    @classmethod
    def setUpClass(cls):
        import json

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "aip-aerodromes.geojson",
        )
        with open(path, encoding="utf-8") as fh:
            cls.data = json.load(fh)

    def test_every_feature_is_a_point_inside_israel(self):
        for feature in self.data["features"]:
            lon, lat = feature["geometry"]["coordinates"]
            self.assertEqual(feature["geometry"]["type"], "Point")
            self.assertTrue(
                fields.in_israel(lat, lon), feature["properties"]["id"]
            )

    def test_ids_are_unique(self):
        ids = [f["properties"]["id"] for f in self.data["features"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_kind_has_a_label(self):
        for feature in self.data["features"]:
            kind = feature["properties"]["kind"]
            self.assertIn(kind, fields.VOLUME_LABELS)
            self.assertEqual(
                feature["properties"]["kind_label"], fields.VOLUME_LABELS[kind]
            )

    def test_the_three_airports_are_there(self):
        """פרק ד' מונה שלושה, וכולם חייבים להיות בקובץ."""
        airports = {
            f["properties"]["icao"]
            for f in self.data["features"]
            if f["properties"]["kind"] == "airport"
        }
        self.assertEqual(airports, {"LLHZ", "LLHA", "LLIB"})

    def test_no_label_carries_a_mirrored_bracket(self):
        """סוגר סוגר שפותח מחרוזת הוא סימן ההיפוך. אין כזה בקובץ."""
        import re

        for feature in self.data["features"]:
            for key in ("name", "title"):
                value = feature["properties"].get(key)
                if value:
                    self.assertIsNone(
                        re.search(r"\)[^()]*\(", value),
                        f"{feature['properties']['id']} · {key}: {value}",
                    )

    def test_elevations_are_plausible(self):
        """מהשפל (-1,300) ועד הרמה (3,000). מספר הפוך יוצא מהטווח."""
        for feature in self.data["features"]:
            feet = feature["properties"].get("elevation_ft")
            if feet is None:
                continue
            self.assertGreaterEqual(feet, -1300, feature["properties"]["id"])
            self.assertLessEqual(feet, 3000, feature["properties"]["id"])


if __name__ == "__main__":
    unittest.main()
