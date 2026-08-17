"""בדיקות יחידה לפרסור. הרצה: python3 -m unittest discover -s scripts -p 'test_*.py' -v"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from parse_qline import (  # noqa: E402
    QLineError,
    dedupe_and_resolve,
    parse_altitudes,
    parse_coord_field,
    parse_limit_item,
    extract_area,
    parse_notam,
    parse_notam_datetime,
    parse_q_line,
    sort_for_display,
    split_items,
)


class TestCoordField(unittest.TestCase):
    def test_spec_example(self):
        """הדוגמה מסעיף 5 במפרט: 31°55'N, 035°18'E, רדיוס 10 מייל ימי."""
        geo = parse_coord_field("3155N03518E010")
        self.assertAlmostEqual(geo["lat"], 31 + 55 / 60)
        self.assertAlmostEqual(geo["lon"], 35 + 18 / 60)
        self.assertEqual(geo["radius_nm"], 10)
        self.assertFalse(geo["fir_wide"])

    def test_fir_wide_radius(self):
        """רדיוס 999 = כל ה-FIR. חייב להיות מסומן כדי שלא יצויר עיגול ענק."""
        geo = parse_coord_field("3200N03500E999")
        self.assertTrue(geo["fir_wide"])
        self.assertEqual(geo["radius_nm"], 999)

    def test_zero_radius(self):
        geo = parse_coord_field("3155N03518E000")
        self.assertEqual(geo["radius_nm"], 0)
        self.assertFalse(geo["fir_wide"])

    def test_southern_western_hemisphere(self):
        geo = parse_coord_field("3330S07040W025")
        self.assertLess(geo["lat"], 0)
        self.assertLess(geo["lon"], 0)
        self.assertAlmostEqual(geo["lat"], -(33 + 30 / 60))
        self.assertAlmostEqual(geo["lon"], -(70 + 40 / 60))

    def test_malformed_raises(self):
        for bad in ("3155N03518E", "abc", "", "31555N03518E010", "3199N03518E010"):
            with self.assertRaises(QLineError, msg=bad):
                parse_coord_field(bad)


class TestAltitudes(unittest.TestCase):
    def test_unlimited_is_flagged(self):
        """000/999 = ללא הגבלת גובה, לא 0 עד 99,900 רגל."""
        alt = parse_altitudes("000", "999")
        self.assertTrue(alt["unlimited"])

    def test_regular_range_converts_hundreds_of_feet(self):
        alt = parse_altitudes("000", "030")
        self.assertFalse(alt["unlimited"])
        self.assertEqual(alt["lower_ft"], 0)
        self.assertEqual(alt["upper_ft"], 3000)

    def test_mid_level_range(self):
        alt = parse_altitudes("050", "120")
        self.assertEqual(alt["lower_ft"], 5000)
        self.assertEqual(alt["upper_ft"], 12000)

    def test_bad_input_raises(self):
        with self.assertRaises(QLineError):
            parse_altitudes("SFC", "999")


class TestQLine(unittest.TestCase):
    SPEC = "Q) LLLL/QRTCA/IV/NBO/W/000/999/3155N03518E010"

    def test_spec_example_full(self):
        q = parse_q_line(self.SPEC)
        self.assertEqual(q["fir"], "LLLL")
        self.assertEqual(q["q_code"], "QRTCA")
        self.assertEqual(q["subject_code"], "RT")
        self.assertEqual(q["condition_code"], "CA")
        self.assertEqual(q["traffic"], "IV")
        self.assertEqual(q["purpose"], "NBO")
        self.assertEqual(q["scope_code"], "W")
        self.assertEqual(q["scope"], "אזהרה למרחב")
        self.assertTrue(q["altitude"]["unlimited"])
        self.assertEqual(q["geo"]["radius_nm"], 10)

    def test_works_without_q_prefix(self):
        self.assertEqual(
            parse_q_line("LLLL/QRTCA/IV/NBO/W/000/999/3155N03518E010")["q_code"],
            "QRTCA",
        )

    def test_uav_notam_decodes_to_hebrew(self):
        q = parse_q_line("Q) LLLL/QWULW/IV/M/W/000/010/3157N03520E003")
        self.assertIn("כטב", q["subject"])
        self.assertEqual(q["altitude"]["upper_ft"], 1000)

    def test_unknown_code_falls_back_to_raw(self):
        q = parse_q_line("Q) LLLL/QZZZZ/IV/NBO/W/000/999/3155N03518E010")
        self.assertIsNone(q["subject"])
        self.assertEqual(q["subject_code"], "ZZ")

    def test_missing_fields_raise(self):
        with self.assertRaises(QLineError):
            parse_q_line("Q) LLLL/QRTCA/IV/NBO/W")

    def test_bad_qcode_raises(self):
        with self.assertRaises(QLineError):
            parse_q_line("Q) LLLL/XX/IV/NBO/W/000/999/3155N03518E010")


class TestLimitItems(unittest.TestCase):
    def test_surface(self):
        self.assertEqual(parse_limit_item("SFC")["feet"], 0)
        self.assertEqual(parse_limit_item("GND")["feet"], 0)

    def test_unlimited(self):
        limit = parse_limit_item("UNL")
        self.assertIsNone(limit["feet"])
        self.assertEqual(limit["reference"], "UNLIMITED")

    def test_flight_level(self):
        self.assertEqual(parse_limit_item("FL120")["feet"], 12000)

    def test_feet_amsl(self):
        limit = parse_limit_item("3000FT AMSL")
        self.assertEqual(limit["feet"], 3000)
        self.assertEqual(limit["reference"], "AMSL")

    def test_metres_converted(self):
        self.assertEqual(parse_limit_item("300M AGL")["feet"], 984)

    def test_empty(self):
        self.assertIsNone(parse_limit_item(None))
        self.assertIsNone(parse_limit_item("   "))


class TestDatetimes(unittest.TestCase):
    def test_basic_utc(self):
        dt = parse_notam_datetime("2608160600")
        self.assertEqual(dt["iso"], "2026-08-16T06:00:00Z")
        self.assertFalse(dt["permanent"])
        self.assertFalse(dt["estimated"])

    def test_perm(self):
        """PERM בשדה סיום = תוקף קבוע, לא תאריך."""
        dt = parse_notam_datetime("PERM")
        self.assertTrue(dt["permanent"])
        self.assertIsNone(dt["iso"])

    def test_est_suffix(self):
        dt = parse_notam_datetime("2612312359 EST")
        self.assertTrue(dt["estimated"])
        self.assertEqual(dt["iso"], "2026-12-31T23:59:00Z")

    def test_est_no_space(self):
        self.assertTrue(parse_notam_datetime("2612312359EST")["estimated"])

    def test_immediate(self):
        dt = parse_notam_datetime("WIE")
        self.assertIsNone(dt["iso"])

    def test_invalid_date_survives(self):
        dt = parse_notam_datetime("2699999999")
        self.assertIsNone(dt["iso"])


class TestSplitItems(unittest.TestCase):
    RAW = (
        "A0123/26 NOTAMN\n"
        "Q) LLLL/QRTCA/IV/NBO/W/000/030/3155N03518E010\n"
        "A) LLLL B) 2608160600 C) 2608161800\n"
        "D) DAILY 0600-1800\n"
        "E) TEMPORARY RESTRICTED AREA ACTIVATED. B) THIS IS NOT AN ITEM.\n"
        "F) SFC G) 3000FT AMSL"
    )

    def test_all_items_present(self):
        items = split_items(self.RAW)
        self.assertEqual(set(items), {"Q", "A", "B", "C", "D", "E", "F", "G"})

    def test_item_letter_inside_e_text_is_not_split(self):
        """'B)' בתוך טקסט של E) לא אמור לשבור את החיתוך."""
        items = split_items(self.RAW)
        self.assertIn("THIS IS NOT AN ITEM", items["E"])
        self.assertEqual(items["B"], "2608160600")

    def test_single_line_notam(self):
        items = split_items(
            "A1/26 NOTAMN Q) LLLL/QRTCA/IV/NBO/W/000/999/3155N03518E010 "
            "A) LLLL B) 2608160600 C) PERM E) TEXT HERE"
        )
        self.assertEqual(items["C"], "PERM")
        self.assertEqual(items["E"], "TEXT HERE")


class TestParseNotam(unittest.TestCase):
    RAW = TestSplitItems.RAW

    def test_full_record(self):
        rec = parse_notam(self.RAW, source="test")
        self.assertEqual(rec["id"], "A0123/26")
        self.assertEqual(rec["type"], "NOTAMN")
        self.assertEqual(rec["locations"], ["LLLL"])
        self.assertEqual(rec["valid_from"]["iso"], "2026-08-16T06:00:00Z")
        self.assertEqual(rec["schedule"], "DAILY 0600-1800")
        self.assertEqual(rec["geo"]["radius_nm"], 10)
        self.assertEqual(rec["parse_errors"], [])

    def test_f_item_wins_over_q_line_floor(self):
        rec = parse_notam(self.RAW)
        self.assertEqual(rec["lower_limit"]["feet"], 0)
        self.assertEqual(rec["floor_ft"], 0)
        self.assertTrue(rec["low_altitude"])

    def test_high_notam_not_marked_low(self):
        raw = (
            "A0200/26 NOTAMN Q) LLLL/QRTCA/IV/NBO/W/100/200/3155N03518E010 "
            "A) LLLL B) 2608160600 C) 2608161800 E) HIGH ALTITUDE ACTIVITY"
        )
        rec = parse_notam(raw)
        self.assertEqual(rec["floor_ft"], 10000)
        self.assertFalse(rec["low_altitude"])

    def test_missing_q_line_survives_with_null_geo(self):
        """שורת Q חסרה — הרשומה נשמרת ומגיעה לרשימה, לא נופלת."""
        raw = "A0300/26 NOTAMN A) LLBG B) 2608160600 C) PERM E) SOME ADMIN TEXT"
        rec = parse_notam(raw)
        self.assertIsNone(rec["geo"])
        self.assertEqual(rec["id"], "A0300/26")
        self.assertIn("שורת Q חסרה", rec["parse_errors"])

    def test_corrupt_q_line_survives_with_null_geo(self):
        raw = "A0301/26 NOTAMN Q) LLLL/GARBAGE A) LLLL B) 2608160600 E) TEXT"
        rec = parse_notam(raw)
        self.assertIsNone(rec["geo"])
        self.assertTrue(rec["parse_errors"])

    def test_completely_unparseable_does_not_raise(self):
        rec = parse_notam("!!! not a notam at all !!!")
        self.assertIsNone(rec["id"])
        self.assertIsNone(rec["geo"])

    def test_checklist_tagged_administrative(self):
        raw = (
            "A0400/26 NOTAMN Q) LLLL/QKKKK/K/K/K/000/999/3200N03500E999 "
            "A) LLLL B) 2608160600 C) 2608312359 E) CHECKLIST YEAR=2026 0123 0200"
        )
        rec = parse_notam(raw)
        self.assertTrue(rec["administrative"])

    def test_trigger_notam_tagged_administrative(self):
        raw = "A0401/26 NOTAMN A) LLLL B) 2608160600 E) TRIGGER NOTAM - AIRAC AIP AMDT"
        self.assertTrue(parse_notam(raw)["administrative"])

    def test_fir_wide_flagged(self):
        raw = (
            "A0500/26 NOTAMN Q) LLLL/QRTCA/IV/NBO/W/000/999/3200N03500E999 "
            "A) LLLL B) 2608160600 C) PERM E) APPLIES TO WHOLE FIR"
        )
        rec = parse_notam(raw)
        self.assertTrue(rec["geo"]["fir_wide"])

    def test_notamr_reference_captured(self):
        raw = (
            "A0600/26 NOTAMR A0599/26 Q) LLLL/QRTCA/IV/NBO/W/000/999/3155N03518E010 "
            "A) LLLL B) 2608160600 C) 2608161800 E) REPLACEMENT"
        )
        rec = parse_notam(raw)
        self.assertEqual(rec["type"], "NOTAMR")
        self.assertEqual(rec["replaces"], "A0599/26")


class TestDedupeAndResolve(unittest.TestCase):
    def _rec(self, nid, ntype="NOTAMN", ref=None, start="2608160600"):
        head = f"{nid} {ntype}" + (f" {ref}" if ref else "")
        return parse_notam(
            f"{head} Q) LLLL/QRTCA/IV/NBO/W/000/999/3155N03518E010 "
            f"A) LLLL B) {start} C) 2608161800 E) TEXT FOR {nid}"
        )

    def test_replaced_notam_not_shown_twice(self):
        records = [self._rec("A0599/26"), self._rec("A0600/26", "NOTAMR", "A0599/26")]
        live = dedupe_and_resolve(records)
        ids = {r["id"] for r in live}
        self.assertEqual(ids, {"A0600/26"})

    def test_cancelled_notam_removed_and_notice_tagged(self):
        records = [self._rec("A0700/26"), self._rec("A0701/26", "NOTAMC", "A0700/26")]
        live = dedupe_and_resolve(records)
        self.assertEqual({r["id"] for r in live}, {"A0701/26"})
        self.assertTrue(live[0]["administrative"])
        self.assertTrue(live[0]["cancellation"])

    def test_duplicate_id_from_two_sources_merged(self):
        a = self._rec("A0800/26")
        a["source"] = "fir"
        b = self._rec("A0800/26")
        b["source"] = "llbg"
        live = dedupe_and_resolve([a, b])
        self.assertEqual(len(live), 1)
        self.assertEqual(set(live[0]["source"].split("+")), {"fir", "llbg"})

    def test_richer_record_wins(self):
        poor = parse_notam("A0900/26 NOTAMN A) LLLL E) NO Q LINE")
        poor["source"] = "poor"
        rich = self._rec("A0900/26")
        rich["source"] = "rich"
        live = dedupe_and_resolve([poor, rich])
        self.assertIsNotNone(live[0]["geo"])

    def test_unidentified_records_kept(self):
        junk = parse_notam("garbage with no id")
        live = dedupe_and_resolve([self._rec("A1000/26"), junk])
        self.assertEqual(len(live), 2)

    def test_replacement_reference_to_absent_notam_is_harmless(self):
        live = dedupe_and_resolve([self._rec("A1100/26", "NOTAMR", "A0001/25")])
        self.assertEqual(len(live), 1)


class TestSorting(unittest.TestCase):
    def _rec(self, nid, start, admin=False):
        text = "CHECKLIST" if admin else "NORMAL TEXT"
        return parse_notam(
            f"{nid} NOTAMN Q) LLLL/QRTCA/IV/NBO/W/000/999/3155N03518E010 "
            f"A) LLLL B) {start} C) 2612312359 E) {text}"
        )

    def test_newest_first(self):
        records = [
            self._rec("A1/26", "2608100600"),
            self._rec("A2/26", "2608160600"),
            self._rec("A3/26", "2608130600"),
        ]
        ordered = sort_for_display(records)
        self.assertEqual([r["id"] for r in ordered], ["A2/26", "A3/26", "A1/26"])

    def test_administrative_sink_to_bottom(self):
        records = [
            self._rec("A1/26", "2608160600", admin=True),
            self._rec("A2/26", "2608100600"),
        ]
        ordered = sort_for_display(records)
        self.assertEqual([r["id"] for r in ordered], ["A2/26", "A1/26"])

    def test_administrative_still_ordered_among_themselves(self):
        records = [
            self._rec("A1/26", "2608100600", admin=True),
            self._rec("A2/26", "2608160600", admin=True),
        ]
        ordered = sort_for_display(records)
        self.assertEqual([r["id"] for r in ordered], ["A2/26", "A1/26"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ExtractAreaTest(unittest.TestCase):
    """גבול מפורש בגוף הנוטאם — האזור עצמו, לא מעטפת שמקיפה אותו."""

    def test_ddmmss_run_is_parsed(self):
        text = ("AN AREA AT GAZA-STRIP BTN FLW PSN CLSD TO ALL FLT "
                "310714N0341759E 310818N0343709E 310550N0344003E")
        area = extract_area(text)
        self.assertIsNotNone(area)
        # 31°07'14" = 31.120556 · 34°17'59" = 34.299722
        self.assertAlmostEqual(area[0][1], 31.120556, places=5)
        self.assertAlmostEqual(area[0][0], 34.299722, places=5)

    def test_lonlat_order_is_geojson(self):
        area = extract_area(
            "PSN 310714N0341759E 310818N0343709E 310550N0344003E")
        # בישראל קו האורך גדול מקו הרוחב; היפוך היה בולט מיד
        for lon, lat in area:
            self.assertGreater(lon, lat)

    def test_ring_is_closed(self):
        area = extract_area(
            "PSN 310714N0341759E 310818N0343709E 310550N0344003E")
        self.assertEqual(area[0], area[-1])

    def test_ddmm_short_form(self):
        area = extract_area("PSN 3107N03417E 3108N03437E 3105N03440E")
        self.assertIsNotNone(area)
        self.assertAlmostEqual(area[0][1], 31 + 7 / 60, places=5)

    def test_two_points_is_not_an_area(self):
        """שתי נקודות הן קו. מצולע דורש שלוש."""
        self.assertIsNone(
            extract_area("PSN 310714N0341759E 310818N0343709E"))

    def test_qline_coordinates_are_not_mistaken_for_an_area(self):
        """שדה 8 של שורת Q נגמר ברדיוס, ואסור לו להיקרא כקודקוד."""
        self.assertIsNone(extract_area(
            "Q) LLLL/QAELC/IV/NBO/E /000/019/3059N03445E001"))

    def test_plain_text_yields_nothing(self):
        self.assertIsNone(extract_area("ATS RTE Q30 CLSD BTN BEXOM-NURIT."))
        self.assertIsNone(extract_area(None))

    def test_parse_notam_attaches_area(self):
        raw = ("(C1575/26 NOTAMN Q) LLLL/QRTCA/IV/BO/W /000/100/3120N03430E030 "
               "A) LLLL B) 2607261511 C) 2608312059 "
               "E) AN AREA CLSD 310714N0341759E 310818N0343709E 310550N0344003E)")
        record = parse_notam(raw)
        self.assertIsNotNone(record["area"])
        self.assertEqual(len(record["area"]), 4)   # שלוש נקודות + סגירה
