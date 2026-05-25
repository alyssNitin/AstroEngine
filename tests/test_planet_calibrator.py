"""
test_planet_calibrator.py
=========================
Unit tests for PlanetCalibrator and PlanetKnowledge.
No external dependencies required.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from backend.ai_interpretation.planet_calibrator import (
    PlanetCalibrator, PlanetKnowledge, PlanetSignal
)
from backend.kundli_engine.engine import KundliEngine


STUB_KUNDLI = KundliEngine().stub_kundli("Test User")

CONFIRMED_CORRECTIONS = {
    "education": "Confirmed — yes, I studied engineering",
    "career":    "Yes, that's right — I work in IT",
    "marriage":  "Confirmed — married in 2018",
}

MIXED_CORRECTIONS = {
    "education": "Actually I studied medicine, not engineering",
    "career":    "Confirmed — yes, IT sector",
    "marriage":  "I am not married yet",
}


class TestPlanetCalibratorBasic(unittest.TestCase):

    def test_confirmed_feedback_adds_active_signals(self):
        pk = PlanetCalibrator.calibrate_from_feedback(CONFIRMED_CORRECTIONS, STUB_KUNDLI)
        self.assertGreater(len(pk.active), 0)

    def test_correction_feedback_adds_inactive_signals(self):
        pk = PlanetCalibrator.calibrate_from_feedback(MIXED_CORRECTIONS, STUB_KUNDLI)
        # "Actually I studied medicine" → not confirmed
        domains = [s.domain for s in pk.inactive]
        self.assertIn("education", domains)

    def test_confirmation_keywords_detected(self):
        self.assertTrue(PlanetCalibrator._is_confirmed("Confirmed — yes, this is accurate"))
        self.assertTrue(PlanetCalibrator._is_confirmed("Yes, that's right"))
        self.assertTrue(PlanetCalibrator._is_confirmed("Absolutely correct"))

    def test_correction_keywords_not_confirmed(self):
        self.assertFalse(PlanetCalibrator._is_confirmed("Actually I studied medicine"))
        self.assertFalse(PlanetCalibrator._is_confirmed("Not quite right"))
        self.assertFalse(PlanetCalibrator._is_confirmed("I am not married yet"))

    def test_education_maps_to_jupiter_mercury(self):
        pk = PlanetCalibrator.calibrate_from_feedback(
            {"education": "Confirmed — I studied engineering"}, STUB_KUNDLI
        )
        active_planets = pk.active_planet_names()
        self.assertIn("Jupiter", active_planets)
        self.assertIn("Mercury", active_planets)

    def test_career_maps_to_saturn_sun(self):
        pk = PlanetCalibrator.calibrate_from_feedback(
            {"career": "Confirmed — IT sector"}, STUB_KUNDLI
        )
        active_planets = pk.active_planet_names()
        self.assertIn("Saturn", active_planets)

    def test_marriage_maps_to_venus(self):
        pk = PlanetCalibrator.calibrate_from_feedback(
            {"marriage": "Confirmed — married in 2018"}, STUB_KUNDLI
        )
        active_planets = pk.active_planet_names()
        self.assertIn("Venus", active_planets)

    def test_summary_not_empty_after_calibration(self):
        pk = PlanetCalibrator.calibrate_from_feedback(CONFIRMED_CORRECTIONS, STUB_KUNDLI)
        self.assertTrue(pk.summary, "Summary should not be empty after calibration")

    def test_for_prompt_lists_active_planets(self):
        pk = PlanetCalibrator.calibrate_from_feedback(CONFIRMED_CORRECTIONS, STUB_KUNDLI)
        prompt_text = pk.for_prompt()
        self.assertIn("CONFIRMED", prompt_text)

    def test_for_prompt_empty_knowledge(self):
        pk = PlanetKnowledge()
        prompt_text = pk.for_prompt()
        self.assertIn("No calibration", prompt_text)


class TestPlanetKnowledgeSerialization(unittest.TestCase):

    def test_to_dict_and_from_dict_roundtrip(self):
        pk = PlanetCalibrator.calibrate_from_feedback(CONFIRMED_CORRECTIONS, STUB_KUNDLI)
        d  = pk.to_dict()
        pk2 = PlanetKnowledge.from_dict(d)
        self.assertEqual(
            sorted(pk.active_planet_names()),
            sorted(pk2.active_planet_names()),
        )
        self.assertEqual(pk.summary, pk2.summary)

    def test_to_dict_has_required_keys(self):
        pk = PlanetKnowledge()
        d  = pk.to_dict()
        self.assertIn("active", d)
        self.assertIn("inactive", d)
        self.assertIn("summary", d)

    def test_from_dict_empty(self):
        pk = PlanetKnowledge.from_dict({})
        self.assertEqual(pk.active, [])
        self.assertEqual(pk.inactive, [])

    def test_active_planet_names_unique(self):
        pk = PlanetCalibrator.calibrate_from_feedback(CONFIRMED_CORRECTIONS, STUB_KUNDLI)
        names = pk.active_planet_names()
        self.assertEqual(len(names), len(set(names)), "active_planet_names should be unique")


class TestMergeNewFeedback(unittest.TestCase):

    def test_merge_adds_new_signals(self):
        pk = PlanetCalibrator.calibrate_from_feedback(
            {"education": "Confirmed — engineering"}, STUB_KUNDLI
        )
        initial_count = len(pk.active)
        pk = PlanetCalibrator.merge_new_feedback(
            pk, {"health": "Confirmed — yes, I had stomach issues"}, STUB_KUNDLI
        )
        self.assertGreater(len(pk.active), initial_count)

    def test_merge_does_not_duplicate(self):
        pk = PlanetCalibrator.calibrate_from_feedback(
            {"education": "Confirmed — engineering"}, STUB_KUNDLI
        )
        count_before = len(pk.active)
        # Adding same domain again should not duplicate
        pk = PlanetCalibrator.merge_new_feedback(
            pk, {"education": "Confirmed — yes, engineering"}, STUB_KUNDLI
        )
        self.assertEqual(len(pk.active), count_before)


class TestLLMCalibrationMerge(unittest.TestCase):

    def test_llm_calibration_enriches_active(self):
        pk = PlanetCalibrator.calibrate_from_feedback(
            {"education": "Confirmed"},
            STUB_KUNDLI,
            llm_calibration={
                "active_planets": [
                    {"planet": "Jupiter", "domain": "education",
                     "reason": "Jupiter in 5th confirms education"},
                    {"planet": "Sun", "domain": "career",
                     "reason": "Sun in 10th for leadership career"},
                ],
                "inactive_or_misread": [],
                "summary": "Jupiter and Sun are giving strong results",
            }
        )
        active_names = pk.active_planet_names()
        self.assertIn("Sun", active_names)
        self.assertIn("Jupiter", active_names)

    def test_llm_summary_applied(self):
        pk = PlanetCalibrator.calibrate_from_feedback(
            {"career": "Confirmed — IT"},
            STUB_KUNDLI,
            llm_calibration={
                "active_planets": [],
                "inactive_or_misread": [],
                "summary": "Saturn is the primary active planet",
            }
        )
        self.assertIn("Saturn", pk.summary)


if __name__ == "__main__":
    unittest.main()
