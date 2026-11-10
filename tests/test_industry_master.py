import unittest
from app.industry_master import INDUSTRY_VERTICALS, validate_industry, INDUSTRY_PROMPT

class IndustryMasterTests(unittest.TestCase):
    def test_exactly_fifteen_unique_labels(self):
        self.assertEqual(len(INDUSTRY_VERTICALS), 15)
        self.assertEqual(len(set(INDUSTRY_VERTICALS)), 15)

    def test_only_exact_labels_are_accepted(self):
        for label in INDUSTRY_VERTICALS:
            self.assertTrue(validate_industry(label))
        self.assertFalse(validate_industry("Automotive"))
        self.assertFalse(validate_industry("Logistics"))
        self.assertFalse(validate_industry("Other"))

    def test_prompt_contains_all_categories_and_no_open_category(self):
        for label in INDUSTRY_VERTICALS:
            self.assertIn(label, INDUSTRY_PROMPT)
        self.assertIn("leave industry blank", INDUSTRY_PROMPT.lower())

if __name__ == "__main__":
    unittest.main()
