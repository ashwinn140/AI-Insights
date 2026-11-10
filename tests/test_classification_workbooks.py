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


if __name__ == "__main__":
    unittest.main()
