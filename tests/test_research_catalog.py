import unittest
from io import BytesIO
from openpyxl import Workbook
from app.research_catalog import parse_research

class ResearchCatalogTests(unittest.TestCase):
    def workbook(self,rows):
        wb=Workbook()
        ws=wb.active;ws.title="Final Classification Master"
        ws.append(["Entity Key","Original Company Name","Primary Industry","Verification Status","Evidence URL"])
        for r in rows: ws.append(r)
        out=BytesIO();wb.save(out);return out.getvalue()
    def test_preserve_evidence_and_uncertainty(self):
        rows=parse_research(self.workbook([
            ["CE-001","Example Ltd","Unknown / Requires Verification","Provisional — Needs Review",None],
            ["CE-002","Verified Ltd","Manufacturing","Verified — Exact Entity","https://example.com"]]))
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["verification_status"],"Provisional — Needs Review")
        self.assertEqual(rows[1]["evidence_url"],"https://example.com")
    def test_duplicate_keys_fail(self):
        with self.assertRaises(ValueError):
            parse_research(self.workbook([
                ["CE-001","A","Manufacturing","Verified — Exact Entity",None],
                ["CE-001","B","Manufacturing","Verified — Exact Entity",None]]))
if __name__=="__main__":unittest.main()
