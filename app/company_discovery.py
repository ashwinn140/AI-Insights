"""Scoped company discovery and evidence-labeled opportunity candidates."""
from sqlalchemy import text
from .crossfilter import conditions

VIEW="ai_insights_source.current_shipments"
def search_companies(engine, *, companies,lobs,term="",limit=50,filters=None):
    term=(term or "").strip()
    if len(term)>100: raise ValueError("Search too long")
    where,params=conditions(companies,lobs,filters or {})
    params.update(term=term,limit=min(limit,100))
    q=text(f"""
        WITH names AS (
          SELECT NULLIF(BTRIM(shipper),'') AS name,'shipper' AS role,
                 origin,destination FROM {VIEW} WHERE {where}
          UNION ALL
          SELECT NULLIF(BTRIM(consignee),'') AS name,'consignee' AS role,
                 origin,destination FROM {VIEW} WHERE {where}
        )
        SELECT name,role,COUNT(*) AS appearances,
               COUNT(DISTINCT COALESCE(origin,'') || ' → ' || COALESCE(destination,'')) AS lanes
          FROM names WHERE name IS NOT NULL
            AND (:term='' OR name ILIKE '%' || :term || '%')
         GROUP BY name,role ORDER BY appearances DESC,name,role LIMIT :limit
    """)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(q,params).mappings()]

def opportunity_candidates(engine, *, companies,lobs,limit=50,filters=None):
    """Participation and lane breadth are indicators only, not verified new prospects."""
    where,params=conditions(companies,lobs,filters or {})
    params["limit"]=min(limit,100)
    q=text(f"""
        WITH names AS (
          SELECT NULLIF(BTRIM(shipper),'') AS name,origin,destination
          FROM {VIEW} WHERE {where}
          UNION ALL
          SELECT NULLIF(BTRIM(consignee),'') AS name,origin,destination
          FROM {VIEW} WHERE {where}
        )
        SELECT name,COUNT(*) AS appearances,
               COUNT(DISTINCT COALESCE(origin,'') || ' → ' || COALESCE(destination,'')) AS lane_count
        FROM names WHERE name IS NOT NULL GROUP BY name
        HAVING COUNT(*)>=5 ORDER BY lane_count DESC,appearances DESC,name LIMIT :limit
    """)
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(q,params).mappings()]
