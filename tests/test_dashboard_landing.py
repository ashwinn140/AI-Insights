"""Regression checks for the operations and classification landing routes."""
import unittest
from pathlib import Path


class DashboardLandingTests(unittest.TestCase):
    def test_root_route_uses_industry_classification_as_default_home(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / "main.py").read_text()
        self.assertIn('@app.get("/", response_class=HTMLResponse)', main)
        self.assertIn('return Path(__file__).parent.joinpath("app/classifications.html").read_text()', main)
        self.assertIn('@app.get("/operations", response_class=HTMLResponse)', main)

    def test_operations_overview_remains_available_at_operations_route(self):
        main = (Path(__file__).resolve().parents[1] / "main.py").read_text()
        self.assertIn('def operations_page(user=Depends(current_user)):', main)
        self.assertIn('joinpath("app/industry_explorer.html")', main)

    def test_classification_register_is_excel_only_in_browser(self):
        html = (Path(__file__).resolve().parents[1] / "app" / "classifications.html").read_text()
        register = html[html.index('<div id="register"'):html.index("<script>")]
        self.assertNotIn("<table", register)
        self.assertIn("/api/classifications/export", register)
        script = html[html.rindex("<script>") + len("<script>"):html.rindex("</script>")]
        self.assertNotIn("api('/api/classifications?", script)
        self.assertNotIn("registerPage", script)

    def test_lookup_endpoint_registered_before_generic_api_fallback(self):
        main = (Path(__file__).resolve().parents[1] / "main.py").read_text()
        self.assertLess(main.index('@app.get("/api/classifications/lookup")'),
                        main.index('@app.get("/api/{path:path}")'))

    def test_manual_classification_lookup_and_save_are_wired(self):
        root = Path(__file__).resolve().parents[1]
        main = (root / "main.py").read_text()
        html = (root / "app" / "classifications.html").read_text()
        self.assertIn('@app.get("/api/classifications/lookup")', main)
        self.assertIn("def classification_lookup(", main)
        self.assertIn("/api/classifications/lookup?", html)
        self.assertIn("/api/classifications/save", html)
        self.assertIn("Add / change industry classification", html)

    def test_visual_drilldown_rows_can_cross_filter_other_views(self):
        html = (Path(__file__).resolve().parents[1] / "app" / "classifications.html").read_text()
        self.assertIn("function applyVerticalCrossFilter(kind,item)", html)
        self.assertIn("refreshIndustryViews();", html)
        self.assertIn("ai-crossfilter-choice", html)


if __name__ == "__main__":
    unittest.main()
