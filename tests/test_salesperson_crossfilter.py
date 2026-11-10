"""Salesperson report must honour the same filters as industry reporting."""
import unittest
from main import dashboard_filters
from app.crossfilter import conditions


class SalespersonCrossFilterTests(unittest.TestCase):
    def test_salesperson_filter_payload_includes_all_shared_filters(self):
        filters = dashboard_filters(origin="Mumbai", destination="Dubai",
            shipper="Acme", consignee="Buyer Ltd", branch="West",
            start="2026-01-01", end="2026-01-31")
        where, params = conditions(["NG"], ["AE"], filters)
        for fragment in ("origin=ANY(:f_origin)", "destination=ANY(:f_destination)",
            "shipper=ANY(:f_shipper)", "consignee=ANY(:f_consignee)",
            "branch=ANY(:f_branch)", "shipment_date >= :start", "shipment_date <= :end"):
            self.assertIn(fragment, where)
        self.assertEqual(params["f_origin"], ["Mumbai"])
        self.assertEqual(params["f_destination"], ["Dubai"])
        self.assertEqual(params["f_shipper"], ["Acme"])
        self.assertEqual(params["f_consignee"], ["Buyer Ltd"])
        self.assertEqual(params["f_branch"], ["West"])


if __name__ == "__main__":
    unittest.main()
