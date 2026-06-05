import os
import logging
import requests
import json
from contextlib import nullcontext
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse
from typing import Optional, Any

# Import timing utilities (optional, will work without it)
try:
    from benchmark_utils import PerformanceTimer
except ImportError:
    PerformanceTimer = None

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger("ada.google_search")

API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
CX = os.getenv("GOOGLE_CSE_CX")

# Never log secret values; only whether they are configured.
logger.debug("CSE API_KEY set: %s, CX set: %s", bool(API_KEY), bool(CX))

if not API_KEY or not CX:
    raise RuntimeError("Missing GOOGLE_CSE_API_KEY or GOOGLE_CSE_CX (check .env / terminal env).")

CSE_URL = "https://www.googleapis.com/customsearch/v1"

from urllib.parse import urlparse 
BLOCKED_DOMAINS = [
    "facebook.com",
    "m.facebook.com",
    "reddit.com",
    "www.reddit.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "pinterest.com",
    "quora.com",
    "medium.com",
    "tiktok.com",
    "youtube.com",
    "linkedin.com",
]

def is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    # match domain or subdomains
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)


def normalize_url(url: str) -> str:
    """
    Normalize a URL so duplicates from different queries match:
    - lower-case scheme + host
    - drop query string & fragment
    - strip trailing slash
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return url

    # drop query & fragment
    cleaned = parsed._replace(query="", fragment="")

    # normalize scheme + host case
    scheme = (cleaned.scheme or "").lower()
    netloc = (cleaned.netloc or "").lower()

    normalized = urlunparse((
        scheme,
        netloc,
        cleaned.path or "",
        cleaned.params or "",
        "",   # no query
        ""    # no fragment
    )).rstrip("/")

    return normalized or url.rstrip("/")



def call_google_search_save(
    queries,
    output_path="output/search_results_raw.ndjson",
    results_per_query=10,
    timer: Optional[Any] = None,  # PerformanceTimer if available
):
    seen_urls = set()  # <- track normalized URLs across ALL queries
    
    # Ensure output directory exists
    from pathlib import Path
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    if timer:
        timer.add_metadata("num_queries", len(queries))
        timer.add_metadata("results_per_query", results_per_query)

    all_results = []

    # Single code path; the optional timer just wraps the API calls in a stage.
    stage = timer.stage("google_cse_api_calls") if timer else nullcontext()
    with stage:
        for q in queries:
            logger.info("CSE query: %s", q)
            params = {
                "key": API_KEY,
                "cx": CX,
                "q": q,
                "num": results_per_query,
            }
            r = requests.get(CSE_URL, params=params, timeout=20)
            if r.status_code != 200:
                logger.error("CSE error %s: %s", r.status_code, r.text[:500])
                r.raise_for_status()
            data = r.json()

            items = data.get("items", [])
            rank = 1  # rank per query

            for item in items:
                result_url = item.get("link")
                if not result_url:
                    continue

                if is_blocked(result_url):
                    continue

                norm = normalize_url(result_url)
                if norm in seen_urls:
                    # already saw this page from a previous query, skip duplicate
                    continue

                seen_urls.add(norm)

                now = datetime.now(timezone.utc).isoformat()
                row = {
                    "query": q,
                    "rank": rank,
                    "title": item.get("title"),
                    "url": result_url,
                    "normalized_url": norm,
                    "snippet": item.get("snippet", ""),
                    "source": "google_cse",
                    "scraped_at": now,
                }
                all_results.append(row)
                rank += 1

    # Write all results
    with open(output_path, "w", encoding="utf-8") as f_out:
        for row in all_results:
            f_out.write(json.dumps(row, ensure_ascii=False) + "\n")

    if timer:
        timer.add_metadata("total_results", len(all_results))
        timer.add_metadata("unique_urls", len(seen_urls))
    
    logger.info("Saved %d search results to %s", len(all_results), output_path)
