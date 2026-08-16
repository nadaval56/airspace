"""בדיקות לפרסור דפי רשות שדות התעופה.

ה-HTML כאן הועתק מהפלט האמיתי של האתר, כולל הרווחים הכבדים.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iaa  # noqa: E402

ROW = '''
<tr class="tblBody">
    <td class="ImgField">
        <img id="DataList1_MoreImg_0" onclick="javascript:f_getMoreInfo(this.id,&#39;more&#39;);" src="Images/plus.gif" />
    </td>
    <td class="NotamID">
        C1760/26
    </td>
    <td class="Location">
        LLLL
    </td>
    <td class="MsgText">
        E) AN AREA AT TLALIM WI 0.3NM RADIUS CENTERED ON PSN 3055N03446E IS CLSD
    </td>
</tr>
'''


class TestDecode(unittest.TestCase):
    def test_follows_meta_tag_not_http_header(self):
        raw = '<meta http-equiv="Content-Type" content="text/html; charset=windows-1255" />'.encode("cp1255")
        raw += "שלום".encode("cp1255")
        self.assertIn("שלום", iaa.decode(raw))

    def test_utf8_when_no_meta(self):
        self.assertIn("שלום", iaa.decode("<html>שלום".encode("utf-8")))


class TestRows(unittest.TestCase):
    def test_fields(self):
        rows = iaa.parse_rows(ROW)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "C1760/26")
        self.assertEqual(rows[0]["location"], "LLLL")
        self.assertEqual(rows[0]["msg_num"], "0")
        self.assertIn("TLALIM", rows[0]["text"])

    def test_whitespace_collapsed(self):
        self.assertNotIn("  ", iaa.parse_rows(ROW)[0]["text"])

    def test_empty_page(self):
        self.assertEqual(iaa.parse_rows("<html></html>"), [])


class TestPosition(unittest.TestCase):
    def test_extracts_psn_and_radius(self):
        geo = iaa.extract_position(iaa.parse_rows(ROW)[0]["text"])
        self.assertAlmostEqual(geo["lat"], 30 + 55 / 60, places=4)
        self.assertAlmostEqual(geo["lon"], 34 + 46 / 60, places=4)
        self.assertEqual(geo["radius_nm"], 0.3)
        self.assertFalse(geo["fir_wide"])

    def test_seconds_form(self):
        geo = iaa.extract_position("CENTERED ON PSN 315530N0351812E")
        self.assertAlmostEqual(geo["lat"], 31 + 55 / 60 + 30 / 3600, places=5)

    def test_no_coordinates_returns_none(self):
        """בלי קואורדינטה מפורשת אין ניחוש — הרשומה תופיע ברשימה בלבד."""
        self.assertIsNone(iaa.extract_position("RUNWAY 12/30 CLOSED"))

    def test_empty(self):
        self.assertIsNone(iaa.extract_position(""))


class TestRawNotam(unittest.TestCase):
    def test_builds_parsable_block(self):
        raw = iaa.to_raw_notam(iaa.parse_rows(ROW)[0])
        self.assertIn("C1760/26 NOTAMN", raw)
        self.assertIn("A) LLLL", raw)
        self.assertIn("E) AN AREA AT TLALIM", raw)

    def test_does_not_double_the_e_marker(self):
        raw = iaa.to_raw_notam({"id": "C1/26", "location": "LLLL", "text": "E) TEXT"})
        self.assertEqual(raw.count("E)"), 1)

    def test_adds_e_marker_when_missing(self):
        raw = iaa.to_raw_notam({"id": "C1/26", "location": "LLLL", "text": "TEXT"})
        self.assertIn("E) TEXT", raw)


class TestWeather(unittest.TestCase):
    PAGE = '''
    <tr class="tblBody">
        <td class="NotamID">TAF</td>
        <td class="Location">LLBG</td>
        <td class="MsgText">TAF BEN GURION, VALID FROM 161800 TILL 171800, WIND 330 DEGREES</td>
    </tr>
    '''

    def test_parses_report(self):
        reports = iaa.parse_weather_page(self.PAGE)
        self.assertEqual(len(reports), 1)
        report = reports[0]
        self.assertEqual(report["kind"], "TAF")
        self.assertEqual(report["station"], "LLBG")
        self.assertEqual(report["valid_from"], "161800")
        self.assertEqual(report["valid_to"], "171800")

    def test_rows_without_text_are_dropped(self):
        page = '<tr><td class="NotamID">X</td><td class="Location">Y</td><td class="MsgText"></td></tr>'
        self.assertEqual(iaa.parse_weather_page(page), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
