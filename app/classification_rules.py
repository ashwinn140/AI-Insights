"""Safe company-name normalization and classification precedence rules.

A normalized name is only a candidate key; never treat name similarity as
verified industry evidence. Explicit manual classifications take precedence
over research candidates, without an approval state.
"""
import re
import unicodedata
from dataclasses import dataclass

VALID_CONFIDENCE = frozenset({"verified", "probable", "provisional", "unknown"})
VALID_SOURCE = frozenset({"manual", "research", "inferred"})

def normalize_company_name(value):
    if not isinstance(value, str):
        return ""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return " ".join(value.split())

@dataclass(frozen=True)
class Classification:
    company_name: str
    industry: str | None
    confidence: str
    source: str

    def __post_init__(self):
        if self.confidence not in VALID_CONFIDENCE or self.source not in VALID_SOURCE:
            raise ValueError("Unsupported classification metadata")
        if self.source == "inferred" and self.confidence == "verified":
            raise ValueError("Inferred classifications cannot be verified")
        if not normalize_company_name(self.company_name):
            raise ValueError("Missing company name")

def select_classification(current, candidate):
    """Keep an explicit manual classification; otherwise accept the research candidate."""
    if current and current.source == "manual":
        return current
    return candidate
