# Implementation/scraper/verticals/base.py

from __future__ import annotations
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class DetectionResult:
    matched: bool
    confidence: float
    reason: str
    matched_entities: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    allow: bool
    score_delta: float
    reason: str


class VerticalIntelligenceModule(ABC):
    """
    Vertical plug-in interface.

    Philosophy:
    - Deterministic rules first.
    - LLM fallback only when needed (you can wire it later).
    """

    # Friendly unique name for logs
    name: str = "base"

    # Higher number = higher priority when multiple verticals match
    priority: int = 0

    @abstractmethod
    def detect_vertical(self, user_request: str) -> DetectionResult:
        """Return whether this vertical matches the user request."""

    @abstractmethod
    def enhance_search_queries(self, user_request: str, base_queries: List[str]) -> List[str]:
        """Return enhanced queries (e.g., domain anchoring, exact-name quoting)."""

    @abstractmethod
    def validate_result(self, user_request: str, candidate: Dict[str, Any]) -> ValidationResult:
        """
        Validate a candidate search result.
        candidate can contain: url, title, snippet, displayLink, etc.
        """

    @abstractmethod
    def get_extraction_instructions(self, user_request: str) -> str:
        """Return extraction instructions tailored to this vertical."""

    def normalize_user_request(self, user_request: str) -> str:
        """Optional request normalization (override as needed)."""
        return user_request.strip()
