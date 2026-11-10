"""Regression tests for durable classification review and approval governance."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import independent_auth as auth


class ClassificationGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "auth.sqlite3"
        self.db_patch = patch.object(auth, "DB", self.db_path)
        self.db_patch.start()
        auth.initialize()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_startup_does_not_auto_approve_pending_records(self):
        auth.classification_save(7, "Example Logistics", "Logistics", "high",
                                 "https://example.com/evidence", False, "India")
        auth.initialize()
        record = auth.classification_list("Example Logistics")[0]
        self.assertEqual(record["approved"], 0)

    def test_contributor_submission_is_pending_until_admin_approval(self):
        auth.classification_save(7, "Example Logistics", "Logistics", "high",
                                 "https://example.com/evidence", False, "India")
        record = auth.classification_list("Example Logistics")[0]
        self.assertEqual(record["approved"], 0)
        self.assertEqual(auth.classification_industry_status()["classified"], 0)
        self.assertEqual(auth.classification_industry_status()["pending_review"], 1)
        self.assertTrue(auth.approve_classification(1, record["id"]))
        self.assertEqual(auth.classification_list("Example Logistics")[0]["approved"], 1)
        self.assertEqual(auth.classification_industry_status()["classified"], 1)

    def test_approved_record_cannot_be_overwritten_by_contributor(self):
        auth.classification_save(1, "Example Logistics", "Logistics", "high",
                                 "Verified evidence", True, "India")
        with self.assertRaisesRegex(ValueError, "approved classification cannot be overwritten"):
            auth.classification_save(7, "Example Logistics", "Retail", "high",
                                     "Different evidence", False, "India")
        self.assertEqual(auth.classification_list("Example Logistics")[0]["industry"], "Logistics")

    def test_excel_import_creates_pending_records_and_preserves_approved(self):
        auth.classification_save(1, "Protected Company", "Manufacturing", "high",
                                 "Verified evidence", True, "India")
        imported = auth.classification_import(7, [
            ("Protected Company", "Retail", "high", "New workbook source", False, "India"),
            ("New Company", "Electronics", "medium", "Research source", False, "Germany"),
        ])
        self.assertEqual(imported, 1)
        records = {r["company_name"]: r for r in auth.classification_list("")}
        self.assertEqual(records["Protected Company"]["industry"], "Manufacturing")
        self.assertEqual(records["Protected Company"]["approved"], 1)
        self.assertEqual(records["New Company"]["approved"], 0)

    def test_missing_or_already_approved_id_is_not_reapproved(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            auth.approve_classification(1, 999)
        auth.classification_save(1, "Example Logistics", "Logistics", "high",
                                 "Evidence", True, "India")
        record = auth.classification_list("Example Logistics")[0]
        self.assertFalse(auth.approve_classification(1, record["id"]))


if __name__ == "__main__":
    unittest.main()
