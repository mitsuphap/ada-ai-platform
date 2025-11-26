"""
llm_scrape_from_seeds.py

Reads chosen_seeds.ndjson (URLs picked by the user),
downloads each page, and uses Gemini to extract structured
press/magazine/agent info.

Output: discovered_sites.ndjson (one JSON per URL).
"""
import os
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from dotenv import load_dotenv

import requests
import google.generativeai as genai

# Load environment variables from .env file if it exists (for local dev)
# In Docker, environment variables are set by docker-compose, so this is optional
try:
    load_dotenv()
except:
    pass  # If .env doesn't exist, rely on environment variables from docker-compose

SEEDS_PATH_DEFAULT = "chosen_seeds.ndjson"
OUTPUT_PATH_DEFAULT = "discovered_sites.ndjson"
API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
CX = os.getenv("GOOGLE_CSE_CX")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Check docker-compose.yml and .env file.")

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "models/gemini-2.5-flash"

MAX_HTML_CHARS = 30000
DEFAULT_HEADERS = {
    "User-Agent": "IntelliBaseCrawler/1.0 (+https://example.com)",
    "Accept-Language": "en-US,en;q=0.8",
}


PARSER_INSTRUCTIONS = """
You are a data extractor for a publishing intelligence platform.

Task:
From the content of a web page about a literary press, magazine, or literary agent,
extract structured data describing either:
- a single publisher / magazine / agent, or
- multiple entities if the page is clearly a directory or list (many agents/presses).

Output format:
- If the page is about ONE main entity, return a single JSON OBJECT.
- If the page clearly lists MANY distinct agents/presses/magazines (like a directory),
  return a JSON ARRAY of JSON OBJECTS, one object per entity.
- Do NOT wrap the result in any extra keys (no {"entities": [...]}) and do NOT add
  any extra text before or after. Only output raw JSON.

Each entity object must have ALL of these keys:

- name (string or null)
- website (string or null)             # main site URL, if you can infer it
- contact_email (string or null)       # best submission / query / general contact email
- genres (array of strings)            # e.g. ["poetry", "fiction"]
- reading_period (string or null)      # e.g. "Jan 1 – Mar 31", or "year-round"
- reading_fee (number)                 # numeric value; use 0 if free or unknown
- submission_methods (array of strings) # e.g. ["Submittable", "email", "online form"]
- city (string or null)
- country (string or null)
- response_time (string or null)       # e.g. "3–6 months"
- notes (string or null)               # extra useful details or warnings

Special guidance for contact_email:
- Look for email addresses related to submissions, queries, or general contact.
- If multiple emails exist, choose the one most relevant to submissions/queries.
- If you cannot tell which email is best, choose the most prominent or general one.
- If no email is present, set contact_email to null.

Special guidance for literary agents (when the label suggests an agent/agency page):
- Focus on what kinds of projects they represent (genres, age categories).
- Note how to query them (email, QueryManager, agency form, etc.).
- Note whether they are open or closed to queries.
- Note any stated response policy (e.g. "no response means no", "respond within 8 weeks").

Special guidance for presses / magazines:
- Focus on genres they publish and submission guidelines.
- Note open/close periods, reading windows, themes, contests, and fees.

Rules:
- If a value is missing or unclear, use null (or [] for arrays).
- "reading_fee" must always be a NUMBER (0, 5, 10, etc.). Use 0 when uncertain.
- Do NOT mention in the notes that the HTML is truncated or that you lack information;
  just leave unknown fields as null or empty lists.
- Output ONLY valid JSON (no comments, no markdown, no backticks, no explanations).
"""

def load_ndjson(path: str) -> List[Dict[str, Any]]:
    rows:List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows

def fetch_html(url: str, timeout: int = 15) -> Optional[str]:
    """Fetch HTML content from a URL."""
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None
def truncate_html(html: str, max_chars: int = MAX_HTML_CHARS) -> str:
    if len(html) <= max_chars:
        return html
    return html[:max_chars]

def prepare_html_for_llm(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")

    # Try some common containers first; fall back to body text
    main = (
        soup.select_one("article")
        or soup.select_one("div.entry-content")
        or soup.select_one("main")
        or soup.body
    )

    text = main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True)
    # Still keep a max length safety
    return text[:MAX_HTML_CHARS]

def strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1 :]
        if t.strip().endswith("```"):
            t = t[: t.rfind("```")]
    return t.strip()

