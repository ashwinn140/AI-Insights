"""Contract tests for the operational source; no live database or credentials required."""
from pathlib import Path

SQL = Path(__file__).resolve().parents[1].joinpath("deployment/03_operational_reconciliation.sql").read_text()
VIEW = Path(__file__).resolve().parents[1].joinpath("deployment/04_readonly_role_template.sql").read_text()
MAIN = Path(__file__).resolve().parents[1].joinpath("main.py").read_text()

def test_current_versions_only():
    assert "to_import IS NULL" in SQL
    assert "to_import IS NULL" in VIEW

def test_no_financial_fields_in_source_view():
    statement = VIEW.split("CREATE OR REPLACE VIEW",1)[1].split("FROM public.shipments",1)[0].lower()
    for field in ("profit", "income", "expense", "revenue", "invoice", "amount", "margin"):
        assert field not in statement

def test_no_source_table_writes():
    sql = VIEW.lower()
    for statement in ("update public.shipments", "delete from public.shipments", "insert into public.shipments", "alter table public.shipments"):
        assert statement not in sql


def test_salesperson_comes_from_erp_sales_person_extra_not_job_owner():
    statement = VIEW.split("CREATE OR REPLACE VIEW",1)[1].split("FROM public.shipments",1)[0]
    assert "extra ->> 'Sales Person' AS salesperson" in statement
    assert "job_owner" in statement
    assert "job_owner AS salesperson" not in statement

def test_salesperson_analytics_uses_dedicated_source_field_and_pending_export_context():
    assert "s.salesperson" in MAIN
    assert "salesperson_names" in MAIN
    assert "job_owner_names" in MAIN
    assert "expanded read-only shipment view is not ready" in MAIN

def test_startup_verifies_expanded_shipment_fields():
    assert 'required_columns = ["shipper","consignee","carrier","job_owner","salesperson"]' in MAIN
    assert "read-only analytics enabled" in MAIN
    assert "data API disabled" not in MAIN


def test_dashboard_export_requests_complete_result_sets():
    assert "dashboard_filters(origin,destination,shipper,consignee,branch,start,end),limit=10000)" in MAIN

def test_research_directory_returns_country_and_renders_matching_column():
    research = Path(__file__).resolve().parents[1].joinpath("app/research_catalog.py").read_text()
    page = Path(__file__).resolve().parents[1].joinpath("app/classifications.html").read_text()
    assert "original_name,normalized_name,canonical_entity,country," in research
    assert "['original_name','country','industry','verification_status','appearances']" in page

def test_pending_workbook_excludes_already_classified_research_entities():
    auth = Path(__file__).resolve().parents[1].joinpath("app/independent_auth.py").read_text()
    section = auth.split("def pending_classification_names",1)[1].split("def classification_industry_status",1)[0]
    assert "WHERE NOT EXISTS" in section
    assert "TRIM(COALESCE(c.industry,'')) <> ''" in section
