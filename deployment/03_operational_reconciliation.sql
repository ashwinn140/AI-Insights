-- Read-only reconciliation. Run against NG-Dashboard PostgreSQL as an authorized DBA.
-- No DDL, writes, finance tables or user-table access.
SELECT company, report_type, COUNT(*) AS current_rows,
       COUNT(DISTINCT key) AS distinct_keys,
       COUNT(*) FILTER (WHERE NULLIF(BTRIM(shipper),'') IS NOT NULL) AS shipper_appearances,
       COUNT(*) FILTER (WHERE NULLIF(BTRIM(consignee),'') IS NOT NULL) AS consignee_appearances,
       COUNT(*) FILTER (WHERE shipment_date IS NULL) AS missing_shipment_dates
FROM public.shipments
WHERE to_import IS NULL
GROUP BY company, report_type
ORDER BY company, report_type;

-- Check unexpected duplicate current keys without changing data.
SELECT company, report_type, key, COUNT(*) AS copies
FROM public.shipments
WHERE to_import IS NULL
GROUP BY company, report_type, key
HAVING COUNT(*) > 1
ORDER BY copies DESC LIMIT 100;

-- No inference that appearance counts equal distinct shipment counts.
