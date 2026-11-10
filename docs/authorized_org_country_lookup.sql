-- Authorized read-only country lookup for AI Insights.
-- Run once as the owner/administrator of NG-Dashboard PostgreSQL.
-- Do not modify NG-Dashboard application code or operational tables.
CREATE SCHEMA IF NOT EXISTS ai_insights_source;
CREATE OR REPLACE VIEW ai_insights_source.organization_country AS
SELECT company, norm_key, name, NULLIF(BTRIM(country),'') AS country, updated_at
FROM public.org_master
WHERE NULLIF(BTRIM(name),'') IS NOT NULL
  AND NULLIF(BTRIM(country),'') IS NOT NULL;
-- Apply only to the existing AI Insights reader role.
GRANT USAGE ON SCHEMA ai_insights_source TO ai_insights_reader;
GRANT SELECT ON ai_insights_source.organization_country TO ai_insights_reader;
-- No grants on public.org_master or finance/security tables.
