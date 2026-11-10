"""Standalone read-only source adapter. Import into app after verified credential provisioning."""
import os
from sqlalchemy import create_engine, text

def operational_engine():
    url = os.environ["SHIPMENT_READONLY_DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0,
                         connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=10000"})

def counts(engine):
    sql = text("""
        SELECT company, report_type, COUNT(*) AS active_rows,
               COUNT(DISTINCT key) AS unique_keys,
               COUNT(*) FILTER (WHERE NULLIF(BTRIM(shipper),'') IS NOT NULL) AS shipper_appearances,
               COUNT(*) FILTER (WHERE NULLIF(BTRIM(consignee),'') IS NOT NULL) AS consignee_appearances
        FROM ai_insights_source.current_shipments
        GROUP BY company, report_type
        ORDER BY company, report_type
    """)
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(sql).mappings()]
