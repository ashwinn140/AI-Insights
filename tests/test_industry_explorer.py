"""Pure scope contract tests; no production credentials required."""
import unittest
from app.industry_explorer import validate_scope

class ScopeTests(unittest.TestCase):
    def test_valid_scope(self):
        self.assertEqual(validate_scope(["NG"],["AE"]), (["NG"],["AE"]))
    def test_invalid_company(self):
        with self.assertRaises(ValueError):
            validate_scope(["NG","OTHER"],["AE"])
    def test_invalid_lob(self):
        with self.assertRaises(ValueError):
            validate_scope(["NG"],["FINANCE"])
    def test_empty_scope_denied(self):
        with self.assertRaises(ValueError):
            validate_scope([],["AE"])
    def test_no_implicit_all(self):
        with self.assertRaises(ValueError):
            validate_scope(["NG"],[])
if __name__ == "__main__":
    unittest.main()
