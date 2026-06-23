from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Protocol


class ResearchProvider(Protocol):
    def find_sector_context(self, company_summary: Dict[str, str], bp_terms: List[str]) -> Dict[str, object]:
        """Return external sector context. First version intentionally returns no external evidence."""


@dataclass(frozen=True)
class NullResearchProvider:
    reason: str = "external_search_not_configured"

    def find_sector_context(self, company_summary: Dict[str, str], bp_terms: List[str]) -> Dict[str, object]:
        return {
            "mode": "llm_only",
            "reason": self.reason,
            "company_summary": company_summary,
            "terms": bp_terms,
            "sources": [],
        }
