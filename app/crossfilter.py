"""Read-only cross-filtered operations analytics, exclusively from the approved source view."""
from sqlalchemy import text
from .industry_explorer import validate_scope

VIEW="ai_insights_source.current_shipments"
FILTER_COLUMNS={"origin":"origin","destination":"destination","shipper":"shipper","consignee":"consignee","branch":"branch"}
def conditions(companies,lobs,filters):
    cs,ls=validate_scope(companies,lobs)
    where=["company=ANY(:companies)","report_type=ANY(:lobs)"]
    params={"companies":cs,"lobs":ls}
    for key,column in FILTER_COLUMNS.items():
        raw=(filters.get(key) or "").strip()
        if len(raw)>1500: raise ValueError("Filter exceeds allowed length")
        values=[x.strip() for x in raw.split(",") if x.strip()]
        if len(values)>30 or any(len(x)>200 for x in values):
            raise ValueError("Too many or too long filter selections")
        if values:
            where.append(f"{column}=ANY(:f_{key})")
            params["f_"+key]=values
    start,end=filters.get("start"),filters.get("end")
    for key,value in (("start",start),("end",end)):
        if value:
            import datetime
            try: datetime.date.fromisoformat(value)
            except ValueError: raise ValueError("Invalid date")
            where.append("shipment_date "+(">=" if key=="start" else "<=")+f" :{key}")
            params[key]=value
    return " AND ".join(where),params

def query_rows(engine,companies,lobs,filters,limit=25):
    where,params=conditions(companies,lobs,filters)
    params["limit"]=min(max(int(limit),1),100)
    def run(conn,sql):
        return [dict(r) for r in conn.execute(text(sql),params).mappings()]
    with engine.connect() as conn:
        overview=run(conn,f"""SELECT COUNT(*) AS shipments,
            COUNT(*) FILTER(WHERE NULLIF(BTRIM(shipper),'') IS NOT NULL) AS shippers,
            COUNT(*) FILTER(WHERE NULLIF(BTRIM(consignee),'') IS NOT NULL) AS consignees,
            COALESCE(SUM(teus),0) AS teus,
            COALESCE(SUM(gross_wt),0) AS gross_weight,
            MIN(shipment_date) AS first_date,MAX(shipment_date) AS last_date
            FROM {VIEW} WHERE {where}""")[0]
        breakdown=run(conn,f"""SELECT company,report_type,COUNT(*) AS shipments
            FROM {VIEW} WHERE {where} GROUP BY 1,2 ORDER BY 1,2""")
        lanes=run(conn,f"""SELECT COALESCE(NULLIF(BTRIM(origin),''),'Unknown') AS origin,
            COALESCE(NULLIF(BTRIM(destination),''),'Unknown') AS destination,
            COUNT(*) AS shipments FROM {VIEW} WHERE {where}
            GROUP BY 1,2 ORDER BY shipments DESC,1,2 LIMIT :limit""")
        participants=run(conn,f"""SELECT role,name,COUNT(*) AS appearances FROM (
            SELECT 'Shipper' AS role,NULLIF(BTRIM(shipper),'') AS name FROM {VIEW} WHERE {where}
            UNION ALL
            SELECT 'Consignee' AS role,NULLIF(BTRIM(consignee),'') AS name FROM {VIEW} WHERE {where}
            ) x WHERE name IS NOT NULL GROUP BY 1,2 ORDER BY appearances DESC,role,name LIMIT :limit""")
        trend=run(conn,f"""SELECT TO_CHAR(DATE_TRUNC('month',shipment_date),'YYYY-MM') AS month,
            COUNT(*) AS shipments FROM {VIEW} WHERE {where} AND shipment_date IS NOT NULL
            GROUP BY 1 ORDER BY 1""")
        branches=run(conn,f"""SELECT COALESCE(NULLIF(BTRIM(branch),''),'Unknown') AS branch,
            COUNT(*) AS shipments FROM {VIEW} WHERE {where}
            GROUP BY 1 ORDER BY shipments DESC,branch LIMIT :limit""")
    return {"overview":overview,"breakdown":breakdown,"lanes":lanes,
            "participants":participants,"trend":trend,"branches":branches,
            "scope":{"companies":params["companies"],"lobs":params["lobs"]},
            "filters":{k:v for k,v in filters.items() if v}}

def filter_options(engine,companies,lobs,filters):
    """Faceted values constrained by the other selected filters."""
    result={}
    with engine.connect() as conn:
        for key,col in FILTER_COLUMNS.items():
            other={k:v for k,v in filters.items() if k!=key}
            where,params=conditions(companies,lobs,other)
            result[key]=[r[0] for r in conn.execute(text(f"""
                SELECT DISTINCT {col} FROM {VIEW} WHERE {where}
                  AND NULLIF(BTRIM({col}),'') IS NOT NULL
                ORDER BY {col} LIMIT 250"""),params)]
    return result
