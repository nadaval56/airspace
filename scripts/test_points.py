"""בדיקות לחילוץ נקודות הדיווח ונקודות הייחוס."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import aip_points as ap  # noqa: E402

# שורה כפי שהיא יוצאת מה-PDF: קוד, קואורדינטות, סוג, ואז שם הפוך.
LINE = (
    "LLHZ 32° 10' 46\" N 34° 50' 04\" E ARP הילצרה "
    "OLGAH 32° 25' 53\" N 34° 51' 57\" E הבוח הגלוא"
)


class ParseTests(unittest.TestCase):
    def test_finds_both_points(self):
        self.assertEqual([p["code"] for p in ap.parse_points(LINE)], ["LLHZ", "OLGAH"])

    def test_aerodrome_position(self):
        point = ap.parse_points(LINE)[0]
        self.assertAlmostEqual(point["lat"], 32.17944, places=4)
        self.assertAlmostEqual(point["lon"], 34.83444, places=4)
        self.assertEqual(point["icao"], "LLHZ")
        self.assertEqual(point["kind"], "שדה תעופה")

    def test_reporting_point_has_no_icao(self):
        point = ap.parse_points(LINE)[1]
        self.assertIsNone(point["icao"])
        self.assertEqual(point["kind"], "דיווח חובה")

    def test_point_outside_israel_is_dropped(self):
        """קוד בן ארבע אותיות שנתפס באמצע מילה יכול לייצר נקודה בים."""
        self.assertEqual(ap.parse_points("ABCD 12° 00' 00\" N 03° 00' 00\" E"), [])

    def test_code_must_touch_its_coordinates(self):
        self.assertEqual(ap.parse_points("LLHZ ARP 32° 10' 46\" N 34° 50' 04\" E"), [])


class DedupeTests(unittest.TestCase):
    def test_one_entry_per_code(self):
        points = ap.parse_points(LINE) + ap.parse_points(LINE)
        self.assertEqual(len(ap.dedupe(points)), 2)

    def test_sorted_by_code(self):
        codes = [p["code"] for p in ap.dedupe(ap.parse_points(LINE))]
        self.assertEqual(codes, sorted(codes))


if __name__ == "__main__":
    unittest.main(verbosity=2)
