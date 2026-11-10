# AI Insights — Security, data and release controls

## Current production architecture

- Production runs as a separate Railway service and project environment from NG-Dashboard.
- Authentication is independent and stored in SQLite on the AI-Insights persistent volume mounted at `/ai-data`.
- Passwords are stored as salted scrypt hashes; session tokens are random and only their SHA-256 hashes are stored.
- Sessions expire after 12 hours. The session cookie is HttpOnly, Secure and SameSite=Lax.
- Failed sign-ins are rate-limited by a temporary account lock after five consecutive failures.
- Mutating browser requests require a matching Origin and Host (same-origin check).
- User authorization scopes company and department access to NG/NCS and AE/AI/OE/OI.
- System administration is restricted to administrator role. Classification save/import is available to any authenticated user.
- Analytics connect only as `ai_insights_reader`, with read-only transaction settings and a 10-second statement timeout.
- Startup verifies the restricted view and explicitly checks that the reader cannot SELECT the base shipment, profit, user or session tables.
- No financial/profitability data is exposed by the approved shipment view.
- Classification data, history and audit records are isolated from NG-Dashboard data storage.

## Production readiness checks

The application exposes `/healthz`. Railway's deployment health check targets this route. It reports data access as verified only when the restricted source probe and required shipment columns pass.

Required environment variables:
- `AI_BOOTSTRAP_EMAIL`, `AI_BOOTSTRAP_PASSWORD` (one-time initial administrator provisioning only)
- `SHIPMENT_DB_HOST`, `SHIPMENT_DB_NAME`, `SHIPMENT_DB_PORT`, `SHIPMENT_DB_USER`, `SHIPMENT_DB_PASSWORD`

The database user must be exactly `ai_insights_reader`. Do not grant it direct access to base shipment, profit, user or session tables.

## Operational boundaries

- Shipment rows, distinct shipment keys, appearances and TEUs are operational measures; they are not revenue, margin, gross profit or confirmed pipeline.
- Company-name matching is exact/normalized only where the relevant query explicitly states so. Similar names are not proof of a common legal entity.
- Industry classification requires company-specific evidence. Salesperson and job-owner values are contextual clues, not proof.
- A workbook import reads the first/import sheet only, validates the canonical 15 industries, and skips blank industry rows.
- The legacy `approved` database column remains for compatibility only; it is not an approval workflow.
- Do not run destructive resets, bulk deletes, or classification archive operations without explicit user authorization and a verified backup.

## Release process

1. Review the diff and tests in a pull request.
2. Require compilation, FastAPI import and the complete unittest suite to pass.
3. Merge to `main` only after reviewing the change.
4. Confirm Railway deployment SUCCESS and inspect startup/health-check logs.
5. Confirm the persistent volume remains mounted and source verification passes.
6. Verify the affected UI/API paths. Authenticated browser verification is separate from server health.
7. Keep NG-Dashboard and its database schema/configuration untouched unless separately authorized.

## Known verification boundary

Automated tests and Railway health/startup logs do not prove every authenticated browser workflow, visual rendering, cross-filter interaction, workbook download/upload, or role-specific screen. Those require a browser session authenticated to AI-Insights and explicit end-to-end checks.