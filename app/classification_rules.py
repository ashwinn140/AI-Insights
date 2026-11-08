"""Safe company-name normalization and classification decision rules.

A normalized name is only a candidate key; never treat name similarity as
verified industry evidence. Explicit manual decisions always win.
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
    approved: bool = False

    def __post_init__(self):
        if self.confidence not in VALID_CONFIDENCE or self.source not in VALID_SOURCE:
            raise ValueError("Unsupported classification metadata")
        if self.confidence == "verified" and not self.approved:
            raise ValueError("Verified classifications require approval")
        if self.source == "inferred" and self.confidence == "verified":
            raise ValueError("Inferred classifications cannot be verified")
        if not normalize_company_name(self.company_name):
            raise ValueError("Missing company name")

def select_classification(current, candidate):
    """Never overwrite approved manual classification with automation."""
    if current and current.source == "manual" and current.approved:
        return current
    if not candidate.approved:
        return current
    return candidate
