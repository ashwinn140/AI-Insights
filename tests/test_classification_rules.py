import unittest
from app.classification_rules import Classification, normalize_company_name, select_classification

class ClassificationRulesTests(unittest.TestCase):
    def test_normalization(self):
        self.assertEqual(normalize_company_name("  ACME,  LTD. "), "acme ltd")
    def test_inferred_cannot_be_verified(self):
        with self.assertRaises(ValueError):
            Classification("ACME", "Automotive", "verified", "inferred")
    def test_manual_classification_protected_from_research_refresh(self):
        manual = Classification("ACME", "Automotive", "verified", "manual")
        researched = Classification("ACME", "Textiles", "probable", "research")
        self.assertIs(select_classification(manual, researched), manual)
    def test_research_candidate_can_be_applied_without_approval(self):
        proposed = Classification("ACME", "Textiles", "probable", "research")
        self.assertIs(select_classification(None, proposed), proposed)
if __name__ == "__main__":
    unittest.main()
