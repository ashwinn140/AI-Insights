"""Classification workbook prompt and import contract tests."""
import unittest
from io import BytesIO
from openpyxl import load_workbook
from app.excel_tools import classification_template, classification_workbook_with_prompt, parse_classification_xlsx
from app.industry_master import INDUSTRY_PROMPT, INDUSTRY_VERTICALS

class WorkbookPromptTests(unittest.TestCase):
    def test_standard_template_has_pending_sheet_prompt_and_dropdown(self):
        wb=load_workbook(BytesIO(classification_template()))
        self.assertEqual(wb.sheetnames,["Pending classification","AI Prompt"])
        self.assertIn(INDUSTRY_PROMPT,str(wb["AI Prompt"]["A2"].value))
        self.assertGreaterEqual(wb["AI Prompt"].column_dimensions["A"].width,100)
        self.assertTrue(wb["AI Prompt"]["A2"].alignment.wrap_text)
        self.assertEqual([wb["AI Prompt"].cell(row=i,column=2).value for i in range(2,17)],list(INDUSTRY_VERTICALS))
        self.assertEqual(wb["Pending classification"].data_validations.dataValidation[0].formula1,"=IndustryVerticals")
        for label in INDUSTRY_VERTICALS: self.assertIn(label,str(wb["AI Prompt"]["A2"].value))
    def test_pending_workbook_uses_same_prompt_and_import_parser(self):
        payload=classification_workbook_with_prompt([("Pending classification",
          ["company_name","industry","confidence","source","country"],
          [["Example Shipper","","","","India"]])],"Pending classification")
        wb=load_workbook(BytesIO(payload))
        self.assertEqual(wb.sheetnames,["Pending classification","AI Prompt"])
        self.assertIn(INDUSTRY_PROMPT,str(wb["AI Prompt"]["A2"].value))
        rows,skipped=parse_classification_xlsx(payload)
        self.assertEqual(rows,[])
        self.assertEqual(skipped,1)

if __name__=="__main__": unittest.main()