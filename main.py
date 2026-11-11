"""Fail-closed AI Insights deployment with a restricted, startup-only database probe.

No customer data is returned until authentication and authorization are implemented.
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from pathlib import Path
from urllib.parse import urlsplit
from io import BytesIO
from app.crossfilter import query_rows,filter_options
from app.research_catalog import parse_research,import_research,research_summary,research_list
from app.excel_tools import analytics_export,parse_classification_xlsx,classification_template,classification_workbook_with_prompt,workbook_bytes
from app import independent_auth as auth
from app.industry_master import INDUSTRY_VERTICALS, INDUSTRY_PROMPT
from app.industry_explorer import summary, top_trade_lanes, company_appearances
from app.company_discovery import search_companies, opportunity_candidates
from functools import lru_cache
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai_insights")
_database_verified = False

def verify_restricted_source():
    """Read-only verification; logs no credentials or shipment names."""
    required = ["SHIPMENT_DB_HOST", "SHIPMENT_DB_NAME", "SHIPMENT_DB_PORT",
                "SHIPMENT_DB_USER", "SHIPMENT_DB_PASSWORD"]
    if any(not os.getenv(k) for k in required):
        logger.warning("Source check: missing connection configuration")
        return False
    if os.environ["SHIPMENT_DB_USER"] != "ai_insights_reader":
        logger.error("Source check: unexpected database user; refusing connection")
        return False
    url = URL.create(
        "postgresql+psycopg2",
        username=os.environ["SHIPMENT_DB_USER"],
        password=os.environ["SHIPMENT_DB_PASSWORD"],
        host=os.environ["SHIPMENT_DB_HOST"],
        port=int(os.environ["SHIPMENT_DB_PORT"]),
        database=os.environ["SHIPMENT_DB_NAME"],
    )
    engine = create_engine(
        url, pool_pre_ping=True, pool_size=1, max_overflow=0,
        connect_args={"connect_timeout": 5, "options": "-c default_transaction_read_only=on -c statement_timeout=10000"},
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT current_user AS username,
                       has_table_privilege(current_user,'ai_insights_source.current_shipments','SELECT') AS allowed,
                       has_table_privilege(current_user,'public.shipments','SELECT') AS direct,
                       has_table_privilege(current_user,'public.profit_lines','SELECT') AS profit,
                       has_table_privilege(current_user,'public.users','SELECT') AS users,
                       has_table_privilege(current_user,'public.sessions','SELECT') AS sessions
            """)).mappings().one()
            safe = (row["username"] == "ai_insights_reader"
                    and row["allowed"] and not any(row[k] for k in ("direct","profit","users","sessions")))
            if not safe:
                logger.error("Source check: permission policy failed; data access remains disabled")
                return False
            required_columns = ["shipper","consignee","carrier","job_owner","salesperson"]
            available = {r[0] for r in conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='ai_insights_source'
                  AND table_name='current_shipments'
                  AND column_name = ANY(:required_columns)
            """), {"required_columns":required_columns}).all()}
            missing = sorted(set(required_columns)-available)
            if missing:
                logger.error("Source check: expanded shipment fields missing (%s); data access remains disabled",
                             ",".join(missing))
                return False
            count = conn.execute(text("SELECT COUNT(*) FROM ai_insights_source.current_shipments")).scalar_one()
            logger.info("Source check passed: read-only analytics enabled; active_rows=%d; salesperson and counterparty fields verified", count)
            return True
    except Exception as exc:
        # Never log connection URL, exception details, or credentials.
        logger.error("Source check failed (%s); data access remains disabled", type(exc).__name__)
        return False
    finally:
        engine.dispose()

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _database_verified
    _database_verified = verify_restricted_source()
    auth.initialize()
    auth.ensure_bootstrap_admin_role()
    bootstrap_status = auth.bootstrap_status()
    logger.info('Independent auth bootstrap status: %s', bootstrap_status)
    if bootstrap_status == 'ready' and auth.provision_initial_admin():
        logger.info('Independent AI Insights admin provisioned from private environment configuration')
    try:
        yield
    finally:
        close_scoped_engine()

app = FastAPI(title="AI Insights Operations", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)

@app.get("/healthz")
def healthz():
    return {"status": "running", "product": "AI Insights",
            "data_access": "verified" if _database_verified else "disabled",
            "production_ready": bool(_database_verified),
            "readiness_basis": "restricted shipment source connection and required columns"}

def same_origin(request: Request):
    """Reject cross-origin mutations; allow plain HTTP only on loopback hosts."""
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    if not origin or not host:
        raise HTTPException(403, "Invalid request origin")
    try:
        parsed = urlsplit(origin)
        host_parts = urlsplit("//" + host)
        host_name = (host_parts.hostname or "").lower()
        loopback = host_name in ("localhost", "127.0.0.1", "::1")
        if (parsed.scheme not in ("https", "http")
                or (parsed.scheme != "https" and not loopback)
                or (parsed.scheme == "http" and not loopback)
                or (parsed.hostname or "").lower() != host_name
                or (parsed.port or (443 if parsed.scheme == "https" else 80))
                   != (host_parts.port or (443 if parsed.scheme == "https" else 80))
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment
                or parsed.username is not None or parsed.password is not None):
            raise HTTPException(403, "Invalid request origin")
    except ValueError:
        raise HTTPException(403, "Invalid request origin")

def current_user(request: Request):
    user = auth.session_user(request.cookies.get("ai_insights_session"))
    if not user:
        raise HTTPException(401, "Authentication required")
    return user

@app.get("/", response_class=HTMLResponse)
def index():
    return Path(__file__).parent.joinpath("app/industry_explorer.html").read_text()

@app.post("/auth/login")
async def login(request: Request, response: Response):
    same_origin(request)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(400, "Invalid request")
    email, password = payload.get("email"), payload.get("password")
    if not isinstance(email, str) or not isinstance(password, str) or len(email)>254 or len(password)>1024:
        raise HTTPException(400, "Invalid request")
    token = auth.authenticate(email, password)
    if not token:
        raise HTTPException(401, "Invalid credentials")
    response.set_cookie("ai_insights_session", token, max_age=12*3600,
                        secure=True, httponly=True, samesite="lax", path="/")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}

@app.get("/auth/me")
def me(user=Depends(current_user)):
    return user

@app.post("/auth/logout")
def logout(request: Request, response: Response):
    same_origin(request)
    auth.logout(request.cookies.get("ai_insights_session"))
    response.delete_cookie("ai_insights_session", path="/")
    return {"ok": True}

@app.get("/api/explorer")
def explorer(company: str | None = None, lob: str | None = None, user=Depends(current_user)):
    if not _database_verified:
        raise HTTPException(503, "Operational source not verified")
    companies, lobs = user["companies"], user["lobs"]
    if company is not None:
        if company not in companies:
            raise HTTPException(403, "Company not authorized")
        companies = [company]
    if lob is not None:
        if lob not in lobs:
            raise HTTPException(403, "Department not authorized")
        lobs = [lob]
    engine = scoped_engine()
    return {"summary":summary(engine,companies=companies,lobs=lobs),
            "lanes":top_trade_lanes(engine,companies=companies,lobs=lobs),
            "participants":company_appearances(engine,companies=companies,lobs=lobs)}

@lru_cache(maxsize=1)
def scoped_engine():
    """One process-wide read-only pool, reused across requests."""
    url=URL.create("postgresql+psycopg2", username=os.environ["SHIPMENT_DB_USER"],
        password=os.environ["SHIPMENT_DB_PASSWORD"],host=os.environ["SHIPMENT_DB_HOST"],
        port=int(os.environ["SHIPMENT_DB_PORT"]),database=os.environ["SHIPMENT_DB_NAME"])
    return create_engine(url,pool_pre_ping=True,pool_size=2,max_overflow=2,pool_timeout=5,
        connect_args={"connect_timeout":5,"options":"-c default_transaction_read_only=on -c statement_timeout=10000"})

def close_scoped_engine():
    """Dispose the shared pool during application shutdown."""
    if scoped_engine.cache_info().currsize:
        scoped_engine().dispose()
        scoped_engine.cache_clear()

def classification_mapping(industry=None, include_evidence=False):
    """Return only unambiguous saved mappings, optionally scoped to one vertical.

    The independent classification store is SQLite while shipment analytics is
    PostgreSQL. Keep this bridge payload minimal and never send evidence text for
    trend/drilldown joins.
    """
    fields = """MIN(c.company_name) AS company_name, MIN(c.industry) AS industry"""
    if include_evidence:
        fields += """, MIN(c.country) AS country,
            MIN(c.confidence) AS confidence, MIN(c.source) AS source"""
    sql = f"""SELECT {fields}
        FROM classifications c
        WHERE TRIM(COALESCE(c.industry,''))<>''
          AND TRIM(COALESCE(c.company_name,''))<>''
          AND (:industry IS NULL OR TRIM(c.industry)=:industry)
          AND NOT EXISTS (
            SELECT 1 FROM classifications other
            WHERE LOWER(TRIM(other.company_name))=LOWER(TRIM(c.company_name))
              AND TRIM(COALESCE(other.industry,''))<>''
              AND other.industry<>c.industry
          )
        GROUP BY LOWER(TRIM(c.company_name))"""
    with auth.connection() as db:
        return [dict(row) for row in db.execute(sql, {"industry": industry})]


def allowed_scope(user,company,lob):
    if not _database_verified: raise HTTPException(503,"Source not verified")
    def parse(raw,authorized):
        if not raw: return authorized
        if raw.startswith("j:"):
            import json
            try: decoded=json.loads(raw[2:])
            except (ValueError,TypeError): raise HTTPException(400,"Invalid selection")
            if not isinstance(decoded,list) or any(not isinstance(x,str) for x in decoded):
                raise HTTPException(400,"Invalid selection")
            values=list(dict.fromkeys(x.strip() for x in decoded if x.strip()))
        else:
            values=list(dict.fromkeys(x.strip() for x in raw.split(",") if x.strip()))
        if not values or len(values)>len(authorized) or any(v not in authorized for v in values):
            raise HTTPException(403,"Selection outside authorized scope")
        return values
    return parse(company,user["companies"]),parse(lob,user["lobs"])

def require_classification_admin(user=Depends(current_user)):
    # All authenticated users may contribute industry classifications by product policy.
    # System administration remains restricted to administrators.
    return user

def require_admin(user=Depends(current_user)):
    if user.get("role") != "admin":
        raise HTTPException(403, "Administrator permission required")
    return user

def dashboard_filters(origin=None,destination=None,shipper=None,consignee=None,branch=None,start=None,end=None):
    return dict(origin=origin,destination=destination,shipper=shipper,consignee=consignee,
                branch=branch,start=start,end=end)

@app.get("/api/dashboard")
def dashboard(company: str|None=None,lob: str|None=None,origin: str|None=None,
              destination: str|None=None,shipper: str|None=None,consignee: str|None=None,
              branch: str|None=None,start: str|None=None,end: str|None=None,
              user=Depends(current_user)):
    companies,lobs=allowed_scope(user,company,lob)
    engine=scoped_engine()
    try:
        return query_rows(engine,companies,lobs,
            dashboard_filters(origin,destination,shipper,consignee,branch,start,end))
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get("/api/dashboard/options")
def dashboard_options(company: str|None=None,lob: str|None=None,origin: str|None=None,
              destination: str|None=None,shipper: str|None=None,consignee: str|None=None,
              branch: str|None=None,start: str|None=None,end: str|None=None,
              user=Depends(current_user)):
    companies,lobs=allowed_scope(user,company,lob)
    engine=scoped_engine()
    try:
        return filter_options(engine,companies,lobs,
            dashboard_filters(origin,destination,shipper,consignee,branch,start,end))
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get("/api/dashboard/export")
def dashboard_export(company: str|None=None,lob: str|None=None,origin: str|None=None,
              destination: str|None=None,shipper: str|None=None,consignee: str|None=None,
              branch: str|None=None,start: str|None=None,end: str|None=None,
              user=Depends(current_user)):
    companies,lobs=allowed_scope(user,company,lob)
    engine=scoped_engine()
    try:
        data=query_rows(engine,companies,lobs,
            dashboard_filters(origin,destination,shipper,consignee,branch,start,end),limit=10000)
        output=analytics_export(data)
    except ValueError as exc: raise HTTPException(400,str(exc))
    return StreamingResponse(BytesIO(output),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-operations.xlsx",
                 "Cache-Control":"no-store"})

@app.get("/api/classifications/template")
@app.get("/api/admin/classifications/template")
def classification_xlsx_template(user=Depends(current_user)):
    return StreamingResponse(BytesIO(classification_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-classification-template.xlsx",
                 "Cache-Control":"no-store"})

def _saved_classification_export_rows():
    # Full saved master, not the 500-row search preview. Export only filled industries.
    with auth.connection() as db:
        return [dict(r) for r in db.execute("""SELECT company_name,industry,confidence,source,country
            FROM classifications WHERE TRIM(COALESCE(industry,'')) <> ''
            ORDER BY company_name COLLATE NOCASE""")]

@app.get("/api/classifications/export")
@app.get("/api/admin/classifications/export")
def classification_xlsx_export(user=Depends(current_user)):
    rows=_saved_classification_export_rows()
    output=workbook_bytes([("Classifications",
        ["company_name","industry","confidence","source","country"],
        [[r["company_name"],r["industry"],r["confidence"],r["source"],r.get("country","")] for r in rows])])
    return StreamingResponse(BytesIO(output),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-classified-organizations.xlsx",
                 "Cache-Control":"no-store"})

@app.get("/api/classifications/unique-verticals")
@app.get("/api/admin/classifications/unique-verticals")
def classification_unique_verticals(user=Depends(current_user)):
    # Case-insensitive unique vertical names, with distinct organization counts.
    with auth.connection() as db:
        rows=db.execute("""SELECT MIN(TRIM(industry)) AS industry,
            COUNT(DISTINCT LOWER(TRIM(company_name))) AS organizations
            FROM classifications WHERE TRIM(COALESCE(industry,'')) <> ''
            GROUP BY LOWER(TRIM(industry)) ORDER BY industry COLLATE NOCASE""").fetchall()
    output=workbook_bytes([("Unique industry verticals",
        ["industry_vertical","classified_organizations"],
        [[r["industry"],r["organizations"]] for r in rows])])
    return StreamingResponse(BytesIO(output),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-unique-industry-verticals.xlsx",
                 "Cache-Control":"no-store"})

@app.post("/api/classifications/import")
@app.post("/api/admin/classifications/import")
async def classification_xlsx_import(request:Request,file:UploadFile=File(...),user=Depends(require_classification_admin)):
    same_origin(request)
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400,"XLSX file required")
    payload=await file.read(20*1024*1024+1)
    try:
        rows,skipped=parse_classification_xlsx(payload)
        count=auth.classification_import(user["id"],rows)
        return {"imported":count,"skipped_unclassified":skipped}
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get("/guide", response_class=HTMLResponse)
def guide_page(user=Depends(current_user)):
    return Path(__file__).parent.joinpath("app/guide.html").read_text()

@app.get("/companies",response_class=HTMLResponse)
def companies_page(user=Depends(current_user)):
    return Path(__file__).parent.joinpath("app/discovery.html").read_text()

@app.get("/opportunities",response_class=HTMLResponse)
def opportunities_page(user=Depends(current_user)):
    return Path(__file__).parent.joinpath("app/discovery.html").read_text()

@app.get("/api/companies")
def companies_api(company: str | None=None,lob: str | None=None,q: str="",
                  origin: str|None=None,destination: str|None=None,branch: str|None=None,
                  start: str|None=None,end: str|None=None,user=Depends(current_user)):
    companies,lobs=allowed_scope(user,company,lob)
    if len(q)>100: raise HTTPException(400,"Search too long")
    engine=scoped_engine()
    try: return {"results":search_companies(engine,companies=companies,lobs=lobs,term=q,filters=dashboard_filters(origin=origin,destination=destination,branch=branch,start=start,end=end))}

    finally: pass
@app.get("/api/discovery/export")
def discovery_export(kind: str,company: str|None=None,lob: str|None=None,
                     origin: str|None=None,destination: str|None=None,
                     branch: str|None=None,start: str|None=None,end: str|None=None,
                     q: str="",user=Depends(current_user)):
    if kind not in ("companies","opportunities"): raise HTTPException(400,"Invalid export type")
    companies,lobs=allowed_scope(user,company,lob)
    filters=dashboard_filters(origin=origin,destination=destination,branch=branch,start=start,end=end)
    engine=scoped_engine()
    try:
        if kind=="companies":
            rows=search_companies(engine,companies=companies,lobs=lobs,term=q,limit=10000,filters=filters)
            cols=["Company name","Role","Appearances","Distinct lanes"]
            fields=["name","role","appearances","lanes"]
        else:
            rows=opportunity_candidates(engine,companies=companies,lobs=lobs,limit=10000,filters=filters)
            cols=["Company name","Appearances","Distinct lanes"]
            fields=["name","appearances","lane_count"]
        output=workbook_bytes([(kind.title(),cols,[[r.get(k) for k in fields] for r in rows]),
            ("Applied filters",["Filter","Value"],[(k,str(v)) for k,v in filters.items() if v])])
    finally: pass
    return StreamingResponse(BytesIO(output),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-"+kind+".xlsx",
                 "Cache-Control":"no-store"})

@app.get("/api/opportunities")
def opportunities_api(company: str | None=None,lob: str | None=None,
                      origin: str|None=None,destination: str|None=None,branch: str|None=None,
                      start: str|None=None,end: str|None=None,user=Depends(current_user)):
    companies,lobs=allowed_scope(user,company,lob)
    engine=scoped_engine()
    try: return {"results":opportunity_candidates(engine,companies=companies,lobs=lobs,
                     filters=dashboard_filters(origin=origin,destination=destination,branch=branch,start=start,end=end)),
                 "disclaimer":"Activity-based candidates only. Not verified new prospects or industry classifications."}

    finally: pass
@app.get("/admin", response_class=HTMLResponse)
def admin_page(user=Depends(require_admin)):
    return Path(__file__).parent.joinpath("app/admin.html").read_text()

@app.get("/api/research/summary")
def research_summary_api(user=Depends(current_user)):
    return research_summary()

@app.get("/api/research/entities")
def research_entities_api(q:str="",status:str="",industry:str="",offset:int=0,user=Depends(current_user)):
    if len(q)>100 or len(status)>100 or len(industry)>100:
        raise HTTPException(400,"Invalid filters")
    return {"results":research_list(q,status,industry,offset=offset)}

@app.post("/api/admin/research/import")
async def research_import_api(request:Request,file:UploadFile=File(...),user=Depends(require_admin)):
    same_origin(request)
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400,"XLSX required")
    payload=await file.read(20*1024*1024+1)
    try:
        records=parse_research(payload)
        return {"imported":import_research(user["id"],records)}
    except ValueError as exc:
        raise HTTPException(400,str(exc))

@app.get("/favicon.ico")
def favicon():
    """Serve the product favicon; browsers otherwise repeatedly request a missing icon."""
    return Response(Path(__file__).parent.joinpath("app/favicon.svg").read_text(),
                    media_type="image/svg+xml", headers={"Cache-Control":"public, max-age=86400"})

@app.get("/assets/ui.css")
def shared_ui_css():
    return Response(Path(__file__).parent.joinpath("app/ui.css").read_text(),media_type="text/css")

@app.get("/assets/ui.js")
def shared_ui_js():
    return Response(Path(__file__).parent.joinpath("app/ui.js").read_text(),media_type="application/javascript")

@app.get("/classifications",response_class=HTMLResponse)
def classification_page(user=Depends(current_user)):
    return Path(__file__).parent.joinpath("app/classifications.html").read_text()

@app.get("/api/classifications/shipment-trend")
def classification_shipment_trend(company: str|None=None,lob: str|None=None,
        start: str|None=None,end: str|None=None,origin:str|None=None,destination:str|None=None,shipper:str|None=None,consignee:str|None=None,branch:str|None=None,role: str="shipper",
        user=Depends(current_user)):
    """Monthly operational shipment rows attributed to saved company industries.

    Each shipment is counted at most once for the selected counterparty role.
    Classification is an exact normalized company-name match, not inferred.
    """
    if role not in ("primary","shipper","consignee"):
        raise HTTPException(400,"Role must be primary, shipper, or consignee")
    companies,lobs=allowed_scope(user,company,lob)
    from app.crossfilter import conditions
    try:
        where,params=conditions(companies,lobs,{"start":start,"end":end,"origin":origin,"destination":destination,"shipper":shipper,"consignee":consignee,"branch":branch})
    except ValueError as exc:
        raise HTTPException(400,str(exc))
    # Send only compact, unambiguous company/industry pairs across the
    # SQLite-to-PostgreSQL boundary; never ship the full evidence register.
    classifications=classification_mapping()
    import json
    params["classifications"]=json.dumps(classifications,separators=(",",":"))
    counterparty=("CASE WHEN s.report_type IN (\'AE\',\'OE\') THEN s.shipper ELSE s.consignee END" if role=="primary" else ("s.shipper" if role=="shipper" else "s.consignee"))
    sql=f"""WITH industry_map AS (
       SELECT LOWER(BTRIM(company_name)) AS normalized_name,
              CASE WHEN COUNT(DISTINCT industry)=1 THEN MIN(industry) ELSE NULL END AS industry
       FROM jsonb_to_recordset(CAST(:classifications AS jsonb))
         AS x(company_name text,industry text)
       GROUP BY LOWER(BTRIM(company_name))
    ), monthly AS (
       SELECT DATE_TRUNC('month',s.shipment_date)::date AS month,
              COALESCE(a.industry,'Unclassified') AS industry,
              COUNT(*) AS shipments
       FROM ai_insights_source.current_shipments s
       LEFT JOIN industry_map a ON LOWER(BTRIM({counterparty}))=a.normalized_name
       WHERE {where} AND s.shipment_date IS NOT NULL
       GROUP BY 1,2
    )
    SELECT TO_CHAR(month,'YYYY-MM') AS month,industry,shipments
    FROM monthly ORDER BY month,shipments DESC,industry"""
    engine=scoped_engine()
    try:
        with engine.connect() as conn:
            rows=[dict(r) for r in conn.execute(text(sql),params).mappings()]
    finally: pass
    return {"role":role,"rows":rows,"classification_basis":"Saved classifications; exact normalized counterparty match; shipment rows, not unique jobs.",
            "total":sum(int(r["shipments"]) for r in rows)}

@app.get("/api/classifications/vertical-performance")
def vertical_performance(industry: str,company: str|None=None,lob: str|None=None,
        start: str|None=None,end: str|None=None,origin:str|None=None,destination:str|None=None,shipper:str|None=None,consignee:str|None=None,branch:str|None=None,role: str="shipper",
        user=Depends(current_user)):
    """Read-only industry drilldown: lanes, mode, branches, counterparties and months."""
    if role not in ("primary","shipper","consignee"): raise HTTPException(400,"Invalid role")
    if not industry or len(industry)>100: raise HTTPException(400,"Invalid industry")
    companies,lobs=allowed_scope(user,company,lob)
    from app.crossfilter import conditions
    try: where,params=conditions(companies,lobs,{"start":start,"end":end,"origin":origin,"destination":destination,"shipper":shipper,"consignee":consignee,"branch":branch})
    except ValueError as exc: raise HTTPException(400,str(exc))
    # The selected vertical is the only mapping needed for this drilldown.
    # Unclassified remains supported by using the complete compact map.
    mapping=classification_mapping(None if industry=="Unclassified" else industry)
    import json
    params["mapping"]=json.dumps(mapping,separators=(",",":"))
    params["industry"]=industry
    field=("CASE WHEN s.report_type IN (\'AE\',\'OE\') THEN s.shipper ELSE s.consignee END" if role=="primary" else ("s.shipper" if role=="shipper" else "s.consignee"))
    base=f"""WITH industry_map AS (
       SELECT LOWER(BTRIM(company_name)) AS name,
              CASE WHEN COUNT(DISTINCT industry)=1 THEN MIN(industry) ELSE NULL END AS industry
       FROM jsonb_to_recordset(CAST(:mapping AS jsonb)) AS x(company_name text,industry text)
       GROUP BY 1
    ), scoped AS (
       SELECT s.* FROM ai_insights_source.current_shipments s
       LEFT JOIN industry_map m ON LOWER(BTRIM({field}))=m.name
       WHERE {where} AND COALESCE(m.industry,'Unclassified')=:industry
    )"""
    opposite_party=("CASE WHEN report_type IN (\'AE\',\'OE\') THEN consignee ELSE shipper END" if role=="primary" else ("consignee" if role=="shipper" else "shipper"))
    queries={
      "overview":"SELECT COUNT(*) AS shipment_rows,COUNT(DISTINCT key) AS distinct_keys,COALESCE(SUM(teus),0) AS teus,COALESCE(SUM(gross_wt),0) AS gross_weight,MIN(shipment_date) AS first_date,MAX(shipment_date) AS last_date FROM scoped",
      "departments":"SELECT company,report_type,COUNT(*) AS shipments,COUNT(DISTINCT key) AS distinct_keys,COALESCE(SUM(teus),0) AS teus,COALESCE(SUM(gross_wt),0) AS gross_weight FROM scoped GROUP BY 1,2 ORDER BY shipments DESC",
      "lanes":"SELECT COALESCE(NULLIF(BTRIM(origin),''),'Unknown') AS origin,COALESCE(NULLIF(BTRIM(destination),''),'Unknown') AS destination,COUNT(*) AS shipments FROM scoped GROUP BY 1,2 ORDER BY shipments DESC LIMIT 25",
      "branches":"SELECT COALESCE(NULLIF(BTRIM(branch),''),'Unknown') AS branch,COUNT(*) AS shipments FROM scoped GROUP BY 1 ORDER BY shipments DESC LIMIT 15",
      "counterparties":f"SELECT COALESCE(NULLIF(BTRIM({opposite_party}),''),'Unknown') AS name,COUNT(*) AS shipments FROM scoped GROUP BY 1 ORDER BY shipments DESC LIMIT 25",
      "months":"SELECT TO_CHAR(DATE_TRUNC('month',shipment_date),'YYYY-MM') AS month,COUNT(*) AS shipments FROM scoped WHERE shipment_date IS NOT NULL GROUP BY 1 ORDER BY 1"
    }
    engine=scoped_engine()
    try:
        with engine.connect() as conn:
            result={k:[dict(r) for r in conn.execute(text(base+" "+q),params).mappings()] for k,q in queries.items()}
    finally: pass
    return {"industry":industry,"role":role,"data":result,
            "notes":["Counts are operational shipment rows, not financial contribution.",
                     "Agent nomination, salesperson and introducer are not in the verified restricted view; not inferred."]}

@app.get("/api/classifications/contributor-options")
def classification_contributor_options(company:str|None=None,lob:str|None=None,
        origin:str|None=None,destination:str|None=None,shipper:str|None=None,
        consignee:str|None=None,branch:str|None=None,start:str|None=None,end:str|None=None,
        user=Depends(current_user)):
    companies,lobs=allowed_scope(user,company,lob)
    from app.crossfilter import filter_options
    engine=scoped_engine()
    try:
        return filter_options(engine,companies,lobs,{"origin":origin,"destination":destination,
            "shipper":shipper,"consignee":consignee,"branch":branch,"start":start,"end":end})
    except ValueError as exc: raise HTTPException(400,str(exc))

@app.get("/api/classifications/contributors")
def classification_contributors(industry:str,company:str|None=None,lob:str|None=None,
        start:str|None=None,end:str|None=None,role:str="primary",
        origin:str|None=None,destination:str|None=None,shipper:str|None=None,
        consignee:str|None=None,branch:str|None=None,limit:int=10,offset:int=0,record_limit:int=10,record_offset:int=0,include_records:bool=False,user=Depends(current_user)):
    """Underlying attributed organisations, with evidence and shipment calculations."""
    if role not in ("primary","shipper","consignee"): raise HTTPException(400,"Invalid counterparty role")
    if not industry or len(industry)>100: raise HTTPException(400,"Invalid industry")
    companies,lobs=allowed_scope(user,company,lob)
    from app.crossfilter import conditions
    filters={"start":start,"end":end,"origin":origin,"destination":destination,
             "shipper":shipper,"consignee":consignee,"branch":branch}
    try: where,params=conditions(companies,lobs,filters)
    except ValueError as exc: raise HTTPException(400,str(exc))
    # Keep the cross-database mapping payload to names and verticals only.
    # Evidence text can be large and is enriched in Python after the shipment query.
    mapping=classification_mapping(industry, include_evidence=True)
    import json, time
    evidence_by_name={
        str(row["company_name"]).strip().casefold(): row
        for row in mapping if row.get("company_name")
    }
    compact_mapping=[
        {"company_name":row["company_name"],"industry":row["industry"]}
        for row in mapping
    ]
    params["mapping"]=json.dumps(compact_mapping,separators=(",",":"))
    params["industry"]=industry
    params["role"]=role
    params["limit"]=min(max(int(limit),1),500)
    params["offset"]=max(int(offset),0)
    params["record_limit"]=min(max(int(record_limit),1),50000)
    params["record_offset"]=max(int(record_offset),0)
    party=("CASE WHEN s.report_type IN ('AE','OE') THEN s.shipper ELSE s.consignee END"
           if role=="primary" else ("s.shipper" if role=="shipper" else "s.consignee"))
    other=("CASE WHEN s.report_type IN ('AE','OE') THEN s.consignee ELSE s.shipper END"
           if role=="primary" else ("s.consignee" if role=="shipper" else "s.shipper"))
    base_cte=f"""WITH industry_map AS (
       SELECT LOWER(BTRIM(company_name)) AS normalized_name, MIN(industry) AS industry
       FROM jsonb_to_recordset(CAST(:mapping AS jsonb))
         AS x(company_name text,industry text)
       GROUP BY 1
    ), scoped AS (
       SELECT s.key,s.shipment_date,s.company,s.report_type,s.teus,s.gross_wt,
              s.salesperson,s.job_owner,s.shipper,s.consignee,s.origin,
              s.destination,s.branch,
              NULLIF(BTRIM({party}),'') AS contributor,
              NULLIF(BTRIM({other}),'') AS related_party,
              CASE WHEN s.report_type IN ('AE','OE') THEN 'Shipper' ELSE 'Consignee' END AS attributed_role
       FROM ai_insights_source.current_shipments s
       JOIN industry_map m
         ON LOWER(BTRIM({party}))=m.normalized_name AND m.industry=:industry
       WHERE {where}
    )"""
    engine=scoped_engine()
    query_started=time.perf_counter()
    try:
        # Keep expensive contributor grouping separate from the simple shipment
        # summary. This avoids repeated DISTINCT aggregates over one materialized
        # working set, which exceeded the production statement timeout.
        grouped_sql=base_cte+""" SELECT contributor AS organisation,
              CASE WHEN :role='shipper' THEN 'Shipper'
                   WHEN :role='consignee' THEN 'Consignee'
                   ELSE CASE WHEN COUNT(DISTINCT attributed_role)=1
                             THEN MIN(attributed_role) ELSE 'Shipper & Consignee' END
              END AS contributor_role,
              COUNT(*) AS shipment_rows,COUNT(DISTINCT key) AS distinct_shipments,
              COUNT(DISTINCT related_party) AS distinct_related_parties,
              COUNT(DISTINCT NULLIF(BTRIM(salesperson),'')) AS salesperson_count,
              STRING_AGG(DISTINCT NULLIF(BTRIM(salesperson),''), '; ' ORDER BY NULLIF(BTRIM(salesperson),'')) AS salespersons,
              STRING_AGG(DISTINCT NULLIF(BTRIM(job_owner),''), '; ' ORDER BY NULLIF(BTRIM(job_owner),'')) AS job_owners
       FROM scoped WHERE contributor IS NOT NULL
       GROUP BY contributor
       ORDER BY shipment_rows DESC,organisation
       LIMIT :limit OFFSET :offset"""
        with engine.connect() as conn:
            rows=[dict(row) for row in conn.execute(text(grouped_sql),params).mappings()]
        total_sql=base_cte+""" SELECT COUNT(DISTINCT contributor) AS contributor_total,
              COUNT(*) AS shipment_rows,COUNT(DISTINCT key) AS distinct_shipments,
              COALESCE(SUM(teus),0) AS teus,COALESCE(SUM(gross_wt),0) AS gross_weight
       FROM scoped"""
        with engine.connect() as conn:
            summary=dict(conn.execute(text(total_sql),params).mappings().one())
        contributor_total=int(summary.pop("contributor_total") or 0)
        shipment_record_total=int(summary.get("shipment_rows") or 0)
        for row in rows:
            evidence=evidence_by_name.get(str(row["organisation"]).strip().casefold(),{})
            row["country"]=evidence.get("country")
            row["confidence"]=evidence.get("confidence")
            row["evidence"]=evidence.get("source")
        records=[]
        if include_records:
            records_sql=base_cte+""" SELECT key AS shipment_key,shipment_date,company,report_type,
                         shipper,consignee,origin,destination,branch,salesperson,job_owner
                  FROM scoped
                  ORDER BY shipment_date DESC NULLS LAST,key
                  LIMIT :record_limit OFFSET :record_offset"""
            with engine.connect() as conn:
                records=[dict(row) for row in conn.execute(text(records_sql),params).mappings()]
            for row in records:
                evidence=evidence_by_name.get(
                    str(row["shipper"] if role=="shipper" or (role=="primary" and row["report_type"] in ("AE","OE"))
                        else row["consignee"] or "").strip().casefold(),{})
                row["evidence"]=evidence.get("source")
                row["confidence"]=evidence.get("confidence")
    except Exception as exc:
        logger.error("Contributor aggregate query failed; industry=%s role=%s elapsed_ms=%d error_type=%s",
                     industry,role,int((time.perf_counter()-query_started)*1000),type(exc).__name__)
        raise
    logger.info("Contributor aggregate query completed; industry=%s role=%s elapsed_ms=%d",
                industry,role,int((time.perf_counter()-query_started)*1000))
    return {"industry":industry,"role":role,"rows":rows,"records":records,
            "contributor_total":contributor_total,"record_total":shipment_record_total,
            "record_summary":summary,
            "calculation":{"contributor_organisations":contributor_total,
                "shipment_rows":sum(int(row["shipment_rows"] or 0) for row in rows),
                "distinct_shipments_sum":sum(int(row["distinct_shipments"] or 0) for row in rows),
                "basis":"Shipment rows are counted per attributed organisation. Distinct shipment keys are per organisation and are not additive across organisations."},
            "evidence_basis":"Classification source saved for each organisation; URL links open directly, other notes remain text."}

@app.get("/api/classifications/contributors/export")
def classification_contributors_export(industry:str,company:str|None=None,lob:str|None=None,
        start:str|None=None,end:str|None=None,role:str="primary",origin:str|None=None,
        destination:str|None=None,shipper:str|None=None,consignee:str|None=None,
        branch:str|None=None,limit:int=50000,user=Depends(current_user)):
    data=classification_contributors(industry,company,lob,start,end,role,origin,destination,shipper,consignee,branch,limit,0,50000,0,True,user)
    rows=data["rows"]; records=data["records"]; summary=data["record_summary"]
    output=workbook_bytes([
      ("Calculation",["Metric","Value"],[[k,v] for k,v in summary.items()]+[[k,v] for k,v in data["calculation"].items()]),
      ("Top 10 Contributors",["Rank","Organisation","Industry vertical","Role","Shipment rows","Distinct shipments","Related parties","Salesperson count","Salespersons","Job owners","Country","Confidence","Evidence"],
       [[i+1,r.get("organisation"),industry]+[r.get(k) for k in ["contributor_role","shipment_rows","distinct_shipments","distinct_related_parties","salesperson_count","salespersons","job_owners","country","confidence","evidence"]] for i,r in enumerate(rows[:10])]),
      ("Complete Contributor List",["Rank","Organisation","Industry vertical","Role","Shipment rows","Distinct shipments","Related parties","Salesperson count","Salespersons","Job owners","Country","Confidence","Evidence"],
       [[i+1,r.get("organisation"),industry]+[r.get(k) for k in ["contributor_role","shipment_rows","distinct_shipments","distinct_related_parties","salesperson_count","salespersons","job_owners","country","confidence","evidence"]] for i,r in enumerate(rows)]),
      ("Shipment records",["Shipment key","Shipment date","Company","Department","Industry vertical","Shipper","Consignee","Origin","Destination","Branch","ERP Sales Person","Job owner","Evidence","Confidence"],
       [[r.get("shipment_key"),r.get("shipment_date"),r.get("company"),r.get("report_type"),industry]+[r.get(k) for k in ["shipper","consignee","origin","destination","branch","salesperson","job_owner","evidence","confidence"]] for r in records]),
      ("Applied filters",["Filter","Value"],[[k,v] for k,v in {"industry":industry,"company":company,"department":lob,"role":role,"origin":origin,"destination":destination,"shipper":shipper,"consignee":consignee,"branch":branch,"start":start,"end":end}.items() if v])
    ])
    return StreamingResponse(BytesIO(output),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
       headers={"Content-Disposition":"attachment; filename=ai-insights-industry-contributor-records.xlsx","Cache-Control":"no-store"})

@app.get("/api/classifications/industry-status")
def classification_status_api(user=Depends(current_user)):
    return auth.classification_industry_status()

@app.get("/api/classifications/pending-template")
def classification_pending_template(user=Depends(current_user)):
    """Export a compact, reusable workbook with saved decisions preserved."""
    # Keep saved classifications (including completed AI/Gemini work) and add
    # genuinely pending companies discovered from the permitted research/source data.
    saved=auth.classification_rows_for_workbook(limit=50000)
    pending=auth.pending_classification_names(limit=50000)
    merged={}
    for row in saved:
        name=(row.get("company_name") or "").strip()
        if not name:
            continue
        key=name.casefold()
        merged[key]={
            "company_name":name,
            "industry":row.get("industry") or "",
            "confidence":row.get("confidence") or "",
            "source":row.get("source") or "",
            "country":row.get("country") or "",
            "appearances":int(row.get("appearances") or 0),
        }
    for row in pending:
        name=(row.get("company_name") or "").strip()
        if not name:
            continue
        key=name.casefold()
        item=merged.setdefault(key,{
            "company_name":name,"industry":"","confidence":"","source":"",
            "country":row.get("country") or "","appearances":0,
        })
        if not item["country"] and row.get("country"):
            item["country"]=row["country"]
        item["appearances"]=max(item["appearances"],int(row.get("appearances") or 0))
    # Discover authorised shipment counterparties without exposing extra columns.
    companies,lobs=allowed_scope(user,None,None)
    engine=scoped_engine()
    try:
        statement=text("""SELECT company_name,COUNT(*) AS appearances FROM (
          SELECT NULLIF(BTRIM(shipper),'') AS company_name
          FROM ai_insights_source.current_shipments
          WHERE company=ANY(:companies) AND report_type=ANY(:lobs)
            AND NULLIF(BTRIM(shipper),'') IS NOT NULL
          UNION ALL
          SELECT NULLIF(BTRIM(consignee),'') AS company_name
          FROM ai_insights_source.current_shipments
          WHERE company=ANY(:companies) AND report_type=ANY(:lobs)
            AND NULLIF(BTRIM(consignee),'') IS NOT NULL
        ) parties GROUP BY company_name ORDER BY appearances DESC LIMIT 50000""")
        with engine.connect() as conn:
            for row in conn.execute(statement,{"companies":companies,"lobs":lobs}).mappings():
                name=(row["company_name"] or "").strip()
                if not name:
                    continue
                key=name.casefold()
                item=merged.setdefault(key,{
                    "company_name":name,"industry":"","confidence":"","source":"",
                    "country":"","appearances":0,
                })
                item["appearances"]=max(item["appearances"],int(row["appearances"] or 0))
    except Exception as exc:
        logger.warning("Pending workbook shipment discovery unavailable (%s)",type(exc).__name__)
        raise HTTPException(503,"The authorised shipment source is not ready for classification export.")
    ordered=sorted(merged.values(),
        key=lambda row:(-row["appearances"],row["company_name"].casefold()))
    output=classification_workbook_with_prompt([
        ("Pending classification",
         ["company_name","industry","confidence","source","country"],
         [[row["company_name"],row["industry"],row["confidence"],row["source"],row["country"]]
          for row in ordered[:50000]])
    ],"Pending classification")
    return StreamingResponse(BytesIO(output),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-pending-classification.xlsx",
                 "Cache-Control":"no-store"})

@app.get("/api/admin/classifications/reset-preview")
def classifications_reset_preview(user=Depends(require_admin)):
    return auth.classification_reset_preview()

@app.post("/api/admin/classifications/reset-for-reclassification")
async def classifications_reset_for_reclassification(request:Request,user=Depends(require_admin)):
    same_origin(request)
    payload=await request.json()
    if not isinstance(payload,dict) or payload.get("confirmation")!="RESET_ALL_CLASSIFICATIONS":
        raise HTTPException(400,"Explicit confirmation RESET_ALL_CLASSIFICATIONS is required")
    batch_id=payload.get("batch_id")
    if not isinstance(batch_id,str) or not batch_id.strip():
        raise HTTPException(400,"A unique reset batch_id is required")
    try:
        return auth.reset_classifications_for_reclassification(user["id"],batch_id.strip())
    except ValueError as exc:
        raise HTTPException(400,str(exc))

@app.get("/api/classifications/salesperson-industry")
def salesperson_industry(company:str|None=None,lob:str|None=None,start:str|None=None,end:str|None=None,origin:str|None=None,destination:str|None=None,shipper:str|None=None,consignee:str|None=None,branch:str|None=None,
                         user=Depends(current_user)):
    companies,lobs=allowed_scope(user,company,lob)
    with auth.connection() as db:
        mapping=[dict(r) for r in db.execute("SELECT company_name,industry FROM classifications WHERE TRIM(COALESCE(industry,''))<>''")]
    import json
    from app.crossfilter import conditions
    try: where,params=conditions(companies,lobs,dashboard_filters(origin=origin,destination=destination,shipper=shipper,consignee=consignee,branch=branch,start=start,end=end))
    except ValueError as exc: raise HTTPException(400,str(exc))
    params["mapping"]=json.dumps(mapping)
    engine=scoped_engine()
    try:
        with engine.connect() as conn:
            rows=[dict(r) for r in conn.execute(text("""WITH industry_map AS (
              SELECT LOWER(BTRIM(company_name)) AS name,
                     CASE WHEN COUNT(DISTINCT industry)=1 THEN MIN(industry) END AS industry
              FROM jsonb_to_recordset(CAST(:mapping AS jsonb)) AS x(company_name text,industry text)
              GROUP BY 1
            )
            SELECT COALESCE(NULLIF(BTRIM(s.salesperson),''),'Unassigned') AS salesperson,
                   COALESCE(m.industry,'Unclassified') AS industry,
                   COUNT(*) AS shipment_rows,COUNT(DISTINCT s.key) AS distinct_shipments,
                   COUNT(DISTINCT NULLIF(BTRIM(s.shipper),'')) AS distinct_shippers,
                   COUNT(DISTINCT NULLIF(BTRIM(s.consignee),'')) AS distinct_consignees
            FROM ai_insights_source.current_shipments s
            LEFT JOIN industry_map m
              ON LOWER(BTRIM(CASE WHEN s.report_type IN ('AE','OE') THEN s.shipper ELSE s.consignee END))=m.name
            WHERE """+where+"""
            GROUP BY 1,2 ORDER BY shipment_rows DESC,salesperson,industry"""),params).mappings()]
    except Exception as exc:
        logger.warning("Salesperson industry query unavailable (%s)",type(exc).__name__)
        raise HTTPException(503,"Salesperson source field is not yet available. Apply the expanded read-only shipment view.")
    return {"rows":rows,"basis":"ERP Sales Person source field; job_owner is separate; export attributed to shipper and import to consignee; saved classifications with a valid industry only."}

@app.get("/api/classifications/salesperson-industry/export")
def salesperson_industry_export(company:str|None=None,lob:str|None=None,start:str|None=None,end:str|None=None,origin:str|None=None,destination:str|None=None,shipper:str|None=None,consignee:str|None=None,branch:str|None=None,user=Depends(current_user)):
    data=salesperson_industry(company,lob,start,end,origin,destination,shipper,consignee,branch,user)
    rows=data["rows"]
    output=workbook_bytes([
      ("Salesperson industry mix",["ERP Sales Person","Industry vertical","Shipment rows","Distinct shipments","Shippers","Consignees"],
       [[r.get("salesperson"),r.get("industry"),r.get("shipment_rows"),r.get("distinct_shipments"),r.get("distinct_shippers"),r.get("distinct_consignees")] for r in rows]),
      ("Applied filters",["Filter","Value"],[[k,v] for k,v in {"company":company,"department":lob,"start":start,"end":end,"origin":origin,"destination":destination,"shipper":shipper,"consignee":consignee,"branch":branch}.items() if v]),
      ("Methodology",["Basis"],[[data["basis"]]])
    ])
    return StreamingResponse(BytesIO(output),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
       headers={"Content-Disposition":"attachment; filename=ai-insights-salesperson-industry-mix.xlsx","Cache-Control":"no-store"})

@app.get("/api/classifications")
def classifications_api(response: Response,q: str="",offset:int=0,limit:int=10,user=Depends(current_user)):
    if len(q)>100: raise HTTPException(400,"Search too long")
    # Classification data changes immediately after Excel import; never serve a stale register.
    if response is not None:
        response.headers["Cache-Control"]="no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"]="no-cache"
        response.headers["Expires"]="0"
    page_limit=min(max(int(limit),1),100)
    page_offset=max(int(offset),0)
    return {"results":auth.classification_list(q,limit=page_limit,offset=page_offset),
            "total":auth.classification_count(q),"limit":page_limit,"offset":page_offset}

@app.post("/api/classifications/save")
@app.post("/api/admin/classifications")
async def classification_upsert(request: Request,user=Depends(require_classification_admin)):
    same_origin(request)
    payload=await request.json()
    try:
        auth.classification_save(user["id"],payload["company_name"],payload["industry"],
            payload["confidence"],payload["source"],payload.get("country",""))
        return {"ok":True,"status":"classified"}
    except (ValueError,KeyError,TypeError,AttributeError) as exc:
        raise HTTPException(400,str(exc))

@app.get("/api/admin/reconciliation")
def reconciliation(user=Depends(require_admin)):
    if not _database_verified: raise HTTPException(503,"Source not verified")
    engine=scoped_engine()
    try:
        with engine.connect() as conn:
            rows=[dict(r) for r in conn.execute(text("""
                SELECT company,report_type,COUNT(*) AS shipment_rows,
                       COUNT(DISTINCT key) AS distinct_keys,
                       COUNT(*) FILTER(WHERE shipment_date IS NULL) AS missing_dates,
                       COUNT(*) FILTER(WHERE NULLIF(BTRIM(shipper),'') IS NULL) AS missing_shippers,
                       COUNT(*) FILTER(WHERE NULLIF(BTRIM(consignee),'') IS NULL) AS missing_consignees
                FROM ai_insights_source.current_shipments
                WHERE company=ANY(:companies) AND report_type=ANY(:lobs)
                GROUP BY company,report_type ORDER BY company,report_type
            """),{"companies":user["companies"],"lobs":user["lobs"]}).mappings()]
        return {"rows":rows,"total":sum(int(x["shipment_rows"]) for x in rows),
                "status":"Aggregated reconciliation only; independently sourced registers not yet compared"}

    finally: pass
@app.get("/api/admin/users")
def admin_users(user=Depends(require_admin)):
    return {"users":auth.list_users()}

@app.get("/api/admin/audit")
def admin_audit(user=Depends(require_admin)):
    return {"events":auth.audit_events()}

@app.post("/api/admin/users")
async def admin_create(request: Request, user=Depends(require_admin)):
    same_origin(request)
    payload=await request.json()
    try:
        if not isinstance(payload,dict):
            raise ValueError("Invalid input")
        uid=auth.add_user(user["id"],payload["email"],payload.get("name",""),
                          payload["password"],payload.get("role","viewer"),
                          payload["companies"],payload["lobs"])
        return {"id":uid}
    except (ValueError,KeyError,TypeError) as exc:
        raise HTTPException(400,str(exc))

@app.patch("/api/admin/users/{uid}")
async def admin_update(uid: int, request: Request, user=Depends(require_admin)):
    same_origin(request)
    payload=await request.json()
    try:
        if not isinstance(payload,dict):
            raise ValueError("Invalid input")
        auth.edit_user(user["id"],uid,**{k:payload[k] for k in
                       ("active","companies","lobs","role") if k in payload})
        return {"ok":True}
    except (ValueError,TypeError) as exc:
        raise HTTPException(400,str(exc))

@app.post("/api/admin/users/{uid}/password")
async def admin_reset(uid: int, request: Request, user=Depends(require_admin)):
    same_origin(request)
    payload=await request.json()
    try:
        auth.reset_password(user["id"],uid,payload["password"])
        return {"ok":True}
    except (ValueError,KeyError,TypeError) as exc:
        raise HTTPException(400,str(exc))

@app.get("/api/{path:path}")
def locked_api(path: str):
    raise HTTPException(404, "Feature not available")
