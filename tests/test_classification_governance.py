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
        auth.classification_save(7, "Example Logistics", "Logistics & Supply Chain Services", "high",
                                 "https://example.com/evidence", False, "India")
        auth.initialize()
        record = auth.classification_list("Example Logistics")[0]
        self.assertEqual(record["approved"], 0)

    def test_contributor_submission_is_pending_until_admin_approval(self):
        auth.classification_save(7, "Example Logistics", "Logistics & Supply Chain Services", "high",
                                 "https://example.com/evidence", False, "India")
        record = auth.classification_list("Example Logistics")[0]
        self.assertEqual(record["approved"], 0)
        self.assertEqual(auth.classification_industry_status()["classified"], 0)
        self.assertEqual(auth.classification_industry_status()["pending_review"], 1)
        self.assertTrue(auth.approve_classification(1, record["id"]))
        self.assertEqual(auth.classification_list("Example Logistics")[0]["approved"], 1)
        self.assertEqual(auth.classification_industry_status()["classified"], 1)

    def test_approved_record_cannot_be_overwritten_by_contributor(self):
        auth.classification_save(1, "Example Logistics", "Logistics & Supply Chain Services", "high",
                                 "Verified evidence", True, "India")
        with self.assertRaisesRegex(ValueError, "approved classification cannot be overwritten"):
            auth.classification_save(7, "Example Logistics", "Consumer Goods & Retail", "high",
                                     "Different evidence", False, "India")
        self.assertEqual(auth.classification_list("Example Logistics")[0]["industry"], "Logistics & Supply Chain Services")

    def test_excel_import_creates_pending_records_and_preserves_approved(self):
        auth.classification_save(1, "Protected Company", "Industrial Manufacturing & Engineering", "high",
                                 "Verified evidence", True, "India")
        imported = auth.classification_import(7, [
            ("Protected Company", "Consumer Goods & Retail", "high", "New workbook source", False, "India"),
            ("New Company", "Electronics & Electrical Equipment", "medium", "Research source", False, "Germany"),
        ])
        self.assertEqual(imported, 1)
        records = {r["company_name"]: r for r in auth.classification_list("")}
        self.assertEqual(records["Protected Company"]["industry"], "Industrial Manufacturing & Engineering")
        self.assertEqual(records["Protected Company"]["approved"], 1)
        self.assertEqual(records["New Company"]["approved"], 0)

    def test_missing_or_already_approved_id_is_not_reapproved(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            auth.approve_classification(1, 999)
        auth.classification_save(1, "Example Logistics", "Logistics & Supply Chain Services", "high",
                                 "Evidence", True, "India")
        record = auth.classification_list("Example Logistics")[0]
        self.assertFalse(auth.approve_classification(1, record["id"]))


    def test_reclassification_reset_archives_and_returns_all_records_to_pending(self):
        auth.classification_save(1, "Previously Classified Co", "Automotive & Auto Components",
                                 "high", "Verified source", True, "India")
        result = auth.reset_classifications_for_reclassification(1, "batch-2026-11-10")
        self.assertEqual(result["reset"], 1)
        record = auth.classification_list("Previously Classified Co")[0]
        self.assertEqual(record["industry"], "")
        self.assertEqual(record["approved"], 0)
        self.assertEqual(auth.classification_history_count(), 1)
        self.assertEqual(auth.pending_classification_names()[0]["company_name"], "Previously Classified Co")
        with self.assertRaisesRegex(ValueError, "already been applied"):
            auth.reset_classifications_for_reclassification(1, "batch-2026-11-10")

    def test_only_exact_approved_industry_labels_are_accepted(self):
        with self.assertRaisesRegex(ValueError, "15 approved verticals"):
            auth.classification_save(1, "Bad Category Co", "Automotive", "high", "Evidence", False, "India")


if __name__ == "__main__":
    unittest.main()
