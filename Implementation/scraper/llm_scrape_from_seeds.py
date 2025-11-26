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

import requests
import google.generativeai as genai

SEEDS_PATH_DEFAULT = "chosen_seeds.ndjson"
OUTPUT_PATH_DEFAULT = "discovered_sites.ndjson"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")



genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "models/gemini-2.5-flash"

MAX_HTML_CHARS = 30000
DEFAULT_HEADERS = {
    "User-Agent": "IntelliBaseCrawler/1.0 (+https://example.com)",
    "Accept-Language": "en-US,en;q=0.8",
}


PARSER_INSTRUCTIONS = """
You are a data extractor for a general-purpose information platform.

Task:
From the content of a web page about ANY subject (for example: a company, person,
product, service, event, directory, article, etc.), extract structured data that best
answers what the USER CARES ABOUT.

User intent:
- You will be given a short natural-language description of what the user wants
  (the "user request"), such as:
  - "I only care about contact information and location"
  - "Extract all pricing and subscription plans"
  - "Summarize key specs for each product on the page"
- Use this user request to decide which fields to prioritize and how detailed to be.
- Fields that are strongly related to the user request should be as complete and
  accurate as possible. Less relevant fields can be null or omitted.

How to decide the output shape:
- If the page is mostly about ONE main entity, return a single JSON OBJECT.
- If the page clearly lists MANY distinct entities (like a directory, product list,
  team members, etc.), return a JSON ARRAY of JSON OBJECTS, one object per entity.
- Do NOT wrap the result in an outer object (no {"entities": [...]}) and do NOT add
  any extra text before or after. Only output raw JSON.

Entity schema:
- Your JSON objects may contain any keys that make sense for the page and the
  user request, but when possible use these common keys:

  - "name" (string or null)             # main name of the entity
  - "category" (string or null)         # type of entity (e.g. "company", "person", "product")
  - "description" (string or null)      # short free-text summary
  - "website" (string or null)          # main site URL if any
  - "contact_email" (string or null)    # best contact email
  - "phone" (string or null)
  - "address" (string or null)
  - "city" (string or null)
  - "country" (string or null)
  - "social_links" (array of strings)   # e.g. Twitter, Instagram, LinkedIn URLs
  - "tags" (array of strings)           # keywords, topics, technologies, etc.
  - "price" (string or null)            # human-readable price or plan text
  - "price_numeric" (number)            # numeric price if clearly stated; 0 if unknown
  - "opening_hours" (string or null)    # business hours, schedule, availability
  - "extra" (string or null)            # any important details that don't fit above

Rules:
- If a value is missing or unclear, use null (or [] for arrays).
- "price_numeric" must always be a NUMBER (0, 10, 99.99, etc.). Use 0 when uncertain.
- If the page is a directory or list, each entity in the array should be a separate object.
- Do NOT mention that the HTML is truncated or that you lack information; just leave
  unknown fields as null or empty arrays.

Special guidance for contact information:
- For "contact_email", look for email addresses associated with contacting, support,
  sales, or inquiries. If multiple emails exist, pick the most general or the one
  most relevant to the user request (e.g. support vs. sales).
- For "phone" and "address", prefer the most prominent or general ones.

Special guidance when the user request is very specific:
- If the user request only cares about certain information (for example: prices,
  specs, or contact info), you should still output JSON OBJECTS, but you may
  omit unrelated keys or set them to null.
- Focus your effort on extracting the fields that answer the user request well.

Output:
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

def call_gemini_extract(
    html: str,
    url: str,
    label: str,
    title: str,
    user_request: str,
) -> List[Dict[str, Any]]:
    
    model = genai.GenerativeModel(
        MODEL_NAME,
        generation_config={
            "response_mime_type": "application/json"
        },
    )
    
    html_snippet = prepare_html_for_llm(html)

    prompt = f"""{PARSER_INSTRUCTIONS}

    User request:
    - {user_request}

    Extra context:
    - URL: {url}
    - Label: {label}
    - Page title: {title}

    Remember:
    - Output ONLY raw JSON.
    - Either a single JSON object OR a list of JSON objects.

    HTML content:
    {html_snippet}
    """

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()
        clean = strip_code_fence(raw)
        data = json.loads(clean)

        # Accept dict or list directly
        if isinstance(data, dict):
            return [data]
        elif isinstance(data, list):
            return data
        else:
            raise ValueError("LLM returned invalid JSON type")

    except Exception as e:
        print(f"[ERROR] LLM extract failed for {url}: {e}")
        return [{"error": str(e)}]


def llm_scrape_from_seeds(
    seeds_path: str = SEEDS_PATH_DEFAULT,
    output_path: str = OUTPUT_PATH_DEFAULT,
    delay_seconds: float = 1.0,
    user_request: str = "Extract a general profile of each entity.",
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
            
            if html is None:
                record = {
                    "url": url,
                    "label": label,
                    "title": title,
                    "source_query": item.get("source_query"),
                    "scraped_status": "http_error",
                    "scraped_at": None,
                    "llm_payload": None,
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            print(f"[LLM] Extracting structured data for {url} ...")
            entities = call_gemini_extract(
                html,
                url=url,
                label=label,
                title=title,
                user_request=user_request,
            )

            now_str = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            for ent in entities:
                record = {
                    "url": url,
                    "label": label,
                    "title": title,
                    "source_query": item.get("source_query"),
                    "scraped_status": "ok",
                    "scraped_at": now_str,
                    "llm_payload": ent,
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

            if delay_seconds > 0:
                time.sleep(delay_seconds)

if __name__ == "__main__":
    request_user = input("Describe what kind of information would you like to extract: ")
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        default="Extract a general profile of each entity.",
        help="NATURAL LANGUAGE DESCRIPTION of what the user wants to extract.", 

    )
    args = parser.parse_args()
    llm_scrape_from_seeds(user_request=request_user)
