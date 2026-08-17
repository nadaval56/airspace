#!/usr/bin/env python3
"""בדיקות לסיווג המשני של אזורי הפמ"ת."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aip_classify import (  # noqa: E402
    FLOOR_SPLIT_FT,
    THEME_LABELS,
    classify,
    floor_band,
    floor_feet,
    theme,
)


class ThemeTest(unittest.TestCase):
    """הנושא נגזר ממילים שכתובות בשם הרשמי, לא מהיכרות עם המקום."""

    def test_literal_words_from_real_names(self):
        cases = {
            "שטח אש 209": "firing",
            "שטח אש 900": "firing",
            'שט"ן 83': "firing",
            "מטווח 80 צפון": "firing",
            "גליל הצנחה \"הבונים\"": "drop",
            "בלון אבשלום": "balloon",
            'אסדת "לוויתן"': "offshore",
            "תמר/ים טטיס": "offshore",
            "יהודה ושומרון צפון": "judea",
            "הטסת רחפנים גלילות": "model",
            "מנחת טיסנים נגבה": "model",
            "מחוז ירושלים": "police",
            "מטה ארצי ירושלים": "police",
            'מרחב נתב"ג': "transit",
            "נקודת גשר אלנבי": "transit",
        }
        for name, expected in cases.items():
            self.assertEqual(theme(name), expected, name)

    def test_unmarked_name_is_not_guessed(self):
        """אלה שמות אמיתיים במקור. בלי מילת מפתח — אין סיווג, ולא ניחוש."""
        for name in ("החולה", "דימונה", "אשל", "דמון", "כרמל", "מגידו"):
            self.assertEqual(theme(name), "other", name)

    def test_missing_name_is_other(self):
        self.assertEqual(theme(None), "other")
        self.assertEqual(theme(""), "other")

    def test_every_key_has_a_label(self):
        for name in ("שטח אש 1", "בלון x", "לא ידוע", None):
            self.assertIn(theme(name), THEME_LABELS)


class FloorTest(unittest.TestCase):
    def test_ground_words(self):
        for word in ("GND", "MSL", "SFC", "gnd"):
            self.assertEqual(floor_feet(word), 0)
            self.assertEqual(floor_band(word), "ground")

    def test_numeric_floor(self):
        self.assertEqual(floor_feet("3000"), 3000)
        self.assertEqual(floor_band("3000"), "low")
        self.assertEqual(floor_band("14000"), "high")

    def test_split_is_inclusive_at_the_threshold(self):
        """4,000 עצמו נחשב נמוך; מעליו — גבוה."""
        self.assertEqual(floor_band(str(FLOOR_SPLIT_FT)), "low")
        self.assertEqual(floor_band(str(FLOOR_SPLIT_FT + 1)), "high")

    def test_missing_floor_is_unknown_not_ground(self):
        """אזורי נספח ג' באים בלי גובה. להניח 'מהקרקע' היה המצאה."""
        self.assertEqual(floor_band(None), "unknown")
        self.assertEqual(floor_band(""), "unknown")
        self.assertEqual(floor_band("UNL"), "unknown")


class ClassifyTest(unittest.TestCase):
    def test_returns_both_axes(self):
        result = classify({"name": "שטח אש 209", "lower_limit": "GND"})
        self.assertEqual(result, {"theme": "firing", "floor_band": "ground"})

    def test_survives_empty_properties(self):
        self.assertEqual(classify({}), {"theme": "other", "floor_band": "unknown"})


class LiveDataTest(unittest.TestCase):
    """הסיווג השמור בקובץ חייב להתאים לפונקציות — אחרת הדף מציג ישן."""

    def test_stored_classification_matches(self):
        import json

        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "aip-permanent.geojson",
        )
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

        for feature in data.get("features", []):
            props = feature["properties"]
            if "theme" not in props:
                continue
            expected = classify(props)
            self.assertEqual(props["theme"], expected["theme"], props.get("id"))
            self.assertEqual(props["floor_band"], expected["floor_band"], props.get("id"))


if __name__ == "__main__":
    unittest.main()
