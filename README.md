# AI Insights — Operations Intelligence

Independent NGL/NCS shipment industry classification and operational intelligence. This repository is separate from NG-Dashboard.

## Deployment status
Repository scaffolding only. **Not production deployed.** Do not connect to production or expose publicly until the full application source is committed and security gates are met.

## Non-negotiable controls
- Read-only access to approved operational shipment views, not finance tables.
- Existing NG-Dashboard code, service, and database tables must remain unchanged.
- Classification changes go to isolated writable storage.
- Live shipment count uses current rows (`to_import IS NULL`) and reconciles with source.
- Secure user authentication must be implemented before exposure; shared static admin token is not production authentication.
- Saturday 07:00 IST workbook export must have persistent private storage and audit logging.

The full application build is retained in the separate deployment candidate package pending migration and security review.
