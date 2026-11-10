"""Regression coverage for the compact pending-classification workbook."""
from io import BytesIO
from openpyxl import load_workbook
from app.excel_tools import classification_workbook_with_prompt
from app.industry_master import INDUSTRY_PROMPT


def test_pending_classification_workbook_keeps_only_required_update_fields():
    payload = classification_workbook_with_prompt([
        ("Pending classification",
         ["company_name", "industry", "confidence", "source", "country"],
         [["Example Co", "", "", "", "India"]]),
        ("AI Prompt", ["Instructions"],
         [["Keep company_name and existing country unchanged. Update only industry, confidence and source.\n\n" + INDUSTRY_PROMPT]])
    ], "Pending classification")
    wb = load_workbook(BytesIO(payload), data_only=True)
    ws = wb["Pending classification"]
    assert [cell.value for cell in ws[1]] == [
        "company_name", "industry", "confidence", "source", "country"
    ]
    assert ws.max_column == 5
    assert ws["A2"].value == "Example Co"
    assert ws["E2"].value == "India"
    assert "Keep company_name and existing country unchanged" in wb["AI Prompt"]["A2"].value
