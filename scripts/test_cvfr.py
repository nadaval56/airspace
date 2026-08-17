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


def ring(points: list, clockwise: bool) -> list:
    """טבעת סגורה בכיוון מבוקש. כיוון השעון = חיצונית, נגדו = חור."""
    closed = list(points) + [points[0]]
    return closed if clockwise else list(reversed(closed))


# ריבוע חיצוני וריבוע קטן בתוכו, ב-Israel TM Grid.
OUTER = [(200000.0, 650000.0), (200000.0, 660000.0),
         (210000.0, 660000.0), (210000.0, 650000.0)]
HOLE = [(203000.0, 653000.0), (203000.0, 657000.0),
        (207000.0, 657000.0), (207000.0, 653000.0)]
FAR = [(220000.0, 670000.0), (220000.0, 675000.0),
       (225000.0, 675000.0), (225000.0, 670000.0)]


def write_shapefile(directory: str, records: list, shape_type=None) -> str:
    """בונה shapefile של פוליגונים ומחזיר את נתיב ה-.shp."""
    import shapefile

    path = os.path.join(directory, "cvfr_mot")
    writer = shapefile.Writer(
        path, shapeType=shape_type or shapefile.POLYGON, encoding="utf-8"
    )
    writer.field("NAME", "C", 40)
    writer.field("SEGMENT", "C", 40)
    writer.field("EMPTY", "C", 10)
    for name, segment, empty, parts in records:
        if shape_type == shapefile.POLYLINE:
            writer.line(parts)
        else:
            writer.poly(parts)
        writer.record(name, segment, empty)
    writer.close()
    return path + ".shp"


