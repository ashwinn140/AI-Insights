"""Excel import/export for operational analytics and independent classifications."""
from io import BytesIO
from openpyxl import Workbook,load_workbook
from openpyxl.styles import Font,PatternFill,Alignment
from openpyxl.utils import get_column_letter

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
    for name,columns,keys in [
        ("Departments",["Company","Department","Shipments"],["company","report_type","shipments"]),
        ("Trade lanes",["Origin","Destination","Shipments"],["origin","destination","shipments"]),
        ("Companies",["Role","Company name","Appearances"],["role","name","appearances"]),
        ("Monthly trend",["Month","Shipments"],["month","shipments"]),
        ("Branches",["Branch","Shipments"],["branch","shipments"])]:
        sheets.append((name,columns,[[r.get(k) for k in keys] for r in data[name.lower().replace(" ","_")] if False]))
    # Explicit dataset names avoid accidental mapping or omitted tabs.
    sheets=sheets[:1]
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
    if len(payload)>2*1024*1024: raise ValueError("Excel file exceeds 2 MB")
    try: wb=load_workbook(BytesIO(payload),read_only=True,data_only=True)
    except Exception: raise ValueError("Invalid XLSX workbook")
    ws=wb.active
    iterator=ws.iter_rows(values_only=True)
    header=next(iterator,None)
    expected=["company_name","industry","confidence","source","approved"]
    if not header or [str(x or "").strip().lower() for x in header[:5]]!=expected:
        raise ValueError("Expected columns: "+", ".join(expected))
    rows=[]
    for n,row in enumerate(iterator,2):
        if n>501: raise ValueError("Maximum 500 rows per import")
        if not any(x is not None for x in row): continue
        if len(row)<5: raise ValueError(f"Row {n}: missing columns")
        name,industry,confidence,source,approved=row[:5]
        if not all(isinstance(x,str) for x in (name,industry,confidence,source)):
            raise ValueError(f"Row {n}: invalid text fields")
        flag=str(approved or "").strip().lower()
        if flag not in ("yes","no","true","false","1","0",""):
            raise ValueError(f"Row {n}: approved must be Yes or No")
        rows.append((name,industry,confidence.lower(),source,flag in ("yes","true","1")))
    return rows

def classification_template():
    return workbook_bytes([("Classification import",
        ["company_name","industry","confidence","source","approved"],
        [["Example Company","Example industry","medium","Verified source reference","No"]])])
