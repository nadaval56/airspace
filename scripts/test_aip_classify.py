#!/usr/bin/env python3
"""בדיקות לסיווג המשני של אזורי הפמ"ת."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aip_classify import (  # noqa: E402
    FLOOR_SPLIT_FT,
    IPS_AUTHORITY,
    THEME_LABELS,
    classify,
    floor_band,
    floor_feet,
    theme,
)


class ThemeTest(unittest.TestCase):
    """הנושא נגזר ממילים שכתובות במקור, לא מהיכרות עם המקום."""

    def test_literal_words_from_real_names(self):
        cases = {
            "שטח אש 209": "firing",
            "שטח אש 900": "firing",
            'שט"ן 83': "firing",
            "מטווח 80 צפון": "firing",
            "גליל הצנחה \"הבונים\"": "drop",
            "בלון אבשלום": "balloon",
            "בלון מעוגן חלמיש": "balloon",
            'אסדת "לוויתן"': "offshore",
            "תמר/ים טטיס": "offshore",
            "יהודה ושומרון צפון": "judea",
            "הטסת רחפנים גלילות": "model",
            "מנחת טיסנים נגבה": "model",
            "מחוז ירושלים": "police",
            "מטה ארצי ירושלים": "police",
            'מטה מג"ב לוד': "police",
            "בתי הזיקוק": "energy",
            "תחנת כוח חדרה": "energy",
            "תחנת אגירה כוכב הירדן": "energy",
            "טורבינות עמק הבכא": "energy",
            "מפעל יצחק": "industry",
            "מחצבת חתרורים": "industry",
            "אזור תעשיה קיסריה": "industry",
            "אזור סחר ראש העין": "industry",
            "מכון למחקר ביולוגי": "research",
            "מחנה בית ליד": "military",
            "קריית הממשלה": "government",
            "עיריית רעננה": "government",
            "נקודת נמל תעופה אילת רמון": "airport",
            'מרחב נתב"ג': "transit",
            "נקודת גשר אלנבי": "transit",
        }
        for name, expected in cases.items():
            self.assertEqual(theme(name), expected, name)

    def test_specific_word_wins_over_general(self):
        """סדר הכללים אינו שרירותי: מנחת טיסנים הוא אתר טיסנים ולא
        נמל תעופה, ומתקן מג"ב הוא מג"ב ולא סתם בה"ד."""
        self.assertEqual(theme("מנחת טיסנים נגבה"), "model")
        self.assertEqual(theme('בה"ד מג"ב בית חורון'), "police")

    def test_unmarked_name_is_not_guessed(self):
        """אלה שמות אמיתיים במקור. בלי מילת מפתח בשם ובלי מלל —
        אין סיווג, ולא ניחוש."""
        for name in ("החולה", "דימונה", "אשל", "דמון", "כרמל", "מגידו"):
            self.assertEqual(theme(name), "other", name)

    def test_missing_name_is_other(self):
        self.assertEqual(theme(None), "other")
        self.assertEqual(theme(""), "other")

    def test_every_key_has_a_label(self):
        for name in ("שטח אש 1", "בלון x", "לא ידוע", None):
            self.assertIn(theme(name), THEME_LABELS)


