"""Regression checks for the operations dashboard landing route."""
import unittest
from pathlib import Path


class DashboardLandingTests(unittest.TestCase):
    def test_authenticated_root_renders_dashboard_instead_of_redirecting(self):
        source = Path("app/industry_explorer.html").read_text()
        show = source[source.index("async function show()"):source.index("$('loginform')")]
        self.assertIn("identity=await api('/auth/me')", show)
        self.assertIn("$('app').classList.remove('hide')", show)
        self.assertNotIn("location.replace('/classifications')", show)

    def test_successful_login_returns_to_operations_dashboard(self):
        source = Path("app/industry_explorer.html").read_text()
        self.assertIn("location.replace('/classifications')", source)


    def test_discovery_pages_remain_in_primary_navigation(self):
        source = Path("app/ui.js").read_text()
        assert "location.replace('/classifications')" not in source
        assert "a.getAttribute('href')" in source
        assert "['/companies','/opportunities'].includes" not in source

    def test_guide_route_and_business_outcome_indicators_are_wired(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        main = (root / "main.py").read_text()
        guide = (root / "app" / "guide.html").read_text()
        ui = (root / "app" / "ui.js").read_text()
        home = (root / "app" / "industry_explorer.html").read_text()
        self.assertIn('@app.get("/guide"', main)
        self.assertIn('Business outcomes', guide)
        self.assertIn('Financial boundary', guide)
        self.assertIn('addBusinessIndicators', ui)
        self.assertIn('Guide & Business Outcomes', ui)
        self.assertIn('/assets/ui.js?v=3', home)


if __name__ == "__main__":
    unittest.main()
