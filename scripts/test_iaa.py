"""בדיקות לפרסור דפי רשות שדות התעופה.

ה-HTML כאן הועתק מהפלט האמיתי של האתר, כולל הרווחים הכבדים.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import iaa  # noqa: E402

# מבנה אמיתי מהדף החי. ה-`<tr>` עטוף ב-`divMainInfo_<msgNum>`, וממנו
# — ולא מ-`MoreImg_0` — נלקח מספר ההודעה: ה-onclick עושה `.substr(12)`
# על מזהה האב, ו-"divMainInfo_" הוא בדיוק 12 תווים.
ROW = '''
<div id="divMainInfo_2046996" style="display: inline;">
<table id="tblMainInfo_2046996" class="tblMainInfo">
<tr class="tblBody">
    <td class="ImgField">
        <img id="DataList1_MoreImg_0" onclick="javascript:f_getMoreInfo(this.parentNode.parentNode.parentNode.parentNode.parentNode.id.substr(12),&#39;more&#39;);" src="Images/plus.gif" />
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
</table>
</div>
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
        # מזהה ההודעה, לא האינדקס של השורה ב-DataList.
        self.assertEqual(rows[0]["msg_num"], "2046996")
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


class TestContinuationRows(unittest.TestCase):
    """הודעה ארוכה נשברת על פני שורות; רק לראשונה יש מזהה."""

    WRAPPED = '''
    <tr class="tblBody">
        <td class="NotamID">C1760/26</td>
        <td class="Location">LLLL</td>
        <td class="MsgText">AN AREA AT TLALIM WI 0.3NM RADIUS CENTERED ON PSN</td>
    </tr>
    <tr class="tblBody">
        <td class="NotamID">&nbsp;</td>
        <td class="Location">&nbsp;</td>
        <td class="MsgText">3055N03446E IS CLSD</td>
    </tr>
    '''

    def test_continuation_is_merged_not_dropped(self):
        rows = iaa.parse_notam_page(self.WRAPPED)
        self.assertEqual(len(rows), 1)
        self.assertIn("3055N03446E", rows[0]["text"])

    def test_coordinates_recovered_after_merge(self):
        """הבאג שהיה: שורות ההמשך סוננו, ואיתן נזרקו הקואורדינטות."""
        row = iaa.parse_notam_page(self.WRAPPED)[0]
        geo = iaa.extract_position(row["text"])
        self.assertIsNotNone(geo)
        self.assertAlmostEqual(geo["lat"], 30 + 55 / 60, places=4)
        self.assertEqual(geo["radius_nm"], 0.3)

    def test_weather_taf_across_rows(self):
        page = ('<tr class="tblBody"><td class="MsgType">TAF</td>'
                '<td class="weatherLocation">LLBG</td>'
                '<td class="MsgText">TAF BEN GURION, WIND 330 DEGREES, 7</td></tr>'
                '<tr class="tblBody"><td class="MsgType">&nbsp;</td>'
                '<td class="weatherLocation">&nbsp;</td>'
                '<td class="MsgText">KNOTS, VISIBILITY 10 KILOMETERS</td></tr>')
        reports = iaa.parse_weather_page(page)
        self.assertEqual(len(reports), 1)
        self.assertIn("KNOTS, VISIBILITY", reports[0]["text"])


class TestTruncation(unittest.TestCase):
    """שורה שאפשר להרחיב מסומנת, ואיתה מספר ההודעה לבקשה."""

    def test_row_with_expand_button(self):
        self.assertTrue(iaa.parse_rows(ROW)[0]["expandable"])

    def test_each_row_gets_its_own_message_number(self):
        """שתי שורות, שני עוטפים — כל שורה חייבת לקבל את המספר שלה
        ולא את זה של קודמתה."""
        page = ROW + ROW.replace("2046996", "2047001").replace("C1760/26", "C1761/26")
        rows = iaa.parse_rows(page)
        self.assertEqual([r["msg_num"] for r in rows], ["2046996", "2047001"])

    def test_row_without_expand_button(self):
        page = ('<tr class="tblBody"><td class="MsgType">METAR</td>'
                '<td class="weatherLocation">LLBG</td><td class="MsgText">SHORT</td></tr>')
        self.assertFalse(iaa.parse_rows(page)[0]["expandable"])

    def test_weather_report_carries_the_flag(self):
        self.assertIn("truncated", iaa.parse_weather_page(TestWeather.PAGE)[0])

    def test_complete_metar_is_not_flagged(self):
        """METAR מגיע שלם ומסתיים ב-'=' — אין לו המשך."""
        page = ('<tr class="tblBody"><td class="MsgType">METAR</td>'
                '<td class="weatherLocation">LLBG</td>'
                '<td class="MsgText">METAR LLBG 162120Z VRB03KT 9999 Q1010 NOSIG=</td></tr>')
        self.assertFalse(iaa.parse_weather_page(page)[0]["truncated"])


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
    """דף מזג האוויר משתמש בשמות מחלקות אחרים לאותם שדות."""

    PAGE = '''
    <tr class="tblBody">
        <td class="ImgField">&nbsp;</td>
        <td class="MsgType">TAF</td>
        <td class="weatherLocation">LLBG</td>
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

    def test_weather_cell_classes_differ_from_notam(self):
        """הבאג שהיה: המפרסר חיפש NotamID/Location, ודף מזג האוויר
        משתמש ב-MsgType/weatherLocation — ולכן החזיר אפס שורות."""
        rows = iaa.parse_rows(self.PAGE)
        self.assertEqual(rows[0]["id"], "TAF")
        self.assertEqual(rows[0]["location"], "LLBG")

    def test_rows_without_text_are_dropped(self):
        page = ('<tr class="tblBody"><td class="MsgType">X</td>'
                '<td class="weatherLocation">Y</td><td class="MsgText"></td></tr>')
        self.assertEqual(iaa.parse_weather_page(page), [])


class WeatherAreaTests(unittest.TestCase):
    """סעיף ה-WI של AIRMET/SIGMET — הגיאומטריה היחידה שיש למזג אוויר."""

    AIRMET = (
        "LLLL AIRMET 4 VALID 161900/162300 LLBD- LLLL TEL AVIV FIR MT OBSC "
        "FCST WI N3321 E03548 - N3257 E03555 - N3018 E03435 - N3042 E03426 "
        "- N3321 E03548 STNR INTSF="
    )

    def test_extracts_closed_ring(self):
        ring = iaa.extract_area(self.AIRMET)
        # ארבעה קודקודים ייחודיים, והטבעת נסגרת חזרה על הראשון.
        self.assertEqual(len(ring), 5)
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(ring[0], [35.8, 33.35])

    def test_stops_at_movement_word(self):
        """בלי העצירה ב-STNR/MOV, מספרי המשך היו נבלעים כקודקודים."""
        ring = iaa.extract_area(self.AIRMET + " N9999 E09999")
        self.assertEqual(len(ring), 5)

    def test_seconds_form(self):
        ring = iaa.extract_area(
            "SIGMET WI N332130 E0354830 - N330000 E0353000 - N301800 E0343500 MOV E="
        )
        self.assertEqual(len(ring), 4)
        self.assertAlmostEqual(ring[0][1], 33.358333, places=5)

    def test_metar_has_no_area(self):
        self.assertIsNone(iaa.extract_area(
            "METAR LLBG 162220Z VRB02KT 9999 SCT025 28/22 Q1009 NOSIG="))

    def test_two_points_are_not_an_area(self):
        """שתי נקודות אינן פוליגון. עדיף בלי אזור מאשר אזור מומצא."""
        self.assertIsNone(iaa.extract_area("AIRMET WI N3321 E03548 - N3257 E03555 STNR="))

    def test_report_carries_area(self):
        page = ('<tr class="tblBody"><td class="MsgType">AIRMET</td>'
                '<td class="weatherLocation">LLLL</td>'
                f'<td class="MsgText">{self.AIRMET}</td></tr>')
        report = iaa.parse_weather_page(page)[0]
        self.assertEqual(report["kind"], "AIRMET")
        self.assertEqual(len(report["area"]), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