def call_gemini_extract(html: str, url: str, label: str, title: str, custom_instructions: Optional[str] = None) -> List[Dict[str, Any]]:
    # You can keep or remove JSON mode; this just increases chance of clean JSON
    model = genai.GenerativeModel(
        MODEL_NAME,
        generation_config={
            "response_mime_type": "application/json",
        },
    )

    html_snippet = prepare_html_for_llm(html)  # or html[:MAX_HTML_CHARS]

    # Use custom instructions if provided, otherwise use default
    parser_instructions = custom_instructions if custom_instructions else PARSER_INSTRUCTIONS

    prompt = f"""{parser_instructions}

    Extra context:
    - URL: {url}
    - Label (from search classification): {label}
    - Page title: {title}

    REMEMBER:
    - If this page is a directory with MANY presses / agents / magazines,
      you may return EITHER:
        1) {{ "entities": [ entity1, entity2, ... ] }}
      OR
        2) [ entity1, entity2, ... ]
    - If there is just ONE main entity, return a single JSON OBJECT.

    Here is the page content (possibly truncated):

    <html>
    {html_snippet}
    </html>
    """

    entities: List[Dict[str, Any]] = []
    try:
        resp = model.generate_content(prompt)
        raw_text = (resp.text or "").strip()

        # DEBUG (keep if useful)
        print("\n=== RAW LLM OUTPUT (truncated) ===")
        print(raw_text[:500])
        print("=== END RAW OUTPUT ===\n")

        clean_text = strip_code_fence(raw_text)

        data = json.loads(clean_text)

        # Normalize:
        # 1) {"entities": [...]}
        if isinstance(data, dict) and "entities" in data and isinstance(data["entities"], list):
            entities = [d for d in data["entities"] if isinstance(d, dict)]

        # 2) plain dict -> single entity
        elif isinstance(data, dict):
            entities = [data]

        # 3) list of dicts
        elif isinstance(data, list):
            entities = [d for d in data if isinstance(d, dict)]

        else:
            raise ValueError("Gemini response is neither dict nor list of dicts")

        # If entities[] came back empty, treat as “nothing extracted”
        if not entities:
            raise ValueError("No entities extracted from page")

    except Exception as e:
        print(f"[LLM] Parse error for {url}: {e}")
        # Fallback: one empty-ish entity
        entities = [
            {
                "name": None,
                "website": None,
                "genres": [],
                "reading_period": None,
                "reading_fee": 0,
                "submission_methods": [],
                "city": None,
                "country": None,
                "contact_email ": None,
                "response_time": None,
                "notes": f"llm_error: {e}",
            }
        ]

    # 🔧 Normalize each entity safely
    required_keys = [
        "name",
        "website",
        "genres",
        "reading_period",
        "reading_fee",
        "submission_methods",
        "city",
        "country",
        "contact_email ",
        "response_time",
        "notes",
    ]

    for ent in entities:
        # Ensure all keys exist
        for key in required_keys:
            if key not in ent:
                ent[key] = [] if key in ("genres", "submission_methods") else None

        # genres as list
        if not isinstance(ent.get("genres"), list):
            ent["genres"] = [str(ent["genres"])] if ent["genres"] else []

        # submission_methods as list
        if not isinstance(ent.get("submission_methods"), list):
            ent["submission_methods"] = (
                [str(ent["submission_methods"])] if ent["submission_methods"] else []
            )

        # reading_fee numeric
        try:
            ent["reading_fee"] = float(ent.get("reading_fee", 0) or 0)
        except (TypeError, ValueError):
            ent["reading_fee"] = 0.0

    return entities

def llm_scrape_from_seeds(
    seeds_path: str = SEEDS_PATH_DEFAULT,
    output_path: str = OUTPUT_PATH_DEFAULT,
    delay_seconds: float = 1.0,
    custom_parser_instructions: Optional[str] = None
) -> None:
    seeds = load_ndjson(seeds_path)
    print(f"Loaded {len(seeds)} seeds from {seeds_path}")

    out_file = Path(output_path)
    with out_file.open("w", encoding="utf-8") as f_out:
        for idx, item in enumerate(seeds):
            url = item.get("url")
            label = item.get("label", "unknown")
            title = item.get("title", "")

            print(f"\n[{idx}/{len(seeds)}] Fetching {url} (label={label})")
            html = fetch_html(url)
            if  html is None:
                record = {
                    "url": url,
                    "label": label,
                    "title": title,
                    "source_query":item.get("source_query"),
                    "scraped_status": "http_error",
                    "scraped_at": None,
                    "llm_payload": None,
                }

                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            print(f"[LLM] Extracting structured data for {url} ...")
            extracted_entities = call_gemini_extract(html, url=url, label=label, title=title, custom_instructions=custom_parser_instructions)

            for ent in extracted_entities:
                record = {
                "url": url,                         # directory or single page URL
                "label": label,
                "title": title,
                "source_query": item.get("source_query"),
                "scraped_status": "ok",
                "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "llm_payload": ent,
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            if delay_seconds > 0:
                 time.sleep(delay_seconds)

if __name__ == "__main__":
    llm_scrape_from_seeds()
