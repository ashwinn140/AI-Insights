"""Regression checks for classification analytics reliability fixes."""
from pathlib import Path
import inspect
import unittest

import main


class ClassificationReliabilityTests(unittest.TestCase):
    def test_contributor_export_has_bounded_timeout_and_timing_diagnostics(self):
        source = inspect.getsource(main.classification_contributors_export)
        self.assertIn("SET LOCAL statement_timeout = '25000'", source)
        self.assertIn("Contributor workbook export query completed", source)
        self.assertIn("elapsed_ms", source)

    def test_vertical_drilldown_has_bounded_timeout(self):
        source = inspect.getsource(main.vertical_performance)
        self.assertIn("SET LOCAL statement_timeout = '20000'", source)

    def test_global_database_timeout_is_not_relaxed(self):
        source = inspect.getsource(main.scoped_engine)
        self.assertIn("statement_timeout=10000", source)
        self.assertNotIn("25000", source)
        self.assertNotIn("20000", source)

    def test_refresh_requests_share_the_inflight_promise(self):
        page = Path("app/classifications.html").read_text()
        self.assertIn("let refreshInProgress=false,refreshPromise=null", page)
        self.assertIn("if(refreshPromise)return refreshPromise", page)
        self.assertIn("return refreshPromise}", page)

    def test_register_search_ignores_stale_responses(self):
        page = Path("app/classifications.html").read_text()
        self.assertIn("registerSearchSequence", page)
        self.assertIn("sequence!==registerSearchSequence", page)
        self.assertIn("q!==$('register-search').value.trim()", page)


    def test_counterparty_crossfilter_uses_the_opposite_party_field(self):
        page = Path("app/classifications.html").read_text()
        self.assertIn("if(role==='shipper')target='consignee'", page)
        self.assertIn("else if(role==='consignee')target='shipper'", page)
        self.assertIn("exportsOnly=lob.length>0&&lob.every", page)
        self.assertIn("importsOnly=lob.length>0&&lob.every", page)
        self.assertIn("Select only export or only import departments", page)

    def test_save_success_is_not_misreported_as_save_failure_on_refresh_error(self):
        page = Path("app/classifications.html").read_text()
        self.assertIn("Classification was saved, but dashboard refresh failed:", page)
        self.assertIn("Save failed:", page)


    def test_refresh_status_reports_partial_failures_instead_of_false_success(self):
        page = Path("app/classifications.html").read_text()
        self.assertIn("return false", page[page.index("async function contributorFilterOptions"):page.index("async function shipmentTrend")])
        self.assertIn("return false", page[page.index("async function shipmentTrend"):page.index("async function verticalDetail")])
        self.assertIn("return false", page[page.index("async function verticalDetail"):page.index("async function contributorRecords")])
        self.assertIn("return false", page[page.index("async function salespersonIndustry"):page.index("$('sales-prev').onclick")])
        self.assertIn("if(ok===false)outcomes.push(label)", page)
        self.assertIn("Refresh incomplete · ", page)
        self.assertIn("return {ok:outcomes.length===0,failed:outcomes}", page)

    def test_complete_inline_javascript_passes_node_syntax_check(self):
        import re
        import shutil
        import subprocess
        import tempfile

        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js is not installed")
        page = Path("app/classifications.html").read_text()
        scripts = re.findall(r"<script\\b[^>]*>([\\s\\S]*?)</script>", page, re.IGNORECASE)
        self.assertTrue(scripts)
        for script in scripts:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", encoding="utf-8") as handle:
                handle.write(script)
                handle.flush()
                subprocess.run([node, "--check", handle.name], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
