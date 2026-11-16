"""Regression checks for bounded contributor analytics query timeouts."""
import inspect
import unittest

import main


class ContributorQueryTimeoutTests(unittest.TestCase):
    def test_contributor_queries_get_a_targeted_25_second_timeout(self):
        source = inspect.getsource(main.classification_contributors)
        self.assertIn("SET LOCAL statement_timeout = '25000'", source)
        self.assertEqual(source.count("set_contributor_timeout(conn)"), 3)

    def test_global_database_timeout_remains_unchanged(self):
        source = inspect.getsource(main.scoped_engine)
        self.assertIn("statement_timeout=10000", source)
        self.assertNotIn("25000", source)


if __name__ == "__main__":
    unittest.main()
