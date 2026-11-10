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

INDUSTRY_PROMPT = """Classify each named legal/operating organisation into exactly ONE of these 15 industry verticals, using the exact label and spelling:
""" + "\n".join(f"{i+1}. {name}" for i,name in enumerate([
"Automotive & Auto Components","Aerospace, Aviation & Defence","Chemicals, Petrochemicals & Plastics",
"Pharmaceuticals & Healthcare","Food, Agriculture & Beverages","Electronics & Electrical Equipment",
"Industrial Manufacturing & Engineering","Machinery & Capital Equipment","Textiles, Apparel & Footwear",
"Consumer Goods & Retail","Metals, Mining & Minerals","Energy, Oil & Gas",
"Construction & Building Materials","Trading & Distribution","Logistics & Supply Chain Services"
])) + """

Evidence rules:
- Use the organisation's own business activity, products, official website, regulatory filings or credible business sources.
- Use shipper and consignee names, country, shipment appearances and salesperson/job-owner context only as corroborating clues; shipment direction, lane, customer relationship or salesperson alone does not prove an industry's business.
- Distinguish similarly named legal entities, subsidiaries and countries. Do not classify a freight forwarder as the shipper's industry.
- Select the principal operating business, not every industry it may touch. If evidence is genuinely insufficient or conflicting, leave industry blank and explain what is missing in source; do not guess.
- Confidence must be low, medium or high. Every nonblank classification must include a verifiable source URL or specific evidence note.
- Preserve organisation names exactly. Do not create new vertical labels, abbreviations, subcategories or alternative spellings.
""";
def validate_industry(value):
    return isinstance(value, str) and value.strip() in INDUSTRY_VERTICALS
