"""Excel import/export for operational analytics and independent classifications."""
from io import BytesIO
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.workbook.defined_name import DefinedName
from app.industry_master import INDUSTRY_VERTICALS, INDUSTRY_PROMPT, validate_industry

def safe_cell(value):
    if isinstance(value,str) and value.lstrip().startswith(("=","+","-","@")):
        return "'"+value
    return value

def workbook_bytes(sheets):
    wb=Workbook()
    wb.remove(wb.active)
    for title,columns,rows in sheets:
        ws=wb.create_sheet(title[:31])
        ws.append(columns)
        for row in rows:
            ws.append([safe_cell(v) for v in row])
        ws.freeze_panes="A2"
        ws.auto_filter.ref=ws.dimensions
        for cell in ws[1]:
            cell.font=Font(bold=True,color="FFFFFF")
            cell.fill=PatternFill("solid",fgColor="193557")
            cell.alignment=Alignment(wrap_text=True)
        for i,column in enumerate(columns,1):
            ws.column_dimensions[get_column_letter(i)].width=min(45,max(14,len(column)+5))
    out=BytesIO()
    wb.save(out)
    return out.getvalue()

def analytics_export(data):
    o=data["overview"]
    sheets=[("Overview",["Metric","Value"],[(k,v) for k,v in o.items()])]
    for title,key,columns,fields in [
        ("Departments","breakdown",["Company","Department","Shipments"],["company","report_type","shipments"]),
        ("Trade lanes","lanes",["Origin","Destination","Shipments"],["origin","destination","shipments"]),
        ("Companies","participants",["Role","Company name","Appearances"],["role","name","appearances"]),
        ("Monthly trend","trend",["Month","Shipments"],["month","shipments"]),
        ("Branches","branches",["Branch","Shipments"],["branch","shipments"])]:
        sheets.append((title,columns,[[r.get(k) for k in fields] for r in data[key]]))
    sheets.append(("Applied filters",["Filter","Value"],[(k,str(v)) for k,v in data["filters"].items()]))
    return workbook_bytes(sheets)

def parse_classification_xlsx(payload):
    """Parse the compact five-column workbook; blank rows remain pending."""
    if len(payload)>20*1024*1024:
        raise ValueError("Excel file exceeds 20 MB")
    try:
        wb=load_workbook(BytesIO(payload),read_only=True,data_only=True)
    except Exception:
        raise ValueError("Invalid XLSX workbook")
    try:
        if "Pending classification" not in wb.sheetnames:
            raise ValueError('Expected worksheet: "Pending classification"')
        ws=wb["Pending classification"]
        iterator=ws.iter_rows(values_only=True)
        header=next(iterator,None)
        expected=["company_name","industry","confidence","source","country"]
        if not header or [str(x or "").strip().lower() for x in header[:5]]!=expected or len(header)!=5:
            raise ValueError("Expected exactly five columns: "+", ".join(expected))
        rows=[]
        skipped=0
        seen=set()
        for n,row in enumerate(iterator,2):
            if n>50001:
                raise ValueError("Maximum 50,000 rows per import")
            if not any(x is not None for x in row):
                continue
            if len(row)<5:
                raise ValueError(f"Row {n}: missing columns")
            name,industry,confidence,source,country=row[:5]
            if not isinstance(name,str) or not name.strip():
                raise ValueError(f"Row {n}: invalid company name")
            if country is not None and not isinstance(country,str):
                raise ValueError(f"Row {n}: country must be text")
            # Blank industry means "not classified this cycle" and is a no-op.
            if industry is None or not str(industry).strip():
                skipped+=1
                continue
            if not isinstance(industry,str) or not validate_industry(industry):
                raise ValueError(f"Row {n}: industry must exactly match one of the 15 industry verticals")
            if not isinstance(confidence,str) or confidence.strip().lower() not in ("low","medium","high"):
                raise ValueError(f"Row {n}: confidence must be low, medium or high")
            if not isinstance(source,str) or len(source.strip())<3:
                raise ValueError(f"Row {n}: classified rows require evidence or a source URL")
            key=name.strip().casefold()
            if key in seen:
                raise ValueError(f"Row {n}: duplicate company name; keep one row per organisation")
            seen.add(key)
            rows.append((name.strip(),industry.strip(),confidence.strip().lower(),source.strip(),(country or "").strip()))
        return rows,skipped
    finally:
        wb.close()

def classification_workbook_with_prompt(sheets, import_sheet_title):
    """Add canonical research instructions and the 15-industry dropdown."""
    payload=workbook_bytes(sheets)
    wb=load_workbook(BytesIO(payload))
    if "AI Prompt" not in wb.sheetnames:
        ws=wb.create_sheet("AI Prompt", 1)
        ws.append(["Instructions"])
        ws.append(["Follow the provider-neutral classification instructions below. Edit only industry, confidence and source in the first worksheet. Preserve company_name, country, row order, all rows and the five-column format. Leave uncertain or out-of-scope industries blank and explain why in source.\n\n"+INDUSTRY_PROMPT])
        ws.column_dimensions["A"].width=120
        ws["A1"].font=Font(bold=True,color="FFFFFF")
        ws["A1"].fill=PatternFill("solid",fgColor="193557")
        ws["A2"].alignment=Alignment(wrap_text=True,vertical="top")
        ws.row_dimensions[2].height=360
    prompt=wb["AI Prompt"]
    prompt.column_dimensions["A"].width=120
    prompt["A1"].font=Font(bold=True,color="FFFFFF")
    prompt["A1"].fill=PatternFill("solid",fgColor="193557")
    if prompt.max_row>=2:
        prompt["A2"].alignment=Alignment(wrap_text=True,vertical="top")
        prompt.row_dimensions[2].height=420
    # Keep the workbook to exactly two visible sheets. Store the dropdown
    # source on Sheet 2 (AI Prompt), not in a redundant third worksheet.
    for name in list(wb.sheetnames):
        if name != import_sheet_title and name != "AI Prompt":
            del wb[name]
    prompt["B1"]="Industry master (exact allowed values)"
    prompt["B1"].font=Font(bold=True,color="FFFFFF")
    prompt["B1"].fill=PatternFill("solid",fgColor="193557")
    prompt.column_dimensions["B"].width=48
    for row,label in enumerate(INDUSTRY_VERTICALS,2):
        prompt.cell(row=row,column=2,value=label)
    wb.defined_names.add(DefinedName("IndustryVerticals",attr_text="'AI Prompt'!$B$2:$B$16"))
    ws=wb[import_sheet_title]
    validation=DataValidation(type="list",formula1="=IndustryVerticals",allow_blank=True)
    validation.error="Select one of the 15 industry verticals."
    validation.errorTitle="Invalid industry"
    validation.showErrorMessage=True
    ws.add_data_validation(validation)
    validation.add("B2:B50001")
    out=BytesIO(); wb.save(out); return out.getvalue()

def classification_template():
    return classification_workbook_with_prompt([
        ("Classification import",["company_name","industry","confidence","source","country"],
         [["Example Company",INDUSTRY_VERTICALS[0],"medium","Verified source reference","India"]])
    ],"Classification import")
