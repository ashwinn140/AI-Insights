-- Run as the restricted ai_insights_reader (not the database owner).
-- Success: SELECT works for the approved operational view only.
SELECT COUNT(*) AS current_shipments FROM ai_insights_source.current_shipments;
SELECT has_schema_privilege(current_user,'ai_insights_source','USAGE') AS source_schema_usage,
       has_table_privilege(current_user,'ai_insights_source.current_shipments','SELECT') AS can_read_shipments,
       has_table_privilege(current_user,'public.profit_lines','SELECT') AS can_read_profit,
       has_table_privilege(current_user,'public.users','SELECT') AS can_read_users,
       has_table_privilege(current_user,'public.sessions','SELECT') AS can_read_sessions;
-- Expected: true,true,false,false,false. If any denied table reads true,
-- stop and review inherited/PUBLIC grants before production.
