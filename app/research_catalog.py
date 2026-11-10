"""Import research master as evidence for classification, not machine-learning training or assumed truth."""
from io import BytesIO
from datetime import date,datetime
from openpyxl import load_workbook
from . import independent_auth as auth
import time

COLUMNS={
"Entity Key":"entity_key","Original Company Name":"original_name",
"Normalized Company Name":"normalized_name","Canonical Legal Entity":"canonical_entity",
"Parent Group":"parent_group","Alias Group ID":"alias_group","Country":"country",
"Primary Industry":"industry","Sub-Industry":"sub_industry","Business Activity":"activity",
"Activity Type":"activity_type","Classification Rationale":"rationale",
"Evidence URL":"evidence_url","Evidence Source Type":"evidence_type",
"Confidence":"confidence","Verification Status":"verification_status",
"Research Date":"research_date","Shipment Appearances":"appearances",
"Shipper Appearances":"shipper_appearances","Consignee Appearances":"consignee_appearances",
"NGL Appearances":"ngl_appearances","NCS Appearances":"ncs_appearances",
"Review Notes":"review_notes","Provisional Industry (NOT classified)":"provisional_industry",
"Unresolved Reason":"unresolved_reason","Record Origin":"record_origin"
}
NUMERIC={"appearances","shipper_appearances","consignee_appearances","ngl_appearances","ncs_appearances"}
FIELDS=list(COLUMNS.values())
def parse_research(payload):
    if len(payload)>20*1024*1024: raise ValueError("Workbook exceeds 20 MB")
    try: wb=load_workbook(BytesIO(payload),read_only=True,data_only=True)
    except Exception: raise ValueError("Invalid XLSX workbook")
    if "Final Classification Master" not in wb.sheetnames:
        raise ValueError("Final Classification Master sheet required")
    ws=wb["Final Classification Master"]
    ws.reset_dimensions()
    iterator=ws.iter_rows(values_only=True)
    headers=next(iterator,None)
    if not headers: raise ValueError("Missing header")
    indexes={name:headers.index(name) for name in COLUMNS if name in headers}
    required=("Entity Key","Original Company Name","Verification Status","Primary Industry")
    if any(k not in indexes for k in required):
        raise ValueError("Missing required master columns")
    records=[];keys=set()
    for number,row in enumerate(iterator,2):
        if not row or not row[indexes["Entity Key"]]: continue
        record={}
        for heading,field in COLUMNS.items():
            i=indexes.get(heading)
            v=row[i] if i is not None and i<len(row) else None
            if field in NUMERIC:
                try: v=int(v) if v is not None else None
                except (ValueError,TypeError): v=None
            elif isinstance(v,(date,datetime)): v=v.isoformat()
            elif v is not None: v=str(v).strip()[:3000]
            record[field]=v
        key=record["entity_key"]
        if key in keys: raise ValueError(f"Duplicate entity key at row {number}")
        keys.add(key)
        if len(records)>=50000: raise ValueError("Maximum 50,000 entities")
        records.append(record)
    if not records: raise ValueError("No research records")
    return records

def import_research(actor,records):
    fields=FIELDS+["imported_at"]
    placeholders=",".join("?" for _ in fields)
    with auth.connection() as db:
        # Keep curated classifications separate; source import replaces research snapshot only.
        db.execute("DELETE FROM research_entities")
        now=int(time.time())
        db.executemany("INSERT INTO research_entities ("+",".join(fields)+") VALUES ("+placeholders+")",
            [tuple(r.get(k) for k in FIELDS)+(now,) for r in records])
        db.execute("INSERT INTO audit(event,user_id,created_at) VALUES (?,?,?)",
                   ("research_master_import_"+str(len(records)),actor,now))
    return len(records)

def research_summary():
    with auth.connection() as db:
        totals=[dict(r) for r in db.execute("""SELECT verification_status,COUNT(*) AS count
          FROM research_entities GROUP BY verification_status ORDER BY count DESC""")]
        industries=[dict(r) for r in db.execute("""SELECT industry,COUNT(*) AS companies,
          COALESCE(SUM(appearances),0) AS appearances FROM research_entities
          WHERE verification_status IN ('Verified — Exact Entity','Probable — Strong Evidence')
            AND industry IS NOT NULL AND industry!='Unknown / Requires Verification'
          GROUP BY industry ORDER BY appearances DESC,companies DESC LIMIT 50""")]
        count=db.execute("SELECT COUNT(*) FROM research_entities").fetchone()[0]
    return {"total":count,"statuses":totals,"industries":industries}

def research_list(q="",status="",industry="",limit=100,offset=0):
    q=q.strip()[:100]
    with auth.connection() as db:
        rows=db.execute("""SELECT entity_key,original_name,normalized_name,canonical_entity,country,
          parent_group,alias_group,industry,sub_industry,activity_type,
          evidence_url,confidence,verification_status,appearances,review_notes,
          provisional_industry,unresolved_reason
          FROM research_entities WHERE (?='' OR original_name LIKE '%'||?||'%')
          AND (?='' OR verification_status=?)
          AND (?='' OR industry=?)
          ORDER BY COALESCE(appearances,0) DESC,original_name LIMIT ? OFFSET ?""",
          (q,q,status,status,industry,industry,min(limit,200),max(0,offset))).fetchall()
    return [dict(r) for r in rows]
