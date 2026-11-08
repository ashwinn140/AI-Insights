"""Scoped company discovery from approved operational view only."""
from sqlalchemy import text
from .industry_explorer import validate_scope

def search_companies(engine, *, companies, lobs, term="", limit=50):
    companies,lobs=validate_scope(companies,lobs)
    term=(term or "").strip()
    if len(term)>100: raise ValueError("Search too long")
    q=text("""
        WITH names AS (
            SELECT NULLIF(BTRIM(shipper),'') AS name, 'shipper' AS role,
                   origin,destination,shipment_date
              FROM ai_insights_source.current_shipments
             WHERE company=ANY(:companies) AND report_type=ANY(:lobs)
            UNION ALL
            SELECT NULLIF(BTRIM(consignee),'') AS name, 'consignee' AS role,
                   origin,destination,shipment_date
              FROM ai_insights_source.current_shipments
             WHERE company=ANY(:companies) AND report_type=ANY(:lobs)
        )
        SELECT name,role,COUNT(*) AS appearances,
               COUNT(DISTINCT COALESCE(origin,'') || ' → ' || COALESCE(destination,'')) AS lanes
          FROM names WHERE name IS NOT NULL
            AND (:term = '' OR name ILIKE '%' || :term || '%')
         GROUP BY name,role
         ORDER BY appearances DESC,name,role LIMIT :limit
    """)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(q,dict(companies=companies,lobs=lobs,term=term,limit=min(limit,100))).mappings()]

def opportunity_candidates(engine, *, companies, lobs, limit=50):
    """Heuristic only: high observed shipment participation, not verified prospect status."""
    companies,lobs=validate_scope(companies,lobs)
    q=text("""
        WITH participation AS (
          SELECT NULLIF(BTRIM(shipper),'') AS name, origin,destination
          FROM ai_insights_source.current_shipments
          WHERE company=ANY(:companies) AND report_type=ANY(:lobs)
          UNION ALL
          SELECT NULLIF(BTRIM(consignee),'') AS name,origin,destination
          FROM ai_insights_source.current_shipments
          WHERE company=ANY(:companies) AND report_type=ANY(:lobs)
        )
        SELECT name, COUNT(*) AS appearances,
               COUNT(DISTINCT COALESCE(origin,'') || ' → ' || COALESCE(destination,'')) AS lane_count
          FROM participation WHERE name IS NOT NULL
         GROUP BY name HAVING COUNT(*)>=5
         ORDER BY lane_count DESC,appearances DESC,name LIMIT :limit
    """)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(q,dict(companies=companies,lobs=lobs,limit=min(limit,100))).mappings()]