class NarrativeThemeTest(unittest.TestCase):
    """המלל של הפרק הוא חלק מהמקור — והוא הפרסום הקובע."""

    def test_reserve_is_read_from_the_chapter_text(self):
        """הטבלה כותבת "החולה"; המלל כותב "מעל שמורת הטבע 'החולה'"."""
        narrative = {"title": 'האזור האסור מעל שמורת הטבע "החולה'}
        self.assertEqual(theme("החולה", narrative, "LLP01"), "nature")

    def test_uav_zone_without_a_named_body_falls_to_ips(self):
        """סעיף 1א: מי שלא מצוין תחתיו גורם — התיאום עליו מול שב"ס."""
        narrative = {"title": 'האזור האסור "אשל.', "coordination": None}
        self.assertEqual(theme("אשל", narrative, "LLU02"), "ips")

    def test_a_named_body_beats_the_default(self):
        narrative = {"title": 'האזור האסור "דור.', "coordination": "לתיאום טיסה..."}
        self.assertEqual(theme("דור", narrative, "LLU55"), "contact")

    def test_the_ips_default_is_only_for_uav_zones(self):
        """סעיף 1א מדבר על אזורי ה-LLU בלבד. אזור אסור רגיל בלי גורם
        תיאום נשאר בלי סיווג, ולא נתלה בשב"ס."""
        narrative = {"title": 'האזור האסור "דימונה', "coordination": None}
        self.assertEqual(theme("דימונה", narrative, "LLP15"), "other")

    def test_a_name_keyword_still_wins(self):
        """גם כשהמלל נוקב גורם תיאום, מפעל נשאר מפעל."""
        narrative = {"title": 'האזור האסור "מפעל יצחק', "coordination": "לתיאום טיסה..."}
        self.assertEqual(theme("מפעל יצחק", narrative, "LLP22"), "industry")

    def test_ips_default_authority_is_written_out(self):
        properties = {"id": "LLU02", "name": "אשל", "lower_limit": None}
        fields = classify(properties, {"title": 'האזור האסור "אשל.'})
        self.assertEqual(fields["theme"], "ips")
        self.assertEqual(fields["authority"], IPS_AUTHORITY)

    def test_ips_default_is_not_pinned_on_an_identified_facility(self):
        """על "קריית הממשלה" גם כן לא מצוין גורם, אבל לשלוח טייס
        לשב"ס בגלל מתקן שהמקור מזהה אחרת זו טעות שקטה."""
        properties = {"id": "LLU44", "name": "קריית הממשלה", "lower_limit": None}
        fields = classify(properties, {"title": 'האזור האסור "קריית הממשלה.'})
        self.assertEqual(fields["theme"], "government")
        self.assertNotIn("authority", fields)

    def test_coordination_is_carried_to_the_popup(self):
        sentence = "לתיאום טיסה במרחב זה יש ליצור קשר עם מגדל רמת דוד"
        fields = classify(
            {"id": "LLD41", "name": "דליה", "lower_limit": "2000"},
            {"title": 'האזור המסוכן "דליה', "coordination": sentence,
             "authority": "מגדל רמת דוד"},
        )
        self.assertEqual(fields["coordination"], sentence)
        self.assertEqual(fields["authority"], "מגדל רמת דוד")

    def test_no_narrative_means_no_extra_fields(self):
        """נספח ד' אין לו מלל. אזור כזה מקבל נושא מהשם, וזה הכול."""
        fields = classify({"id": "LLP3001", "name": "בלון מעוגן חלמיש",
                           "lower_limit": "GND"})
        self.assertEqual(fields, {"theme": "balloon", "floor_band": "ground"})


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
    """הסיווג השמור בקבצים חייב להתאים לפונקציות — אחרת הדף מציג ישן.

    הבדיקה אינה יכולה לשחזר את הנושא במלואו, כי חלקו נגזר ממלל ה-PDF
    שאינו במאגר. מה שכן נבדק הוא כל מה שאינו תלוי במלל: רצפת הגובה,
    חוקיות המפתח, והכלל שמילת סיווג **בשם** אינה נדרסת.
    """

    DATA = ("data/aip-permanent.geojson", "data/aip-obstacles.geojson")

    def features(self):
        import json

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for name in self.DATA:
            with open(os.path.join(root, name), encoding="utf-8") as fh:
                for feature in json.load(fh).get("features", []):
                    yield name, feature["properties"]

    def test_floor_band_matches(self):
        for name, props in self.features():
            if "floor_band" not in props:
                continue
            self.assertEqual(
                props["floor_band"],
                floor_band(props.get("lower_limit")),
                f"{name} {props.get('id')}",
            )

    def test_every_stored_theme_is_known(self):
        for name, props in self.features():
            self.assertIn(props.get("theme", "other"), THEME_LABELS,
                          f"{name} {props.get('id')}")

    def test_a_name_keyword_is_never_overridden(self):
        """אם השם עצמו נושא מילת סיווג, זה הנושא — גם אחרי שהמלל נקרא."""
        for name, props in self.features():
            from_name = theme(props.get("name"))
            if from_name == "other":
                continue
            self.assertEqual(props.get("theme"), from_name,
                             f"{name} {props.get('id')} {props.get('name')}")

    def test_the_balloons_are_all_in_one_place(self):
        """הבאג שהתחיל את הכל: שמונה בלוני נספח ד' ישבו ב"ללא סיווג"
        בעוד שני בלוני נספח ב' ישבו ב"בלונים"."""
        balloons = [
            props for _, props in self.features()
            if "בלון" in (props.get("name") or "")
        ]
        self.assertEqual(len(balloons), 10)
        for props in balloons:
            self.assertEqual(props.get("theme"), "balloon", props.get("id"))


if __name__ == "__main__":
    unittest.main()
