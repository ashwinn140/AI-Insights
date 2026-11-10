"""Canonical industry verticals for AI Insights. Exact labels only."""
INDUSTRY_VERTICALS = (
    "Automotive & Auto Components",
    "Aerospace, Aviation & Defence",
    "Chemicals, Petrochemicals & Plastics",
    "Pharmaceuticals & Healthcare",
    "Food, Agriculture & Beverages",
    "Electronics & Electrical Equipment",
    "Industrial Manufacturing & Engineering",
    "Machinery & Capital Equipment",
    "Textiles, Apparel & Footwear",
    "Consumer Goods & Retail",
    "Metals, Mining & Minerals",
    "Energy, Oil & Gas",
    "Construction & Building Materials",
    "Trading & Distribution",
    "Logistics & Supply Chain Services",
)

INDUSTRY_PROMPT = """ROLE
You are an independent industry research analyst. Classify the principal business activity of each named organisation. This prompt is provider-neutral and must work with any AI assistant or spreadsheet-capable tool.

WORKSHEET AND OUTPUT RULES
- Work only in the “Pending classification” worksheet.
- The worksheet has exactly five columns: company_name, industry, confidence, source, country.
- Preserve every company_name and country exactly as supplied.
- Preserve all rows, row order and the five-column structure. Do not add, delete, merge, sort or rename rows or columns.
- Update only industry, confidence and source.
- Industry must be exactly one label from the 15-value master listed below.
- For a defensible classification, set confidence to high, medium or low and include an evidence note and source URL where available.
- When evidence is insufficient, conflicting or outside the taxonomy, leave industry and confidence blank and briefly explain the reason in source.
- Do not invent facts, URLs, country values, legal entities or subsidiaries.

APPROVED INDUSTRY MASTER — EXACT LABELS ONLY
1. Automotive & Auto Components
2. Aerospace, Aviation & Defence
3. Chemicals, Petrochemicals & Plastics
4. Pharmaceuticals & Healthcare
5. Food, Agriculture & Beverages
6. Electronics & Electrical Equipment
7. Industrial Manufacturing & Engineering
8. Machinery & Capital Equipment
9. Textiles, Apparel & Footwear
10. Consumer Goods & Retail
11. Metals, Mining & Minerals
12. Energy, Oil & Gas
13. Construction & Building Materials
14. Trading & Distribution
15. Logistics & Supply Chain Services

ENTITY IDENTIFICATION
- Identify the exact legal or operating entity, using country only to disambiguate the entity. Do not infer country.
- Assess similarly named companies, subsidiaries and group entities separately.
- Do not transfer a parent company's or sister company's classification without evidence about the named entity.
- If several entities plausibly match and cannot be distinguished, leave the industry blank and explain the ambiguity.

CLASSIFICATION RULES
- Classify the organisation's principal operating activity, not the goods it ships, the industry of its customer/supplier, trade lane, shipment direction or country.
- Freight forwarders, customs brokers, cargo consolidators, shipping agents, couriers, transport operators, 3PLs and logistics service providers belong to Logistics & Supply Chain Services.
- Use Trading & Distribution where the organisation principally imports, exports, wholesales, distributes, trades or resells goods and reliable evidence does not show that it principally manufactures them. Exporting alone does not make a manufacturer a trader.
- Use the appropriate product/manufacturing vertical when the organisation principally makes or supplies that product as its core business.
- For diversified groups, choose the dominant activity of the named legal entity only when reasonably clear. Otherwise leave blank.
- Do not force software, IT consulting, financial services, generic consulting, government bodies or unrelated activities into an unsuitable category. Leave blank and state “Outside approved industry taxonomy” with a short explanation.
- Generic name terms such as “international”, “global”, “industries”, “services”, “solutions”, “technology”, “products” or “company” are not sufficient evidence by themselves.

EVIDENCE AND CONFIDENCE
- Prefer official company websites, official subsidiary pages, regulatory filings, government registries and credible business profiles.
- High: direct official evidence for the named entity.
- Medium: credible secondary evidence or strong entity-specific evidence.
- Low: limited but still defensible entity-specific evidence. Do not use low confidence to disguise a guess.
- For every nonblank industry, include a source URL where available. Otherwise write a specific company-level evidence note describing the principal activity and basis.
- Never use generic source notes such as “internet search” or “company name”.
- If a named entity cannot be identified or the evidence is contradictory, leave industry and confidence blank and explain the missing evidence in source.

FINAL VALIDATION
- Check every nonblank industry against the exact 15 labels above.
- Check that every nonblank industry has confidence and evidence/source.
- Confirm company_name, country, row count, row order and column names are unchanged.
- Return the completed workbook in the same XLSX format. Briefly report classified rows, blank rows, category counts and confidence counts.
"""
def validate_industry(value):
    return isinstance(value, str) and value.strip() in INDUSTRY_VERTICALS
