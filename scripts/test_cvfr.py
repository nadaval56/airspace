#!/usr/bin/env python3
"""בדיקות להמרת נתיבי ה-CVFR.

הממיר עוד לא רץ על הנתונים האמיתיים — ההורדה מ-data.gov.il מחזירה דף
אתגר, והארכיון מגיע דרך העלאה ידנית. לכן הלוגיקה נבדקת כאן על
shapefile סינתטי שנבנה בקוד: אם ההמרה שבורה, עדיף לגלות את זה עכשיו
ולא ברגע שהקובץ האמיתי סוף סוף יגיע.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build_cvfr_geojson as cvfr  # noqa: E402


# נקודות ב-Israel TM Grid. אלה מרכז הארץ בערך — לא חשוב המיקום המדויק,
# חשוב שההמרה תיתן קואורדינטות שנופלות על ישראל ולא באוקיינוס.
P1 = (200000.0, 650000.0)
P2 = (210000.0, 660000.0)
P3 = (220000.0, 670000.0)


def write_shapefile(directory: str, records: list) -> str:
    """בונה shapefile של קווים ומחזיר את נתיב ה-.shp."""
    import shapefile

    path = os.path.join(directory, "cvfr_mot")
    writer = shapefile.Writer(path, shapeType=shapefile.POLYLINE, encoding="utf-8")
    writer.field("NAME", "C", 40)
    writer.field("SEGMENT", "C", 40)
    writer.field("EMPTY", "C", 10)
    for name, segment, empty, parts in records:
        writer.line(parts)
        writer.record(name, segment, empty)
    writer.close()
    return path + ".shp"


class ConversionTest(unittest.TestCase):
    def build(self, records) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            return cvfr.build(write_shapefile(directory, records))

    def test_single_part_becomes_linestring(self):
        payload = self.build([("נתיב מערב", "A-B", "", [[P1, P2]])])
        self.assertEqual(len(payload["features"]), 1)
        geometry = payload["features"][0]["geometry"]
        self.assertEqual(geometry["type"], "LineString")
        self.assertEqual(len(geometry["coordinates"]), 2)

    def test_multi_part_becomes_multilinestring(self):
        payload = self.build([("נתיב שבור", "A-B", "", [[P1, P2], [P2, P3]])])
        geometry = payload["features"][0]["geometry"]
        self.assertEqual(geometry["type"], "MultiLineString")
        self.assertEqual(len(geometry["coordinates"]), 2)

    def test_coordinates_land_inside_israel(self):
        """ההמרה מ-ITM ל-WGS84 היא כל העניין — בלעדיה הקווים באוקיינוס."""
        payload = self.build([("נתיב", "A-B", "", [[P1, P2]])])
        for lon, lat in payload["features"][0]["geometry"]["coordinates"]:
            self.assertTrue(34.0 < lon < 36.0, f"קו אורך מחוץ לישראל: {lon}")
            self.assertTrue(29.0 < lat < 34.0, f"קו רוחב מחוץ לישראל: {lat}")

    def test_lonlat_order_not_swapped(self):
        """GeoJSON הוא lon,lat. החלפה שקטה מציבה את ישראל בסעודיה.

        בישראל קו האורך (~35) גדול מקו הרוחב (~32), ולכן הסדר הנכון
        ניכר מהערכים עצמם: אם האיבר הראשון קטן מהשני — הם התהפכו.
        """
        lon, lat = self.build(
            [("נתיב", "A-B", "", [[P1, P2]])]
        )["features"][0]["geometry"]["coordinates"][0]
        self.assertGreater(lon, lat, "נראה שהסדר התהפך — בישראל קו האורך גדול מקו הרוחב")

    def test_text_fields_kept_and_empty_dropped(self):
        properties = self.build(
            [("נתיב מערב", "A-B", "", [[P1, P2]])]
        )["features"][0]["properties"]
        self.assertEqual(properties["NAME"], "נתיב מערב")
        self.assertEqual(properties["SEGMENT"], "A-B")
        self.assertNotIn("EMPTY", properties)
        self.assertIn("source", properties)

    def test_degenerate_line_skipped_not_crashed(self):
        """קו של נקודה אחת אינו קו. מדלגים עליו ולא נופלים עליו."""
        payload = self.build([
            ("נקודה בודדת", "X", "", [[P1]]),
            ("נתיב תקין", "A-B", "", [[P1, P2]]),
        ])
        self.assertEqual(len(payload["features"]), 1)
        self.assertEqual(payload["features"][0]["properties"]["NAME"], "נתיב תקין")

    def test_precision_is_bounded(self):
        """שבע ספרות ≈ סנטימטר. זנב ארוך יותר הוא רעש מההמרה."""
        for lon, lat in self.build(
            [("נתיב", "A-B", "", [[P1, P2]])]
        )["features"][0]["geometry"]["coordinates"]:
            self.assertLessEqual(len(str(lon).split(".")[-1]), cvfr.PRECISION)
            self.assertLessEqual(len(str(lat).split(".")[-1]), cvfr.PRECISION)

    def test_metadata_present(self):
        payload = self.build([("נתיב", "A-B", "", [[P1, P2]])])
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertTrue(payload["generated_at"].endswith("Z"))
        self.assertIn("משרד התחבורה", payload["source"])


class GuardTest(unittest.TestCase):
    def test_non_archive_body_is_rejected(self):
        """דף האתגר של data.gov.il הוא HTML עם HTTP 200.

        בלי השער הזה הוא נופל עמוק בתוך zipfile ולא אומר מה קרה.
        """
        import io
        import urllib.request

        challenge = b"<html><head><script>f1xx" + b"x" * 40000

        class FakeResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        original = urllib.request.urlopen
        urllib.request.urlopen = lambda *a, **k: FakeResponse(challenge)
        try:
            with self.assertRaises(SystemExit) as caught:
                cvfr.fetch_zip(None)
        finally:
            urllib.request.urlopen = original
        self.assertIn("אינו ארכיון", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
