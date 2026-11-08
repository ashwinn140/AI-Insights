# AI Insights release controls

**Do not deploy the current starter to an internet-accessible production domain.** It uses a shared administrator token and does not implement the promised secure single sign-on.

## Deployment gates
1. Verify the actual production shipment schema against `deployment/03_operational_reconciliation.sql`.
2. Apply reviewed restricted-role SQL as a database administrator; test SELECT on the approved view and denial on financial and authentication tables.
3. Implement user-level authorization and company/LOB scope enforcement; do not reuse NG-Dashboard session cookies across unrelated domains.
4. Provision separate durable classification storage; no writes to NG-Dashboard tables.
5. Add CSRF protections, file-upload hardening, batch-bound Gemini review, audit identity, and rollback.
6. Test source snapshots, reconciliation, concurrent review and production recovery.
7. Deploy only to the separate Railway project, verify terminal SUCCESS, authenticated access, logs and health.
8. Keep NG-Dashboard repository, environment variables, services and database schema unchanged.

## Source semantics
`shipments.to_import IS NULL` means active/current version; `company` is NG/NCS and `report_type` is AE/AI/OE/OI. Shipment counts and shipper/consignee appearances are different measures. Financial tables are out of scope.

## Status
Repository scaffolding and SQL preparation only. Live source verification, secure authentication, and deployment remain pending.
