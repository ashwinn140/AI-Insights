"""Fail-closed AI Insights deployment with a restricted, startup-only database probe.

No customer data is returned until authentication and authorization are implemented.
"""
import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import HTMLResponse
from pathlib import Path
from app import independent_auth as auth
from app.industry_explorer import summary, top_trade_lanes, company_appearances
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
    if auth.provision_initial_admin():
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

@app.get("/api/{path:path}")
def locked_api(path: str):
    raise HTTPException(404, "Feature not available")
