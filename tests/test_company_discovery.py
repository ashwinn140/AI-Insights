"""Regression tests for company discovery result limits and export caps."""
import unittest
from app.company_discovery import search_companies, opportunity_candidates


class FakeResult:
    def mappings(self):
        return self
    def __iter__(self):
        return iter([])


class FakeConnection:
    def __init__(self):
        self.params = None
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, query, params):
        self.params = params
        return FakeResult()


class FakeEngine:
    def __init__(self):
        self.connection = FakeConnection()
    def connect(self):
        return self.connection


class CompanyDiscoveryLimitTests(unittest.TestCase):
    def test_company_search_limit_is_capped_at_ten_thousand(self):
        engine = FakeEngine()
        search_companies(engine, companies=["NG"], lobs=["AE"], limit=50000)
        self.assertEqual(engine.connection.params["limit"], 10000)

    def test_opportunity_limit_is_capped_at_ten_thousand(self):
        engine = FakeEngine()
        opportunity_candidates(engine, companies=["NG"], lobs=["AE"], limit=50000)
        self.assertEqual(engine.connection.params["limit"], 10000)

    def test_limits_cannot_be_zero_or_negative(self):
        for fn in (search_companies, opportunity_candidates):
            for limit in (0, -10):
                engine = FakeEngine()
                fn(engine, companies=["NG"], lobs=["AE"], limit=limit)
                self.assertEqual(engine.connection.params["limit"], 1)


if __name__ == "__main__":
    unittest.main()
