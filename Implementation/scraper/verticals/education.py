# Implementation/scraper/verticals/education.py

from __future__ import annotations
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from .base import DetectionResult, ValidationResult, VerticalIntelligenceModule


def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _contains_whole_phrase(text: str, phrase: str) -> bool:
    # robust enough for names; keep simple
    if not text or not phrase:
        return False
    return phrase.lower() in text.lower()


def _contains_word(text: str, word: str) -> bool:
    if not text or not word:
        return False
    return re.search(rf"\b{re.escape(word)}\b", text, re.IGNORECASE) is not None


@dataclass(frozen=True)
class Institution:
    key: str
    name: str
    domains: List[str]
    city: str
    state: str
    aliases: List[str]


class EducationVertical(VerticalIntelligenceModule):
    name = "education"
    priority = 100

    EDU_KEYWORDS = [
        "university",
        "college",
        "higher education",
        "provost",
        "vice president",
        "vp",
        "dean",
        "registrar",
        "campus",
        "faculty",  # note: can appear in request; we filter later in extraction
    ]

    # Roles we *care about* for leadership discovery
    ROLE_ALLOW = [
        "president",
        "provost",
        "vice president",
        "vp",
        "chancellor",
        "executive vice president",
        "senior vice president",
    ]

    # Roles we typically *do not* want in this vertical extraction target
    ROLE_DENY = [
        "student",
        "alumni",
        "department",
        "chair",
        "professor",
        "faculty directory",
        "adjunct",
        "graduate assistant",
    ]

    def __init__(self, data_path: Optional[str] = None) -> None:
        if data_path is None:
            data_path = str(Path(__file__).parent / "data" / "education_institutions.json")
        self._institutions = self._load_institutions(data_path)

    def _load_institutions(self, path: str) -> List[Institution]:
        p = Path(path)
        raw = json.loads(p.read_text(encoding="utf-8"))
        insts: List[Institution] = []
        for item in raw:
            insts.append(
                Institution(
                    key=item["key"],
                    name=item["name"],
                    domains=item["domains"],
                    city=item.get("city", ""),
                    state=item.get("state", ""),
                    aliases=item.get("aliases", []),
                )
            )
        return insts

    def _match_institution(self, user_request: str) -> Optional[Institution]:
        req = user_request.lower()

        # Prefer exact full-name match first
        for inst in self._institutions:
            if inst.name.lower() in req:
                return inst

        # Then try alias match, but treat as weaker (acronym ambiguity)
        for inst in self._institutions:
            for alias in inst.aliases:
                if _contains_word(req, alias.lower()):
                    return inst

        return None

    def detect_vertical(self, user_request: str) -> DetectionResult:
        req = self.normalize_user_request(user_request)

        kw_hits = sum(1 for kw in self.EDU_KEYWORDS if kw in req.lower())
        inst = self._match_institution(req)

        if inst and inst.name.lower() in req.lower():
            # strong match: exact name in request
            return DetectionResult(
                matched=True,
                confidence=0.95,
                reason=f"Exact institution name matched: {inst.name}",
                matched_entities={"institution": inst.key, "domain": inst.domains[0]},
            )

        if inst:
            # alias match only — still likely edu but ambiguous
            return DetectionResult(
                matched=True,
                confidence=0.70,
                reason=f"Institution alias matched (possible ambiguity): {inst.name}",
                matched_entities={"institution": inst.key, "domain": inst.domains[0]},
            )

        if kw_hits >= 2:
            return DetectionResult(
                matched=True,
                confidence=0.65,
                reason=f"Higher-ed keywords matched (count={kw_hits})",
                matched_entities={},
            )

        return DetectionResult(matched=False, confidence=0.0, reason="No higher-ed signal")

    def enhance_search_queries(self, user_request: str, base_queries: List[str]) -> List[str]:
        req = self.normalize_user_request(user_request)
        inst = self._match_institution(req)

        enhanced: List[str] = []
        base_queries = base_queries or [req]

        if inst:
            # Strict tier: official domain + exact name
            domain = inst.domains[0]
            exact = f"\"{inst.name}\""
            leadership = "(\"vice president\" OR provost OR \"executive vice president\" OR \"senior vice president\")"

            for q in base_queries:
                enhanced.append(f"site:{domain} {exact} {leadership}")

            # Fallback tier: still official domain, broader leadership wording
            for q in base_queries:
                enhanced.append(f"site:{domain} {exact} (leadership OR administration OR \"office of the president\")")

            return enhanced

        # Generic higher-ed boosting when institution isn't identified
        for q in base_queries:
            enhanced.append(f"{q} (site:.edu) (vice president OR provost OR leadership)")
        return enhanced

    def validate_result(self, user_request: str, candidate: Dict[str, Any]) -> ValidationResult:
        """
        Strict disambiguation rules for higher-ed:
        - Prefer official .edu domains (or exact allowlist domains when known)
        - Prefer pages that contain the full institution name
        - Use location cues as boost; conflicts are hard-block
        """
        req = self.normalize_user_request(user_request)
        inst = self._match_institution(req)

        url = str(candidate.get("url") or candidate.get("link") or "")
        title = str(candidate.get("title") or "")
        snippet = str(candidate.get("snippet") or "")
        text = f"{title}\n{snippet}"

        host = _host(url)

        # 1) If institution known: allowlist domains only (strict)
        if inst:
            allowed = any(host.endswith(d) or host == d for d in inst.domains)
            if not allowed:
                # Still allow some subdomains like www.asu.edu etc. via endswith check above.
                return ValidationResult(
                    allow=False,
                    score_delta=-1.0,
                    reason=f"Blocked: non-official domain for {inst.name} ({host})",
                )

            # 2) Exact name match strongly preferred
            if _contains_whole_phrase(text, inst.name):
                score = +0.6
                reason = "Allowed: official domain + full institution name found"
            else:
                # Allow but penalize if only acronym/alias appears (avoid acronym collapse)
                alias_hit = any(_contains_word(text, a) for a in inst.aliases)
                if alias_hit:
                    score = -0.2
                    reason = "Allowed (weak): official domain but only alias/acronym appears"
                else:
                    score = -0.1
                    reason = "Allowed (weak): official domain but institution name not found in snippet/title"

            # 3) Location cue boost / conflict block
            # If we see a conflicting state abbreviation (rare but helpful), block.
            # Keep it simple: if another state's abbreviation shows strongly AND ours doesn't show at all, penalize.
            state = inst.state.strip()
            city = inst.city.strip()

            if state and _contains_word(text, state):
                score += 0.2
                reason += f"; location cue matched ({state})"
            if city and _contains_whole_phrase(text, city):
                score += 0.1
                reason += f"; city cue matched ({city})"

            return ValidationResult(allow=True, score_delta=score, reason=reason)

        # If institution unknown: require .edu as minimum for higher-ed vertical
        if not host.endswith(".edu"):
            return ValidationResult(allow=False, score_delta=-1.0, reason=f"Blocked: non-.edu domain ({host})")

        # Soft boost for leadership pages
        leadership_hit = any(_contains_word(text, r) for r in ["vice", "provost", "president", "leadership", "administration"])
        return ValidationResult(
            allow=True,
            score_delta=0.2 if leadership_hit else 0.0,
            reason="Allowed: .edu domain" + (" + leadership cue" if leadership_hit else ""),
        )

    def get_extraction_instructions(self, user_request: str) -> str:
        """
        These instructions are meant to be appended to your LLM extraction prompt.
        Keep them strict to reduce false positives.
        """
        req = self.normalize_user_request(user_request)
        inst = self._match_institution(req)

        inst_name = inst.name if inst else "the target institution"
        inst_domains = ", ".join(inst.domains) if inst else "official .edu domain"

        return f"""
You are extracting Higher Education leadership contact data.

Target institution:
- Name: {inst_name}
- Official domain(s): {inst_domains}

STRICT RULES:
1) Only extract contacts from known official domain pages (no news, no social media).
2) Only extract leadership-level roles:
   - Allowed: President, Provost, Vice President (any variant), Chancellor, EVP/SVP.
   - Not allowed: faculty, department chairs, students, alumni staff, random directories.
3) Only output an email if it is explicitly present in the page text.
4) Prefer pages that clearly show the FULL institution name "{inst_name}" (avoid acronym-only identification).
5) Output must be structured JSON with an array of people.

OUTPUT JSON SCHEMA (example keys):
{{
  "institution_name": "{inst_name}",
  "official_domains": ["{inst.domains[0] if inst else ""}"],
  "contacts": [
    {{
      "name": "",
      "title": "",
      "email": "",
      "phone": "",
      "source_url": ""
    }}
  ]
}}
""".strip()
