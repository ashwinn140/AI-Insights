"""Regression checks for safe filtering, Excel and independent admin scope."""
import unittest
from io import BytesIO
from openpyxl import load_workbook
from app.crossfilter import conditions
from app.excel_tools import analytics_export,parse_classification_xlsx,classification_template

class CrossFilterTests(unittest.TestCase):
    def test_scope_is_required(self):
        with self.assertRaises(ValueError):
            conditions([],["AE"],{})
    def test_all_filters_parameterized(self):
        where,params=conditions(["NG"],["AE"],{"origin":"Mumbai","shipper":"Acme","start":"2026-01-01"})
        self.assertIn("origin=ANY(:f_origin)",where)
        self.assertIn("shipper=ANY(:f_shipper)",where)
        self.assertNotIn("Acme",where)
        self.assertEqual(params["f_shipper"],["Acme"])
    def test_multi_select(self):
        where,params=conditions(["NG","NCS"],["AE","AI"],{"origin":"Mumbai,Hong Kong"})
        self.assertEqual(params["f_origin"],["Mumbai","Hong Kong"])
        self.assertIn("origin=ANY(:f_origin)",where)

    def test_inverted_date_range(self):
        with self.assertRaisesRegex(ValueError, "Start date"):
            conditions(["NG"],["AE"],{"start":"2026-11-10","end":"2026-11-01"})
    def test_invalid_date(self):
        with self.assertRaises(ValueError):
            conditions(["NG"],["AE"],{"start":"yesterday"})
    def test_unknown_scope(self):
        with self.assertRaises(ValueError):
            conditions(["NG","OTHER"],["AE"],{})

    def test_checkbox_filter_allows_250_values(self):
        values=[f"Party {i}" for i in range(250)]
        import json
        where,params=conditions(["NG"],["AE"],{"shipper":"j:"+json.dumps(values)})
        self.assertIn("shipper=ANY(:f_shipper)",where)
        self.assertEqual(len(params["f_shipper"]),250)

    def test_checkbox_filter_rejects_more_than_250_values(self):
        values=[f"Party {i}" for i in range(251)]
        import json
        with self.assertRaisesRegex(ValueError,"Too many"):
            conditions(["NG"],["AE"],{"shipper":"j:"+json.dumps(values)})

    def test_malformed_checkbox_filter_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"Invalid filter"):
            conditions(["NG"],["AE"],{"shipper":"j:{bad json"})

class ExcelTests(unittest.TestCase):
    def test_template_roundtrip(self):
        rows,skipped=parse_classification_xlsx(classification_template())
        self.assertEqual(skipped,0)
        self.assertEqual(rows[0][0],"Example Company")
        self.assertEqual(rows[0][1],"Automotive & Auto Components")
        self.assertEqual(rows[0][4], "India")
    def test_export_tabs(self):
        data={"overview":{"shipments":1,"shippers":1,"consignees":1,"teus":0,"gross_weight":0},
              "breakdown":[{"company":"NG","report_type":"AE","shipments":1}],
              "lanes":[],"participants":[],"trend":[],"branches":[],"filters":{}}
        wb=load_workbook(BytesIO(analytics_export(data)),read_only=True)
        self.assertIn("Trade lanes",wb.sheetnames)
        self.assertIn("Applied filters",wb.sheetnames)
    def test_formula_injection_escaped(self):
        data={"overview":{"shipments":"=1+1"},"breakdown":[],"lanes":[],
              "participants":[],"trend":[],"branches":[],"filters":{}}
        wb=load_workbook(BytesIO(analytics_export(data)))
        self.assertEqual(wb["Overview"]["B2"].data_type,"s")

if __name__=="__main__":
    unittest.main()
