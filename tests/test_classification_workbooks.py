"""Regression tests for the self-service classification workbooks."""
import unittest
from io import BytesIO
from openpyxl import load_workbook

from app.excel_tools import classification_template, parse_classification_xlsx
from app.industry_master import INDUSTRY_PROMPT, INDUSTRY_VERTICALS


class ClassificationWorkbookTests(unittest.TestCase):
    def test_template_has_import_sheet_then_ai_prompt_sheet(self):
        payload = classification_template()
        wb = load_workbook(BytesIO(payload), data_only=True)
        self.assertEqual(wb.sheetnames, ["Classification import", "AI Prompt"])
        self.assertEqual(wb.active.title, "Classification import")
        prompt = str(wb["AI Prompt"]["A2"].value)
        self.assertIn(INDUSTRY_PROMPT, prompt)
        self.assertEqual([wb["AI Prompt"].cell(row=i, column=2).value for i in range(2, 17)], list(INDUSTRY_VERTICALS))
        self.assertIn("IndustryVerticals", wb.defined_names)
        validation = wb["Classification import"].data_validations.dataValidation[0]
        self.assertEqual(validation.formula1, "=IndustryVerticals")
        self.assertEqual(validation.sqref, "B2:B50001")

    def test_import_reads_first_sheet_and_ignores_prompt_sheet(self):
        payload = classification_template()
        rows, skipped = parse_classification_xlsx(payload)
        self.assertEqual(skipped, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], INDUSTRY_VERTICALS[0])


    def test_compact_five_column_import_requires_confidence_and_evidence(self):
        from io import BytesIO
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Pending classification"
        ws.append(["company_name", "industry", "confidence", "source", "country"])
        ws.append(["Classified Co", INDUSTRY_VERTICALS[0], "HIGH", "https://example.com/company", "India"])
        ws.append(["Pending Co", "", "", "Awaiting evidence", "UAE"])
        out = BytesIO()
        wb.save(out)
        rows, skipped = parse_classification_xlsx(out.getvalue())
        self.assertEqual(skipped, 1)
        self.assertEqual(rows, [("Classified Co", INDUSTRY_VERTICALS[0], "high", "https://example.com/company", "India")])

    def test_import_rejects_extra_columns_or_wrong_sheet(self):
        from io import BytesIO
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Classification import"
        ws.append(["company_name", "industry", "confidence", "source", "country"])
        out = BytesIO()
        wb.save(out)
        with self.assertRaisesRegex(ValueError, "Pending classification"):
            parse_classification_xlsx(out.getvalue())



if __name__ == "__main__":
    unittest.main()
