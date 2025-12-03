import os
import requests
import json
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse

API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
CX = os.getenv("GOOGLE_CSE_CX")

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
    output_path="search_results_raw.ndjson",
    results_per_query=10,
):
    seen_urls = set()  # <- track normalized URLs across ALL queries

    with open(output_path, "w", encoding="utf-8") as f_out:
        for q in queries:
            print(f"[CSE] Query: {q}")
            params = {
                "key": API_KEY,
                "cx": CX,
                "q": q,
                "num": results_per_query,
            }
            r = requests.get(CSE_URL, params=params, timeout=20)
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
                f_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                rank += 1

    print(f"Saved search results to {output_path}")
