"""Regression coverage for compact, unambiguous classification-to-shipment mappings."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import main


class ClassificationMappingTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE classifications (
            company_name TEXT, industry TEXT, country TEXT,
            confidence TEXT, source TEXT
        )""")
        self.db.executemany(
            "INSERT INTO classifications VALUES (?,?,?,?,?)",
            [
                ("Alpha Motors", "Automotive", "India", "high", "official site"),
                ("Beta Pharma", "Pharma", "India", "medium", "company profile"),
                ("Ambiguous Co", "Automotive", "India", "high", "source A"),
                ("Ambiguous Co", "Chemicals", "India", "low", "source B"),
                ("Blank Co", "", "India", "low", "unverified"),
            ],
        )
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_selected_vertical_returns_only_its_unambiguous_mapping(self):
        @contextmanager
        def connection():
            yield self.db

        with patch.object(main.auth, "connection", connection):
            result = main.classification_mapping("Automotive", include_evidence=True)

        self.assertEqual([row["company_name"] for row in result], ["Alpha Motors"])
        self.assertEqual(result[0]["industry"], "Automotive")
        self.assertEqual(result[0]["country"], "India")
        self.assertEqual(result[0]["confidence"], "high")
        self.assertEqual(result[0]["source"], "official site")

    def test_all_verticals_excludes_cross_vertical_ambiguity_and_blank_industry(self):
        @contextmanager
        def connection():
            yield self.db

        with patch.object(main.auth, "connection", connection):
            result = main.classification_mapping()

        self.assertEqual(
            {(row["company_name"], row["industry"]) for row in result},
            {("Alpha Motors", "Automotive"), ("Beta Pharma", "Pharma")},
        )

    def test_selected_vertical_does_not_include_other_verticals(self):
        @contextmanager
        def connection():
            yield self.db

        with patch.object(main.auth, "connection", connection):
            result = main.classification_mapping("Pharma")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["industry"], "Pharma")


if __name__ == "__main__":
    unittest.main()
