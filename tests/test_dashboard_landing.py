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
        self.assertIn("location.replace('/')", source)


if __name__ == "__main__":
    unittest.main()


    def test_discovery_pages_remain_in_primary_navigation():
        source = Path("app/ui.js").read_text()
        assert "location.replace('/classifications')" not in source
        assert "link.getAttribute('href')" in source
        assert "['/companies','/opportunities'].includes" not in source
