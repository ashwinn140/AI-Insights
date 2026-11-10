"""Operational-only Industry Explorer query layer.

No routes expose this layer until user-level authentication and scope enforcement
are implemented. Query only the restricted view; never touch financial tables.
"""
from sqlalchemy import text

ALLOWED_COMPANIES = frozenset({"NG", "NCS"})
ALLOWED_LOBS = frozenset({"AE", "AI", "OE", "OI"})

def validate_scope(companies, lobs):
    cs, ls = frozenset(companies), frozenset(lobs)
    if not cs or not ls or not cs <= ALLOWED_COMPANIES or not ls <= ALLOWED_LOBS:
        raise ValueError("Invalid or empty authorized scope")
    return sorted(cs), sorted(ls)

def summary(engine, *, companies, lobs):
    """Aggregate shipment counts and volume within a caller's verified scope.

    Caller must derive companies/lobs from a trusted authenticated identity.
    Do not pass client-supplied scope without intersecting authorized scope.
    """
    companies, lobs = validate_scope(companies, lobs)
    query = text("""
        SELECT company, report_type, COUNT(*) AS shipment_rows,
               COUNT(DISTINCT key) AS unique_shipments,
               COUNT(*) FILTER (WHERE NULLIF(BTRIM(shipper),'') IS NOT NULL)
                   AS shipper_appearances,
               COUNT(*) FILTER (WHERE NULLIF(BTRIM(consignee),'') IS NOT NULL)
                   AS consignee_appearances,
               COALESCE(SUM(teus),0) AS total_teus,
               COALESCE(SUM(gross_wt),0) AS gross_weight
        FROM ai_insights_source.current_shipments
        WHERE company = ANY(:companies) AND report_type = ANY(:lobs)
        GROUP BY company, report_type
        ORDER BY company, report_type
    """)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(query, {"companies":companies,"lobs":lobs}).mappings()]

def top_trade_lanes(engine, *, companies, lobs, limit=25):
    companies, lobs = validate_scope(companies, lobs)
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    query = text("""
        SELECT COALESCE(NULLIF(BTRIM(origin),''),'Unknown') AS origin,
               COALESCE(NULLIF(BTRIM(destination),''),'Unknown') AS destination,
               COUNT(*) AS shipment_rows
        FROM ai_insights_source.current_shipments
        WHERE company = ANY(:companies) AND report_type = ANY(:lobs)
        GROUP BY 1,2 ORDER BY shipment_rows DESC, origin, destination
        LIMIT :limit
    """)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(query, {"companies":companies,"lobs":lobs,"limit":limit}).mappings()]

def company_appearances(engine, *, companies, lobs, limit=25):
    companies, lobs = validate_scope(companies, lobs)
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Invalid limit")
    query = text("""
        SELECT role, company_name, COUNT(*) AS appearances
        FROM (
            SELECT 'shipper' AS role, NULLIF(BTRIM(shipper),'') AS company_name
            FROM ai_insights_source.current_shipments
            WHERE company = ANY(:companies) AND report_type = ANY(:lobs)
            UNION ALL
            SELECT 'consignee' AS role, NULLIF(BTRIM(consignee),'') AS company_name
            FROM ai_insights_source.current_shipments
            WHERE company = ANY(:companies) AND report_type = ANY(:lobs)
        ) names WHERE company_name IS NOT NULL
        GROUP BY role, company_name
        ORDER BY appearances DESC, role, company_name
        LIMIT :limit
    """)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(query, {"companies":companies,"lobs":lobs,"limit":limit}).mappings()]