class ConversionTest(unittest.TestCase):
    def build(self, records) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            return cvfr.build(write_shapefile(directory, records))

    def coords(self, payload):
        """כל הקודקודים שבתוצאה, בלי קשר למבנה."""
        geometry = payload["features"][0]["geometry"]
        polys = ([geometry["coordinates"]] if geometry["type"] == "Polygon"
                 else geometry["coordinates"])
        return [point for poly in polys for ring in poly for point in ring]

    def test_simple_ring_becomes_polygon(self):
        payload = self.build([("פרוזדור", "A-B", "", [ring(OUTER, True)])])
        self.assertEqual(len(payload["features"]), 1)
        geometry = payload["features"][0]["geometry"]
        self.assertEqual(geometry["type"], "Polygon")
        self.assertEqual(len(geometry["coordinates"]), 1)

    def test_hole_is_kept_as_interior_ring(self):
        """הלב של התיקון. חור שנקרא כטבעת חיצונית מנפח את השטח."""
        payload = self.build([
            ("פרוזדור עם חור", "A-B", "", [ring(OUTER, True), ring(HOLE, False)])
        ])
        geometry = payload["features"][0]["geometry"]
        self.assertEqual(geometry["type"], "Polygon")
        self.assertEqual(len(geometry["coordinates"]), 2,
                         "החור לא נשמר כטבעת פנימית")

    def test_hole_shrinks_the_area(self):
        """אימות מספרי, לא מבני: החור באמת מוריד שטח."""
        without = cvfr.ring_area(self.build(
            [("שלם", "A", "", [ring(OUTER, True)])]
        )["features"][0]["geometry"]["coordinates"][0])
        rings = self.build([
            ("עם חור", "A", "", [ring(OUTER, True), ring(HOLE, False)])
        ])["features"][0]["geometry"]["coordinates"]
        net = abs(cvfr.ring_area(rings[0])) - abs(cvfr.ring_area(rings[1]))
        self.assertLess(net, abs(without))
        self.assertGreater(net, 0)

    def test_two_outer_rings_become_multipolygon(self):
        payload = self.build([
            ("שני פרוזדורים", "A", "", [ring(OUTER, True), ring(FAR, True)])
        ])
        self.assertEqual(payload["features"][0]["geometry"]["type"], "MultiPolygon")
        self.assertEqual(len(payload["features"][0]["geometry"]["coordinates"]), 2)

    def test_rings_are_closed(self):
        for poly in [self.build([("פרוזדור", "A", "", [ring(OUTER, True)])])
                     ["features"][0]["geometry"]["coordinates"]]:
            for r in poly:
                self.assertEqual(r[0], r[-1], "טבעת שאינה סגורה אינה פוליגון תקין")

    def test_coordinates_land_inside_israel(self):
        """ההמרה מ-ITM ל-WGS84 היא כל העניין — בלעדיה הצורות באוקיינוס."""
        for lon, lat in self.coords(self.build([("פרוזדור", "A", "", [ring(OUTER, True)])])):
            self.assertTrue(34.0 < lon < 36.0, f"קו אורך מחוץ לישראל: {lon}")
            self.assertTrue(29.0 < lat < 34.0, f"קו רוחב מחוץ לישראל: {lat}")

    def test_lonlat_order_not_swapped(self):
        """GeoJSON הוא lon,lat. החלפה שקטה מציבה את ישראל בסעודיה.

        בישראל קו האורך (~35) גדול מקו הרוחב (~32), ולכן הסדר הנכון
        ניכר מהערכים עצמם: אם האיבר הראשון קטן מהשני — הם התהפכו.
        """
        lon, lat = self.coords(self.build([("פרוזדור", "A", "", [ring(OUTER, True)])]))[0]
        self.assertGreater(lon, lat, "נראה שהסדר התהפך — בישראל קו האורך גדול מקו הרוחב")

    def test_text_fields_kept_and_empty_dropped(self):
        properties = self.build(
            [("פרוזדור מערב", "A-B", "", [ring(OUTER, True)])]
        )["features"][0]["properties"]
        self.assertEqual(properties["NAME"], "פרוזדור מערב")
        self.assertEqual(properties["SEGMENT"], "A-B")
        self.assertNotIn("EMPTY", properties)
        self.assertIn("source", properties)

    def test_degenerate_ring_skipped_not_crashed(self):
        """טבעת של שלוש נקודות אינה פוליגון. מדלגים ולא נופלים."""
        payload = self.build([
            ("מנוון", "X", "", [[OUTER[0], OUTER[1]]]),
            ("תקין", "A-B", "", [ring(OUTER, True)]),
        ])
        self.assertEqual(len(payload["features"]), 1)
        self.assertEqual(payload["features"][0]["properties"]["NAME"], "תקין")

    def test_precision_is_bounded(self):
        """שבע ספרות ≈ סנטימטר. זנב ארוך יותר הוא רעש מההמרה."""
        for lon, lat in self.coords(self.build([("פרוזדור", "A", "", [ring(OUTER, True)])])):
            self.assertLessEqual(len(str(lon).split(".")[-1]), cvfr.PRECISION)
            self.assertLessEqual(len(str(lat).split(".")[-1]), cvfr.PRECISION)

    def test_metadata_present(self):
        payload = self.build([("פרוזדור", "A", "", [ring(OUTER, True)])])
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertTrue(payload["generated_at"].endswith("Z"))
        self.assertIn("משרד התחבורה", payload["source"])

    def test_polyline_source_is_refused(self):
        """אם המאגר יעבור לקווים, עצירה עדיפה על ציור קו מרכז בשקט."""
        import shapefile

        with tempfile.TemporaryDirectory() as directory:
            path = write_shapefile(
                directory,
                [("נתיב", "A", "", [[P1, P2]])],
                shape_type=shapefile.POLYLINE,
            )
            with self.assertRaises(SystemExit) as caught:
                cvfr.build(path)
        self.assertIn("אינו פוליגון", str(caught.exception))


class RingAreaTest(unittest.TestCase):
    def test_orientation_sign(self):
        """כל הפרדת החורים נשענת על הסימן הזה."""
        clockwise = [[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]
        self.assertGreater(cvfr.ring_area(clockwise), 0)
        self.assertLess(cvfr.ring_area(list(reversed(clockwise))), 0)


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
