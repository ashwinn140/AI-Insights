import unittest
from app.classification_rules import Classification, normalize_company_name, select_classification

class ClassificationRulesTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_company_name("  ACME,  LTD. "), "acme ltd")
    def test_inferred_cannot_be_verified(self):
        with self.assertRaises(ValueError):
            Classification("ACME", "Automotive", "verified", "inferred", True)
    def test_manual_approval_protected(self):
        manual = Classification("ACME", "Automotive", "verified", "manual", True)
        researched = Classification("ACME", "Textiles", "probable", "research", True)
        self.assertIs(select_classification(manual, researched), manual)
    def test_unapproved_research_not_applied(self):
        proposed = Classification("ACME", "Textiles", "probable", "research", False)
        self.assertIsNone(select_classification(None, proposed))
if __name__ == "__main__":
    unittest.main()
