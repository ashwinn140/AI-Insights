# AI Insights — Operations Intelligence

AI Insights is a separately deployed application for shipment operations intelligence, industry classification and evidence-led organisation discovery.

## Production application
- URL: https://ai-insights-production-3d81.up.railway.app
- Repository: https://github.com/ashwinn140/AI-Insights
- Runtime: Railway production service `AI-Insights`
- Data source: restricted read-only view `ai_insights_source.current_shipments`
- Writable classification, authentication, research and audit data: isolated persistent `/ai-data` volume
- Company / department scopes: NG and NCS; AE, AI, OE and OI, intersected with each authenticated user's permissions.

## Application areas
- **Operations Overview:** shipment KPIs, monthly trends, company/department breakdown, trade lanes, counterparties and branches. Cross-filters apply to the same read-only query set and Excel export.
- **Industry Classification:** 15 canonical industry verticals, manual and workbook classification, evidence/confidence, pending register, industry trend, vertical drilldown, contributor records and salesperson-wise industry mix.
- **Company Explorer:** shipper/consignee appearances and distinct lane breadth from authorised operational shipment records.
- **Activity-based Discovery:** candidate organisations ranked by observed participation and lane breadth. These are research candidates, not verified prospects or sales pipeline opportunities.
- **Research Master:** separately imported historical research entities with evidence and verification status. It does not silently overwrite manually saved classifications.
- **Administration:** user access, scope management, audit and controlled archive/reset tools.

## Classification workbook contract
- Sheet 1 is the import data sheet.
- Sheet 2 is the AI Prompt and canonical 15-industry master.
- Blank industries remain pending; invalid labels are rejected.
- Every nonblank classification must include confidence and evidence.
- All authenticated users can download and upload classifications; no approval workflow exists.
- Saved classifications become active immediately and are used by industry and salesperson reporting.

## Data and security boundaries
- Shipment analytics use only the approved read-only source view and a read-only database transaction.
- The service refuses operational data access if source credentials or required fields are missing or if the restricted role has broader table privileges.
- User accounts, sessions, classification history and research data are isolated from NG-Dashboard and stored on the AI Insights private volume.
- Administrative user and research-import actions remain administrator-only; classification contributions do not.
- Salesperson attribution uses the ERP `salesperson` field; `job_owner` is displayed separately and is not substituted for it.
- Industry attribution for export uses shipper; import uses consignee. Exact normalized name matching is used; ambiguous conflicting mappings are not attributed.

## Verification
Run:
```bash
python -m compileall -q main.py app tests
python -c 'import main; print("FastAPI imports OK")'
python -m unittest discover -s tests -p 'test_*.py'
```
