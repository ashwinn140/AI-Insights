from pathlib import Path
import unittest


ROOT = Path(__file__).parents[1]


class ShipmentInsightsPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "app" / "classifications.html").read_text()
        cls.main = (ROOT / "main.py").read_text()

    def test_shipment_insights_are_expanded_by_default(self):
        self.assertIn('id="shipment-trend"><div class="ai-section-heading"', self.html)
        self.assertNotIn('id="shipment-trend"><details', self.html)

    def test_heavy_insights_start_after_first_paint(self):
        self.assertIn("requestIdleCallback(startRefresh,{timeout:1200})", self.html)
        self.assertIn("setTimeout(startRefresh,250)", self.html)
        self.assertNotIn("updateAttribution();applyPeriod();await refreshIndustryViews();", self.html)

    def test_primary_trend_is_rendered_before_secondary_comparison(self):
        self.assertIn("compareTrendPeriods(total).catch(()=>{})", self.html)
        self.assertLess(self.html.index("await run('Industry trends',shipmentTrend)"),
                        self.html.index("await run('Contributor filters',contributorFilterOptions)"))

    def test_trend_query_filters_and_projects_narrow_rows_before_mapping(self):
        start = self.main.index('@app.get("/api/classifications/shipment-trend")')
        end = self.main.index('@app.get("/api/classifications/vertical-performance")', start)
        route = self.main[start:end]
        self.assertIn("scoped_shipments AS MATERIALIZED", route)
        self.assertIn("WHERE {where} AND s.shipment_date IS NOT NULL", route)
        self.assertIn("s.industry_party", route)
        self.assertIn("SET LOCAL statement_timeout = '20000'", route)


if __name__ == "__main__":
    unittest.main()
