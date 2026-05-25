"""
test_persistence.py
===================
Unit tests for Database — uses a temp SQLite file.
Covers TC-WALLET-* style CRUD tests adapted for the user profile store.
"""
import sys, os, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import unittest
from backend.persistence.database import Database
from backend.kundli_engine.engine import KundliEngine


def _make_db() -> tuple:
    """Return (db, tmpdir) — caller must clean up tmpdir."""
    tmpdir = tempfile.mkdtemp()
    db = Database(path=os.path.join(tmpdir, "test.db"))
    return db, tmpdir


STUB = KundliEngine().stub_kundli("Test User")


class TestDatabaseInit(unittest.TestCase):

    def setUp(self):
        self.db, self.tmpdir = _make_db()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_creates_table(self):
        # If init() worked, lookup should return None (not crash)
        result = self.db.lookup("anyone@test.com")
        self.assertIsNone(result)

    def test_init_idempotent(self):
        # Calling init() twice should not raise
        self.db.init()
        self.db.init()


class TestDatabaseCRUD(unittest.TestCase):

    def setUp(self):
        self.db, self.tmpdir = _make_db()
        self.email = "ravi@test.com"
        self.uid = self.db.save_or_update(
            email=self.email,
            name="Ravi Kumar",
            date_of_birth="1990-06-15",
            time_of_birth="14:30:00",
            place_of_birth="Chennai, India",
            latitude=13.08,
            longitude=80.27,
            timezone_offset=5.5,
            kundli=STUB,
            predictions=[{"id": "education", "statement": "test"}],
            overall_theme="Life of service",
            lagna=STUB["lagna"],
            birth_info=STUB["birth_info"],
            marital_status="married",
            session_id="sess-001",
        )

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_returns_uid(self):
        self.assertIsInstance(self.uid, str)
        self.assertGreater(len(self.uid), 0)

    def test_lookup_finds_saved_user(self):
        profile = self.db.lookup(self.email)
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "Ravi Kumar")

    def test_lookup_email_case_insensitive(self):
        profile = self.db.lookup("RAVI@TEST.COM")
        self.assertIsNotNone(profile)

    def test_lookup_returns_none_for_unknown(self):
        result = self.db.lookup("nobody@test.com")
        self.assertIsNone(result)

    def test_has_predictions_true(self):
        self.assertTrue(self.db.has_predictions(self.email))

    def test_has_predictions_false_for_unknown(self):
        self.assertFalse(self.db.has_predictions("nobody@test.com"))

    def test_predictions_json_decoded(self):
        profile = self.db.lookup(self.email)
        preds = profile["predictions_json"]
        self.assertIsInstance(preds, list)
        self.assertGreater(len(preds), 0)

    def test_kundli_json_decoded(self):
        profile = self.db.lookup(self.email)
        kundli = profile["kundli_json"]
        self.assertIsInstance(kundli, dict)
        self.assertIn("rasi_chart", kundli)

    def test_update_keeps_same_uid(self):
        uid2 = self.db.save_or_update(
            email=self.email, name="Ravi Kumar Updated",
            date_of_birth="1990-06-15", time_of_birth="14:30:00",
            place_of_birth="Chennai, India",
            latitude=13.08, longitude=80.27, timezone_offset=5.5,
        )
        self.assertEqual(self.uid, uid2)

    def test_update_changes_name(self):
        self.db.save_or_update(
            email=self.email, name="Ravi K.",
            date_of_birth="1990-06-15", time_of_birth="14:30:00",
            place_of_birth="Chennai, India",
            latitude=13.08, longitude=80.27, timezone_offset=5.5,
        )
        profile = self.db.lookup(self.email)
        self.assertEqual(profile["name"], "Ravi K.")

    def test_update_refined_analysis(self):
        self.db.update_refined(
            email=self.email,
            refined_analysis="Jupiter in 5th gives strong education.",
            planet_knowledge={"active": [], "inactive": [], "summary": "Jupiter active"},
            session_id="sess-002",
        )
        profile = self.db.lookup(self.email)
        self.assertIn("Jupiter", profile["refined_analysis"])

    def test_planet_knowledge_json_stored(self):
        self.db.update_refined(
            email=self.email,
            refined_analysis="test",
            planet_knowledge={"active": [{"planet": "Jupiter", "domain": "education",
                                          "confirmed": True, "reason": "test", "strength": 1.0}],
                              "inactive": [], "summary": "Jupiter active"},
        )
        profile = self.db.lookup(self.email)
        pk = profile.get("planet_knowledge_json", {})
        self.assertIsInstance(pk, dict)
        self.assertIn("active", pk)

    def test_marital_status_stored(self):
        profile = self.db.lookup(self.email)
        self.assertEqual(profile["marital_status"], "married")

    def test_delete_removes_user(self):
        deleted = self.db.delete(self.email)
        self.assertTrue(deleted)
        self.assertIsNone(self.db.lookup(self.email))

    def test_delete_nonexistent_returns_false(self):
        deleted = self.db.delete("nobody@test.com")
        self.assertFalse(deleted)

    def test_list_users_includes_saved(self):
        users = self.db.list_users()
        emails = [u["email"] for u in users]
        self.assertIn(self.email, emails)

    def test_multiple_users_isolated(self):
        self.db.save_or_update(
            email="priya@test.com", name="Priya",
            date_of_birth="1992-03-10", time_of_birth="08:00:00",
            place_of_birth="Mumbai, India",
            latitude=19.07, longitude=72.87, timezone_offset=5.5,
        )
        p1 = self.db.lookup(self.email)
        p2 = self.db.lookup("priya@test.com")
        self.assertEqual(p1["name"], "Ravi Kumar")
        self.assertEqual(p2["name"], "Priya")


if __name__ == "__main__":
    unittest.main()
