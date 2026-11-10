"""Exercise independent auth storage, session and account controls against temp SQLite."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import independent_auth as auth


class IndependentAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = auth.DB
        auth.DB = Path(self.temp.name) / "auth.sqlite3"
        auth.initialize()

    def tearDown(self):
        auth.DB = self.original_db
        self.temp.cleanup()

    def create_admin(self):
        with patch.dict(os.environ, {
            "AI_BOOTSTRAP_EMAIL": "admin@example.com",
            "AI_BOOTSTRAP_PASSWORD": "a-long-test-password-123",
        }, clear=False):
            self.assertTrue(auth.provision_initial_admin())
        return auth.list_users()[0]


    def test_pending_names_keep_nonblank_country_when_duplicate_entities_are_grouped(self):
        with auth.connection() as db:
            db.execute(
                "INSERT INTO research_entities "
                "(original_name,country,verification_status,appearances) "
                "VALUES (?,?,?,?)",
                ("Duplicate Company Ltd", "", "Unknown", 2),
            )
            db.execute(
                "INSERT INTO research_entities "
                "(original_name,country,verification_status,appearances) "
                "VALUES (?,?,?,?)",
                ("Duplicate Company Ltd", "India", "Verified", 5),
            )
        pending = auth.pending_classification_names()
        row = next(x for x in pending if x["company_name"] == "Duplicate Company Ltd")
        self.assertEqual(row["country"], "India")
        self.assertEqual(row["appearances"], 5)

    def test_bootstrap_provisions_one_admin_only(self):
        admin = self.create_admin()
        self.assertEqual(admin["role"], "admin")
        self.assertFalse(auth.provision_initial_admin())
        self.assertEqual(auth.bootstrap_status(), "existing_account")

    def test_login_stores_only_hash_of_session_token_and_logout_revokes_it(self):
        admin = self.create_admin()
        token = auth.authenticate(admin["email"], "a-long-test-password-123")
        self.assertIsNotNone(token)
        with auth.connection() as db:
            stored = db.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertNotEqual(stored, token)
        self.assertEqual(len(stored), 64)
        self.assertEqual(auth.session_user(token)["id"], admin["id"])
        auth.logout(token)
        self.assertIsNone(auth.session_user(token))

    def test_five_failed_logins_lock_account_even_with_correct_password(self):
        admin = self.create_admin()
        for _ in range(5):
            self.assertIsNone(auth.authenticate(admin["email"], "incorrect-password"))
        with auth.connection() as db:
            row = db.execute("SELECT failed,locked_until FROM users WHERE id=?", (admin["id"],)).fetchone()
        self.assertEqual(row["failed"], 5)
        self.assertGreater(row["locked_until"], 0)
        self.assertIsNone(auth.authenticate(admin["email"], "a-long-test-password-123"))

    def test_new_user_scope_is_restricted_and_edit_revokes_sessions(self):
        admin = self.create_admin()
        user_id = auth.add_user(admin["id"], "viewer@example.com", "Viewer",
                                "another-long-password-123", "viewer", ["NG"], ["AE", "OE"])
        token = auth.authenticate("viewer@example.com", "another-long-password-123")
        user = auth.session_user(token)
        self.assertEqual(user["companies"], ["NG"])
        self.assertEqual(user["lobs"], ["AE", "OE"])
        auth.edit_user(admin["id"], user_id, active=False)
        self.assertIsNone(auth.session_user(token))

    def test_user_cannot_be_created_with_out_of_scope_company(self):
        admin = self.create_admin()
        with self.assertRaisesRegex(ValueError, "permissions"):
            auth.add_user(admin["id"], "bad@example.com", "Bad",
                          "another-long-password-123", "viewer", ["OTHER"], ["AE"])

    def test_administrator_cannot_disable_own_account(self):
        admin = self.create_admin()
        with self.assertRaisesRegex(ValueError, "own administrator access"):
            auth.edit_user(admin["id"], admin["id"], active=False)


if __name__ == "__main__":
    unittest.main()
