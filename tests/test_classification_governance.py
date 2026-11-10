"""Regression tests: classifications are immediately active; no approval workflow exists."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import independent_auth as auth


class ClassificationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_patch = patch.object(auth, "DB", Path(self.tmp.name) / "auth.sqlite3")
        self.db_patch.start()
        auth.initialize()

    def tearDown(self):
        self.db_patch.stop()
        self.tmp.cleanup()

    def test_saved_classification_is_immediately_active(self):
        auth.classification_save(7, "Example Logistics", "Logistics & Supply Chain Services",
                                 "high", "https://example.com/evidence", None, "India")
        record = auth.classification_list("Example Logistics")[0]
        self.assertEqual(record["industry"], "Logistics & Supply Chain Services")
        self.assertNotIn("approved", record)
        status = auth.classification_industry_status()
        self.assertEqual(status["classified"], 1)
        self.assertEqual(status["pending_classification"], 0)

    def test_any_authorized_contributor_can_update_existing_classification(self):
        auth.classification_save(1, "Example Logistics", "Logistics & Supply Chain Services",
                                 "high", "Verified evidence", None, "India")
        auth.classification_save(7, "Example Logistics", "Consumer Goods & Retail",
                                 "medium", "Updated source", None, "India")
        record = auth.classification_list("Example Logistics")[0]
        self.assertEqual(record["industry"], "Consumer Goods & Retail")
        self.assertEqual(record["confidence"], "medium")
        self.assertEqual(record["source"], "Updated source")

    def test_excel_import_immediately_saves_and_overwrites_classifications(self):
        auth.classification_save(1, "Existing Company", "Industrial Manufacturing & Engineering",
                                 "high", "Old evidence", None, "India")
        imported = auth.classification_import(7, [
            ("Existing Company", "Automotive & Auto Components", "medium", "New workbook source", False, "India"),
            ("New Company", "Electronics & Electrical Equipment", "high", "Research source", False, "Germany"),
        ])
        self.assertEqual(imported, 2)
        records = {r["company_name"]: r for r in auth.classification_list("")}
        self.assertEqual(records["Existing Company"]["industry"], "Automotive & Auto Components")
        self.assertEqual(records["New Company"]["industry"], "Electronics & Electrical Equipment")
        self.assertEqual(auth.classification_industry_status()["classified"], 2)

    def test_blank_industry_is_pending_and_valid_label_required(self):
        with self.assertRaisesRegex(ValueError, "15 defined verticals"):
            auth.classification_save(1, "Bad Category Co", "Automotive", "high", "Evidence", None, "India")
        self.assertEqual(auth.classification_industry_status()["pending_classification"], 0)

    def test_reclassification_reset_archives_existing_data_and_clears_industry(self):
        auth.classification_save(1, "Previously Classified Co", "Automotive & Auto Components",
                                 "high", "Verified source", None, "India")
        result = auth.reset_classifications_for_reclassification(1, "batch-2026-11-10")
        self.assertEqual(result["reset"], 1)
        self.assertEqual(result["archived"], 1)
        record = auth.classification_list("Previously Classified Co")[0]
        self.assertEqual(record["industry"], "")
        self.assertEqual(auth.classification_history_count(), 1)
        self.assertEqual(auth.pending_classification_names()[0]["company_name"], "Previously Classified Co")
        self.assertEqual(auth.classification_reset_preview(), {"total": 1, "already_pending": 1})
        with self.assertRaisesRegex(ValueError, "already been applied"):
            auth.reset_classifications_for_reclassification(1, "batch-2026-11-10")


if __name__ == "__main__":
    unittest.main()
