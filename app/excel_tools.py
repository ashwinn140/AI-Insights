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
    if len(payload)>20*1024*1024: raise ValueError("Excel file exceeds 20 MB")
    try: wb=load_workbook(BytesIO(payload),read_only=True,data_only=True)
    except Exception: raise ValueError("Invalid XLSX workbook")
    ws=wb.active
    iterator=ws.iter_rows(values_only=True)
    header=next(iterator,None)
    expected=["company_name","industry","confidence","source"]
    if not header or [str(x or "").strip().lower() for x in header[:4]]!=expected:
        raise ValueError("Expected columns: "+", ".join(expected))
    header_names=[str(x or "").strip().lower() for x in header]
    country_index=header_names.index("country") if "country" in header_names else None
    rows=[]
    skipped=0
    for n,row in enumerate(iterator,2):
        if n>50001: raise ValueError("Maximum 50,000 rows per import")
        if not any(x is not None for x in row): continue
        if len(row)<4: raise ValueError(f"Row {n}: missing columns")
        name,industry,confidence,source=row[:4]
        if not isinstance(name,str) or not name.strip():
            raise ValueError(f"Row {n}: invalid company name")
        country=row[country_index] if country_index is not None and len(row)>country_index else ""
        if country is None: country=""
        if not isinstance(country,str): raise ValueError(f"Row {n}: country must be text")
        # Unresolved research rows remain pending; never manufacture an industry.
        if industry is None or not str(industry).strip():
            skipped+=1
            continue
        if not all(isinstance(x,str) for x in (industry,confidence,source)):
            raise ValueError(f"Row {n}: classified rows require text industry, confidence and source")
        if not validate_industry(industry):
            raise ValueError(f"Row {n}: industry must exactly match one of the 15 industry verticals")
        rows.append((name,industry,confidence.strip().lower(),source,country))
    return rows,skipped

def classification_workbook_with_prompt(sheets, import_sheet_title):
    """Add canonical research instructions and the 15-industry dropdown."""
    payload=workbook_bytes(sheets)
    wb=load_workbook(BytesIO(payload))
    if "AI Prompt" not in wb.sheetnames:
        ws=wb.create_sheet("AI Prompt", 1)
        ws.append(["Instructions"])
        ws.append(["Complete Sheet 1 only. Preserve every organisation and every column. Use only the exact 15 industry verticals. Use company-specific evidence; shipper/consignee appearances and salesperson/job-owner context are clues, not proof. Leave uncertain industries blank. Include a verifiable URL or specific evidence note for every classified row. Do not copy this prompt elsewhere.\n\n"+INDUSTRY_PROMPT])
        ws.column_dimensions["A"].width=120
        ws["A1"].font=Font(bold=True,color="FFFFFF")
        ws["A1"].fill=PatternFill("solid",fgColor="193557")
        ws["A2"].alignment=Alignment(wrap_text=True,vertical="top")
        ws.row_dimensions[2].height=360
    if "Industry Master" in wb.sheetnames: del wb["Industry Master"]
    master=wb.create_sheet("Industry Master")
    for label in INDUSTRY_VERTICALS: master.append([label])
    master.sheet_state="hidden"
    wb.defined_names.add(DefinedName("IndustryVerticals",attr_text="'Industry Master'!$A$1:$A$15"))
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
