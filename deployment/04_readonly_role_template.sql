-- REVIEW BEFORE RUNNING. This script only creates a role and read-only view.
-- Requires an authorized PostgreSQL administrator. Run once, in a transaction.
-- Set a strong generated password securely outside source control.
BEGIN;
CREATE SCHEMA IF NOT EXISTS ai_insights_source;
CREATE OR REPLACE VIEW ai_insights_source.current_shipments AS
SELECT id, company, report_type, key, shipment_no, shipment_date,
       branch, customer, shipper, consignee, origin, origin_code,
       destination, destination_code, gross_wt, chargeable_wt,
       teus, volume, cargo_type, consol_type, nomination, status, stage,
       carrier, job_owner, job_owner AS salesperson
FROM public.shipments WHERE to_import IS NULL;
-- Create role only if it does not exist (psql-compatible PL/pgSQL).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='ai_insights_reader') THEN
    CREATE ROLE ai_insights_reader LOGIN NOINHERIT;
  END IF;
END $$;
REVOKE ALL ON SCHEMA ai_insights_source FROM PUBLIC;
GRANT USAGE ON SCHEMA ai_insights_source TO ai_insights_reader;
GRANT SELECT ON ai_insights_source.current_shipments TO ai_insights_reader;
-- IMPORTANT: Review PUBLIC grants and default database/schema grants separately.
-- No GRANT on profit_lines, users, sessions, or other dashboard tables.
COMMIT;
