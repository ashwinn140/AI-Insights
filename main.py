"""Fail-closed AI Insights deployment with a restricted, startup-only database probe.

No customer data is returned until authentication and authorization are implemented.
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, Depends, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from pathlib import Path
from io import BytesIO
from app.crossfilter import query_rows,filter_options
from app.excel_tools import analytics_export,parse_classification_xlsx,classification_template,workbook_bytes
from app import independent_auth as auth
from app.industry_explorer import summary, top_trade_lanes, company_appearances
from app.company_discovery import search_companies, opportunity_candidates
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
            count = conn.execute(text("SELECT COUNT(*) FROM ai_insights_source.current_shipments")).scalar_one()
            logger.info("Source check passed: approved operational view accessible; active_rows=%d; data API disabled", count)
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
    yield

app = FastAPI(title="AI Insights Operations", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)

@app.get("/healthz")
def healthz():
    return {"status": "running", "product": "AI Insights",
            "data_access": "disabled", "production_ready": False}

def same_origin(request: Request):
    origin = request.headers.get("origin")
    host = request.headers.get("host", "")
    if not origin or not host or origin not in ("https://" + host, "http://localhost:" + host.rsplit(":",1)[-1]):
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
    from sqlalchemy.engine import URL
    url = URL.create("postgresql+psycopg2", username=os.environ["SHIPMENT_DB_USER"],
                     password=os.environ["SHIPMENT_DB_PASSWORD"],
                     host=os.environ["SHIPMENT_DB_HOST"],
                     port=int(os.environ["SHIPMENT_DB_PORT"]),
                     database=os.environ["SHIPMENT_DB_NAME"])
    engine = create_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0,
        connect_args={"connect_timeout":5,"options":"-c default_transaction_read_only=on -c statement_timeout=10000"})
    try:
        return {"summary":summary(engine,companies=companies,lobs=lobs),
                "lanes":top_trade_lanes(engine,companies=companies,lobs=lobs),
                "participants":company_appearances(engine,companies=companies,lobs=lobs)}
    finally:
        engine.dispose()

def scoped_engine():
    url=URL.create("postgresql+psycopg2", username=os.environ["SHIPMENT_DB_USER"],
        password=os.environ["SHIPMENT_DB_PASSWORD"],host=os.environ["SHIPMENT_DB_HOST"],
        port=int(os.environ["SHIPMENT_DB_PORT"]),database=os.environ["SHIPMENT_DB_NAME"])
    return create_engine(url,pool_pre_ping=True,pool_size=1,max_overflow=0,
        connect_args={"connect_timeout":5,"options":"-c default_transaction_read_only=on -c statement_timeout=10000"})

def allowed_scope(user,company,lob):
    if not _database_verified: raise HTTPException(503,"Source not verified")
    def parse(raw,authorized):
        if not raw: return authorized
        values=list(dict.fromkeys(x.strip() for x in raw.split(",") if x.strip()))
        if not values or len(values)>len(authorized) or any(v not in authorized for v in values):
            raise HTTPException(403,"Selection outside authorized scope")
        return values
    return parse(company,user["companies"]),parse(lob,user["lobs"])

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
    finally: engine.dispose()

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
    finally: engine.dispose()

@app.get("/api/dashboard/export")
def dashboard_export(company: str|None=None,lob: str|None=None,origin: str|None=None,
              destination: str|None=None,shipper: str|None=None,consignee: str|None=None,
              branch: str|None=None,start: str|None=None,end: str|None=None,
              user=Depends(current_user)):
    companies,lobs=allowed_scope(user,company,lob)
    engine=scoped_engine()
    try:
        data=query_rows(engine,companies,lobs,
            dashboard_filters(origin,destination,shipper,consignee,branch,start,end),limit=100)
        output=analytics_export(data)
    except ValueError as exc: raise HTTPException(400,str(exc))
    finally: engine.dispose()
    return StreamingResponse(BytesIO(output),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-operations.xlsx",
                 "Cache-Control":"no-store"})

@app.get("/api/admin/classifications/template")
def classification_xlsx_template(user=Depends(require_admin)):
    return StreamingResponse(BytesIO(classification_template()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-classification-template.xlsx",
                 "Cache-Control":"no-store"})

@app.get("/api/admin/classifications/export")
def classification_xlsx_export(user=Depends(require_admin)):
    rows=auth.classification_list(limit=500)
    output=workbook_bytes([("Classifications",
        ["company_name","industry","confidence","source","approved"],
        [[r["company_name"],r["industry"],r["confidence"],r["source"],
          "Yes" if r["approved"] else "No"] for r in rows])])
    return StreamingResponse(BytesIO(output),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":"attachment; filename=ai-insights-classifications.xlsx",
                 "Cache-Control":"no-store"})

@app.post("/api/admin/classifications/import")
async def classification_xlsx_import(request:Request,file:UploadFile=File(...),user=Depends(require_admin)):
    same_origin(request)
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(400,"XLSX file required")
    payload=await file.read(2*1024*1024+1)
    try:
        rows=parse_classification_xlsx(payload)
        count=auth.classification_import(user["id"],rows)
        return {"imported":count}
    except ValueError as exc: raise HTTPException(400,str(exc))

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
    finally: engine.dispose()

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
            rows=search_companies(engine,companies=companies,lobs=lobs,term=q,limit=100,filters=filters)
            cols=["Company name","Role","Appearances","Distinct lanes"]
            fields=["name","role","appearances","lanes"]
        else:
            rows=opportunity_candidates(engine,companies=companies,lobs=lobs,limit=100,filters=filters)
            cols=["Company name","Appearances","Distinct lanes"]
            fields=["name","appearances","lane_count"]
        output=workbook_bytes([(kind.title(),cols,[[r.get(k) for k in fields] for r in rows]),
            ("Applied filters",["Filter","Value"],[(k,str(v)) for k,v in filters.items() if v])])
    finally: engine.dispose()
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
    finally: engine.dispose()

@app.get("/admin", response_class=HTMLResponse)
def admin_page(user=Depends(require_admin)):
    return Path(__file__).parent.joinpath("app/admin.html").read_text()

@app.get("/classifications",response_class=HTMLResponse)
def classification_page(user=Depends(current_user)):
    return Path(__file__).parent.joinpath("app/classifications.html").read_text()

@app.get("/api/classifications")
def classifications_api(q: str="",user=Depends(require_admin)):
    if len(q)>100: raise HTTPException(400,"Search too long")
    return {"results":auth.classification_list(q)}

@app.post("/api/admin/classifications")
async def classification_upsert(request: Request,user=Depends(require_admin)):
    same_origin(request)
    payload=await request.json()
    try:
        auth.classification_save(user["id"],payload["company_name"],payload["industry"],
            payload["confidence"],payload["source"],payload.get("approved",False))
        return {"ok":True}
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
    finally: engine.dispose()

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
