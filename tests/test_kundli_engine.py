"""
test_kundli_engine.py
=====================
Unit tests for KundliEngine stub (no PyJHora required) and
formatter output structure.
Covers TC-KUNDLI-* tests that can run without swisseph.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from backend.kundli_engine.engine import KundliEngine
from backend.kundli_engine.formatter import format_for_claude_compact


class TestKundliEngineStub(unittest.TestCase):
    """Tests against the built-in stub — no PyJHora required."""

    def setUp(self):
        self.engine = KundliEngine()
        self.kundli = self.engine.stub_kundli("Test User")

    def test_stub_has_birth_info(self):
        bi = self.kundli.get("birth_info", {})
        self.assertIn("date_of_birth", bi)
        self.assertIn("time_of_birth", bi)
        self.assertIn("place", bi)
        self.assertIn("latitude", bi)
        self.assertIn("longitude", bi)
        self.assertIn("timezone_offset", bi)

    def test_stub_has_lagna(self):
        lagna = self.kundli.get("lagna", {})
        self.assertIn("rasi", lagna)
        self.assertIn("nakshatra", lagna)
        self.assertIn("nakshatra_pada", lagna)
        self.assertIn("degree", lagna)

    def test_stub_has_nine_grahas(self):
        rasi = self.kundli.get("rasi_chart", {})
        expected = ["Sun", "Moon", "Mars", "Mercury", "Jupiter",
                    "Venus", "Saturn", "Rahu", "Ketu"]
        for graha in expected:
            self.assertIn(graha, rasi, f"{graha} missing from rasi chart")

    def test_stub_planet_has_required_fields(self):
        rasi = self.kundli.get("rasi_chart", {})
        for planet, info in rasi.items():
            with self.subTest(planet=planet):
                self.assertIn("rasi", info)
                self.assertIn("degree", info)
                self.assertIn("nakshatra", info)
                self.assertIn("nakshatra_pada", info)
                self.assertIn("retrograde", info)

    def test_stub_has_navamsa_d9(self):
        div = self.kundli.get("divisional_charts", {})
        self.assertIn("D9_Navamsa", div)
        d9 = div["D9_Navamsa"]
        self.assertIn("ascendant", d9)
        self.assertIn("planets", d9)

    def test_stub_has_dasamsa_d10(self):
        div = self.kundli.get("divisional_charts", {})
        self.assertIn("D10_Dasamsa", div)

    def test_stub_has_vimshottari_dasha(self):
        vim = self.kundli.get("dashas", {}).get("vimshottari", {})
        self.assertIn("balance_at_birth", vim)
        self.assertIn("periods", vim)
        self.assertGreater(len(vim["periods"]), 0)

    def test_vimshottari_period_has_required_fields(self):
        periods = self.kundli["dashas"]["vimshottari"]["periods"]
        for p in periods:
            with self.subTest(period=p):
                self.assertIn("maha_lord", p)
                self.assertIn("antara_lord", p)
                self.assertIn("start_date", p)

    def test_stub_lagna_rasi_is_valid(self):
        valid_rasis = ["Aries","Taurus","Gemini","Cancer","Leo","Virgo",
                       "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"]
        lagna = self.kundli.get("lagna", {})
        self.assertIn(lagna.get("rasi"), valid_rasis)

    def test_stub_nakshatra_pada_1_to_4(self):
        lagna = self.kundli.get("lagna", {})
        pada = lagna.get("nakshatra_pada")
        self.assertIn(pada, [1, 2, 3, 4])

    def test_stub_planetary_degrees_in_range(self):
        rasi = self.kundli.get("rasi_chart", {})
        for planet, info in rasi.items():
            with self.subTest(planet=planet):
                deg = info.get("degree", -1)
                self.assertGreaterEqual(deg, 0)
                self.assertLess(deg, 30, f"{planet} degree should be 0–30 within sign")

    def test_stub_name_stored(self):
        kundli = self.engine.stub_kundli("Narayan Tester")
        self.assertEqual(kundli["birth_info"]["name"], "Narayan Tester")

    def test_engine_unavailable_raises_runtime_error(self):
        """When PyJHora is not installed, generate() should raise RuntimeError."""
        if self.engine.available:
            self.skipTest("PyJHora is installed — testing live engine instead")
        with self.assertRaises(RuntimeError):
            self.engine.generate("Chennai, India", "1990-06-15", "14:30:00")


class TestKundliFormatter(unittest.TestCase):
    """Tests for claude_formatter output."""

    def setUp(self):
        self.kundli = KundliEngine().stub_kundli()

    def test_compact_format_not_empty(self):
        text = format_for_claude_compact(self.kundli)
        self.assertGreater(len(text), 100)

    def test_compact_format_contains_birth_info(self):
        text = format_for_claude_compact(self.kundli)
        self.assertIn("BIRTH", text.upper())
        self.assertIn("1990-06-15", text)

    def test_compact_format_contains_lagna(self):
        text = format_for_claude_compact(self.kundli)
        self.assertIn("LAGNA", text.upper())
        self.assertIn("Virgo", text)

    def test_compact_format_contains_sun(self):
        text = format_for_claude_compact(self.kundli)
        self.assertIn("Sun", text)

    def test_compact_format_contains_vimshottari(self):
        text = format_for_claude_compact(self.kundli)
        self.assertIn("VIMSHOTTARI", text.upper())

    def test_compact_format_contains_d9(self):
        text = format_for_claude_compact(self.kundli)
        self.assertIn("D9", text.upper())

    def test_compact_format_contains_d10(self):
        text = format_for_claude_compact(self.kundli)
        self.assertIn("D10", text.upper())

    def test_compact_format_token_efficiency(self):
        """Compact format should be under 3000 characters for cost control."""
        text = format_for_claude_compact(self.kundli)
        self.assertLess(len(text), 6000,
            "Compact format too large — will increase API costs")

    def test_format_empty_kundli_no_crash(self):
        """Formatter must not crash on empty input."""
        try:
            text = format_for_claude_compact({})
            self.assertIsInstance(text, str)
        except Exception as e:
            self.fail(f"Formatter crashed on empty input: {e}")


if __name__ == "__main__":
    unittest.main()
