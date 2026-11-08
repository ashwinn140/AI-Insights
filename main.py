"""Fail-closed deployment shell for independent AI Insights.

No customer data is served until operational source, storage, and authentication
are explicitly provisioned and verified. Never import NG-Dashboard app modules.
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

app = FastAPI(title="AI Insights Operations", docs_url=None, redoc_url=None, openapi_url=None)

@app.get("/healthz")
def healthz():
    return {"status":"running","product":"AI Insights","data_access":"disabled","production_ready":False}

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Insights</title><style>body{font:16px system-ui;background:#0b1220;color:#edf2f7;margin:0;display:grid;min-height:100vh;place-items:center}
main{max-width:650px;padding:40px}h1{font-size:42px}p{line-height:1.7;color:#b7c7d9}
small{color:#9db0c6}.status{display:inline-block;border:1px solid #526174;border-radius:20px;padding:6px 14px}</style>
<main><small>INDEPENDENT OPERATIONS INTELLIGENCE</small><h1>AI Insights</h1>
<p class="status">Private deployment — access not activated</p>
<p>The service is deployed separately from NG-Dashboard. Industry intelligence and customer data access remain disabled until secure authentication, restricted shipment permissions, and reconciliation pass.</p>
<small>No profitability data is connected. Existing dashboard remains unchanged.</small></main></html>"""

@app.get("/api/{path:path}")
def locked_api(path: str):
    raise HTTPException(status_code=503,detail="AI Insights data access is disabled pending production security gates")
