# AI Insights: vertical-led freight forwarding intelligence (non-accounting scope)

## Objective
Help NG and NCS department heads explain where the company operates, identify verticals and trade lanes worth growing, manage sales/agent relationships, and publish substantiated marketing capabilities.

## Source contract
NG-Dashboard is the system of record. Its public.shipments table has company, report_type, key, shipment_no, shipment_date, branch, customer, shipper, consignee, job_owner, carrier, origin/destination (and codes), weights, chargeable_wt, TEUs, volume, cargo_type, consol_type, nomination, status, stage, operational lock dates, and extra JSON. Its public.org_master has organization sales/network/country. Only the restricted ai_insights_source.current_shipments view is currently confirmed accessible to AI Insights. The source schema confirms a dedicated `Sales Person` value in shipments.extra and a separate `job_owner` column. The expanded view must expose `extra ->> 'Sales Person' AS salesperson` and retain `job_owner` separately, alongside shipper and consignee. No raw table grants should be assumed.

## Excluded
No accounting figures: no income, expense, GP, invoices, billing, rates, or finance columns in the UI, API, exports or narrative. Do not join profit_lines until explicitly reauthorized.

## Intelligence modules
1. Executive vertical mix: shipment counts, classified coverage, contribution shares, MoM/YoY and time-comparable dates.
2. Vertical deep dive: AE/AI/OE/OI, company, branch, lanes, shipper/consignee, TEUs, gross weight, month trend.
3. Salesperson and nomination: use shipments.job_owner as the salesperson/job-owner attribution field unless the source owner confirms a separate dedicated salesperson column. Report salesperson × industry, job/shipment counts, and shipper/consignee relationships. Self/agent nominations, introducing agent, customer and agent contribution, new/lost/reactivated customers require their own verified source fields.
4. Network: origin-destination by industry and LOB; carriers; lane concentration and growth.
5. Operations: cargo/consol type, status/stage, lock milestones, turnaround and exception rate where dates are reliable.
6. Market-ready credentials: only aggregated, evidence-backed, permission-reviewed claims, with period and volume basis.

## Access and reconciliation
Read-only curated views only. Scope by authorized NG/NCS and AE/AI/OE/OI on every query and export. No security/auth tables. Preserve active snapshot semantics (to_import IS NULL), current/historical coverage, and exact job key mapping. Show unmatched classification and missing source fields; do not infer sales ownership or introducing agents. Never duplicate a shipment through joins. Compare totals to NG-Dashboard before release.

## Current implementation
Industry mix, filters and comparison periods, selected industry department/lane/counterparty/branch drilldown and evidence-based operational narratives are implemented against existing restricted view. Salesperson-wise industry reporting is enabled only after the curated view exposes the ERP `Sales Person` value as salesperson and source reconciliation passes. Nomination, carrier, operational milestones and agent relationships remain blocked until their fields are separately verified.
