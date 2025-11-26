import os
import requests
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
import time

# Load environment variables from .env file if it exists (for local dev)
# In Docker, environment variables are set by docker-compose, so this is optional
try:
    load_dotenv()
except:
    pass  # If .env doesn't exist, rely on environment variables from docker-compose

API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
CX = os.getenv("GOOGLE_CSE_CX")

CSE_URL = "https://www.googleapis.com/customsearch/v1"
from urllib.parse import urlparse 
BLOCKED_DOMAINS = [
    "reedsy.com",
    "newpages.com",
    "pw.org",
    "poets.org",
]

def is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return False
    # match domain or subdomains
    return any(host == d or host.endswith("." + d) for d in BLOCKED_DOMAINS)

DEFAULT_QUERIES = [
    "literary magazine submissions directory",
    "poetry press open submissions",
    "literary agents accepting submissions list",
    "small press submissions guidelines",
]



def call_google_search_save(queries, output_path="search_results_raw.ndjson", results_per_query=10):
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
            now = datetime.now(timezone.utc).isoformat()
            for item in items:
                result_url = item["link"]
                if not result_url:
                    continue
                if is_blocked(result_url):
                    continue  # skip reedsy / newpages / P&W etc.

                row = {
                "query": q,
                "rank": rank,
                "title": item.get("title"),
                "url": result_url,
                "snippet": item.get("snippet", ""),
                "source": "google_cse",
                "scraped_at": datetime.now(timezone.utc).isoformat(),
    }
                f_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                rank += 1

    print(f"Saved search results to {output_path}")
    


    



