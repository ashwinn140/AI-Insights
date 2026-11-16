"""Regression tests for server-rendered industry selectors and direct all-industry export."""
import unittest
from html import escape
from unittest.mock import MagicMock, patch

import main
from app.industry_master import INDUSTRY_PROMPT, INDUSTRY_VERTICALS


class IndustrySelectorAndExportTests(unittest.TestCase):
    def test_both_industry_selectors_render_from_the_canonical_master(self):
        page = main.render_classification_page()
        self.assertNotIn("INDUSTRY_OPTIONS", page)
        self.assertNotIn("CONTRIBUTOR_INDUSTRY_OPTIONS", page)
        for industry in INDUSTRY_VERTICALS:
            option = f'value="{escape(industry, quote=True)}">{escape(industry)}</option>'
            self.assertEqual(page.count(option), 2, industry)
        self.assertIn('value="Unclassified">Unclassified</option>', page)

    def test_excel_prompt_and_validation_share_the_canonical_industry_master(self):
        for industry in INDUSTRY_VERTICALS:
            self.assertIn(industry, INDUSTRY_PROMPT)
        self.assertNotIn('15-value master', INDUSTRY_PROMPT)
        self.assertNotIn('exact 15 labels', INDUSTRY_PROMPT)


    def test_classification_page_has_no_stale_dom_bindings_that_abort_startup(self):
        from pathlib import Path
        import re

        page = Path("app/classifications.html").read_text()
        ids = set(re.findall(r'\\bid=["\\']([^"\\']+)["\\']', page))
        refs = set(re.findall(r"\\$\\(['\\"]([^'\\"]+)['\\"]\\)", page))
        self.assertEqual(refs - ids, set(), "Every static DOM lookup must have a matching element")
        self.assertNotIn("$('search').onclick=load", page)
        self.assertNotIn("$('q').onkeydown", page)
        self.assertNotIn("Promise.all([load(),industryStatus(),refreshIndustryViews()])", page)
        self.assertNotIn("function renderShipmentRows(rows)", page)
        self.assertLess(page.index("initContributorIndustrySelector();"),
                        page.index("api('/auth/me').then"))

    def test_contributor_export_needs_no_industry_selection_or_refresh(self):
        record = {
            "shipment_key": "JOB-001",
            "shipment_date": None,
            "company": "Test Co",
            "report_type": "AE",
            "industry": INDUSTRY_VERTICALS[0],
            "shipper": "Example Manufacturer",
            "consignee": "Example Buyer",
            "origin": "Mumbai",
            "destination": "London",
            "branch": "Mumbai",
            "salesperson": "Sales One",
            "job_owner": "Owner One",
            "evidence": "https://example.com",
            "confidence": "high",
            "country": "India",
            "organisation": "Example Manufacturer",
            "contributor_role": "Shipper",
            "shipment_rows": 1,
            "distinct_shipments": 1,
            "distinct_related_parties": 1,
            "salesperson_count": 1,
            "salespersons": "Sales One",
            "job_owners": "Owner One",
            "industry_rank": 1,
        }
        engine = MagicMock()
        connection = MagicMock()
        engine.connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.mappings.return_value = [record]

        with patch.object(main, "allowed_scope", return_value=(["Test Co"], ["AE"])), \
             patch.object(main, "classification_mapping", return_value=[{
                 "company_name": "Example Manufacturer",
                 "industry": INDUSTRY_VERTICALS[0],
                 "country": "India",
                 "confidence": "high",
                 "source": "https://example.com",
             }]), \
             patch.object(main, "scoped_engine", return_value=engine), \
             patch.object(main, "workbook_bytes", return_value=b"xlsx") as workbook, \
             patch.object(main, "classification_contributors", side_effect=AssertionError("must not refresh")):
            response = main.classification_contributors_export(user={"id": 1})

        self.assertEqual(response.media_type, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("ai-insights-all-industry-contributors.xlsx", response.headers["content-disposition"])
        connection.execute.assert_called_once()
        sheets = workbook.call_args.args[0]
        self.assertEqual([sheet[0] for sheet in sheets], [
            "Calculation", "Top 10 Contributors", "Complete Contributor List",
            "Shipment records", "Applied filters",
        ])
        self.assertEqual(sheets[1][2][0][2], INDUSTRY_VERTICALS[0])
        self.assertEqual(sheets[3][2][0][0], "JOB-001")


if __name__ == "__main__":
    unittest.main()
