-- AI Insights: read-only source inventory for NG-Dashboard.
-- Run using an authorized database administrator connection.
-- This file does NOT grant privileges, copy data, or modify the dashboard.
-- The AI Insights application role must NOT be granted users/sessions/login_tokens/uploads/prefs/settings/admin_log.
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema='public'
  AND table_name IN ('shipments','profit_lines','org_master','imports','current_import')
ORDER BY table_name, ordinal_position;

-- Discover extra ERP fields without retrieving customer or financial values.
SELECT 'shipments' AS dataset, k.key AS extra_column, COUNT(*) AS populated_rows
FROM public.shipments s
CROSS JOIN LATERAL jsonb_object_keys(COALESCE(s.extra::jsonb,'{}'::jsonb)) AS k(key)
WHERE s.to_import IS NULL
GROUP BY k.key
UNION ALL
SELECT 'profit_lines', k.key, COUNT(*)
FROM public.profit_lines p
CROSS JOIN LATERAL jsonb_object_keys(COALESCE(p.extra::jsonb,'{}'::jsonb)) AS k(key)
WHERE p.to_import IS NULL
GROUP BY k.key
ORDER BY dataset, populated_rows DESC;

-- Count active records by company and department without exposing row contents.
SELECT 'shipments' AS dataset, company, report_type AS department, COUNT(*) AS active_rows,
       MIN(shipment_date) AS first_date, MAX(shipment_date) AS last_date
FROM public.shipments WHERE to_import IS NULL
GROUP BY company,report_type
UNION ALL
SELECT 'profit_lines', company, lob, COUNT(*),MIN(job_date),MAX(job_date)
FROM public.profit_lines
WHERE to_import IS NULL
GROUP BY company,lob
ORDER BY dataset,company,department;

-- Before enabling finance analytics:
-- 1. Verify that profit_lines contain current job-date format (exclude legacy charge rows).
-- 2. Build dedicated SECURITY-INVOKER or tightly granted read-only views with company/LOB scope.
-- 3. Enforce finance permission on the server; no raw generic table browser.
-- 4. Reconcile shipment/job keys and prevent fan-out joins or double-counting.
-- 5. Never expose operational security/authentication tables.
