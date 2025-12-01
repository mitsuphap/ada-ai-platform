"""
llm_scrape_from_seeds.py

Reads chosen_seeds.ndjson (URLs picked by the user),
downloads each page, and uses Gemini to extract structured
info.

Output: discovered_sites.ndjson (one JSON per URL/entity).
"""
import os
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from bs4 import BeautifulSoup
import requests
import google.generativeai as genai

SEEDS_PATH_DEFAULT = "search_results_classified.ndjson"
OUTPUT_PATH_DEFAULT = "discovered_sites.ndjson"

# --- API KEYS -------------------------------------------------
# Use a dedicated GEMINI_API_KEY here (NOT the CSE key)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not set in the environment")

genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "models/gemini-2.5-flash"

MAX_HTML_CHARS = 30000
DEFAULT_HEADERS = {
    "User-Agent": "IntelliBaseCrawler/1.0 (+https://example.com)",
    "Accept-Language": "en-US,en;q=0.8",
}

# --- REGEX HELPERS (phone + email) ----------------------------

PHONE_REGEX = re.compile(
    r"""
    (?:
        \+?\d{1,3}[\s\-\.\)]*    # optional country code, like +1
    )?
    (?:
        \(?\d{3}\)?              # area code: (604) or 604
        [\s\-\.\)]*
    )?
    \d{3}                        # first 3 digits
    [\s\-\.\)]*
    \d{4}                        # last 4 digits
    """,
    re.VERBOSE,
)

EMAIL_REGEX = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)

def extract_phone_candidates(text: str) -> List[str]:
    matches = {m.group(0).strip() for m in PHONE_REGEX.finditer(text)}
    # keep only reasonable lengths (strip non-digits to check)
    cleaned = []
    for m in matches:
        digits = re.sub(r"\D", "", m)
        if 7 <= len(digits) <= 15:
            cleaned.append(m)
    return cleaned

def extract_email_candidates(text: str) -> List[str]:
    return list({m.group(0).strip() for m in EMAIL_REGEX.finditer(text)})


# --- LLM INSTRUCTIONS -----------------------------------------

PARSER_INSTRUCTIONS =  """
You are a data extractor for a general-purpose information platform.

You will receive:
1) A USER REQUEST: what the user cares about (may be LONG and contain fluff).
2) The CONTENT of a web page (about a company, person, product, service, event,
   directory, article, etc.).

Your job:
- First, understand the core information need from the USER REQUEST.
- Then, extract structured JSON data from the page that best answers that need.

--------------------------------------------------
USER REQUEST (VERY IMPORTANT)
--------------------------------------------------

The user request may look like:

- "I am a Digital marketing manager working for higher education trying to improve a
   university ranking in US news and world report. Basically find me email address
   of VPs at Douglas college."

- "I'm a geology student and I just need lists of mines with location and commodity."

- "Only care about subscription prices and their monthly cost."

Your behavior:

1. Ignore persona / backstory / emotion ("I am a marketing manager", "I'm stressed", etc.).
2. Focus ONLY on the concrete data they want:
   - contact info (emails, phones),
   - locations,
   - prices,
   - product specs,
   - list of people/agents, etc.
3. If the user explicitly mentions email / contact info / phone numbers /
   "how to reach them", you must prioritize those fields.

--------------------------------------------------
OUTPUT SHAPE
--------------------------------------------------

- If the page is mostly about ONE main entity, return a SINGLE JSON OBJECT.
- If the page clearly lists MANY distinct entities (e.g. a directory of agents),
  return a JSON ARRAY of JSON OBJECTS, one per entity.
- Do NOT wrap inside {"entities": [...]}. Output ONLY raw JSON.

--------------------------------------------------
ENTITY SCHEMA
--------------------------------------------------

Use any keys that make sense for the user request and page, but when possible
prefer these common keys:

- "name" (string or null)
- "category" (string or null)
- "description" (string or null)
- "website" (string or null)
- "contact_email" (string or null)
- "phone" (string or null)
- "address" (string or null)
- "city" (string or null)
- "country" (string or null)
- "social_links" (array of strings)
- "tags" (array of strings)
- "price" (string or null)
- "price_numeric" (number)
- "opening_hours" (string or null)
- "extra" (string or null)

Rules:
- If a value is missing or unclear, use null (or [] for arrays).
- "price_numeric" must always be a NUMBER. Use 0 when uncertain.
- In lists/directories, each entity is a separate object.

--------------------------------------------------
SPECIAL CONTACT INFO RULES (CRITICAL)
--------------------------------------------------

When the USER REQUEST mentions things like:
- "email address",
- "contact information",
- "how to reach",
- "phone number",
you MUST try very hard to find contact details.

1. Search explicitly for section headers like:
   - "Contact Us", "Contact", "Contact Info", "Get in Touch",
     "Reach Us", "Support", "Submissions", "Queries".

2. Also look near phrases like:
   - "Email:", "E-mail:", "Contact:", "Submissions:", "For queries:", "For inquiries:".

3. If ANY email address appears anywhere in the page:
   - Set "contact_email" to that value (or the most general one, e.g. info@, submissions@).
   - Do NOT leave "contact_email" null in that case.

4. If ANY phone number appears anywhere:
   - Set "phone" to that value (or the most general one).
   - Do NOT leave "phone" null in that case.

5. Only set "contact_email": null and "phone": null if there is truly no email
   or phone number in the provided text.

Even when the user request is only about emails, you may still fill other fields
(name, website, tags) if they are easy to identify.

--------------------------------------------------
FOCUSING ON THE USER REQUEST
--------------------------------------------------

- If the user only cares about emails (e.g. "find me email addresses of VPs"),
  you can keep other fields simple or null, but:

  * For a single-entity page:
    - return one JSON object with at least "name" and "contact_email".

  * For a directory/list page:
    - return an array of objects, each with at least "name" and "contact_email"
      where available.

- If the user cares about prices only, focus on price and price_numeric.
- If the user cares about location only, focus on address/city/country.

Do NOT hallucinate data that is not present.
--------------------------------------------------
REMEMBER:
- Output ONLY valid JSON.
- No comments, no markdown, no backticks, no explanations.
"""


# --- UTILITIES ------------------------------------------------

def load_ndjson(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
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


def prepare_html_for_llm(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")

    main = (
        soup.select_one("article")
        or soup.select_one("div.entry-content")
        or soup.select_one("main")
        or soup.body
    )

    text = main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True)

    # If it's huge, keep both the beginning and the end (footer)
    if len(text) > MAX_HTML_CHARS:
        front = text[:20000]
        back = text[-10000:]   # last 10k chars – where footer often lives
        text = front + "\n...\n" + back

    return text


def strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1 :]
        if t.strip().endswith("```"):
            t = t[: t.rfind("```")]
    return t.strip()


# --- LLM CALL -------------------------------------------------

def call_gemini_extract(
    html: str,
    url: str,
    label: str,
    title: str,
    user_request: str,
    custom_parser_instructions: Optional[str] = None,
) -> List[Dict[str, Any]]:

    model = genai.GenerativeModel(
        MODEL_NAME,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": 0.0,
        },
    )

    # Text for both Gemini and regex helpers
    html_snippet = prepare_html_for_llm(html)

    # Regex-based backups
    phone_candidates = extract_phone_candidates(html_snippet)
    email_candidates = extract_email_candidates(html_snippet)

    # Use custom instructions if provided, otherwise use default
    parser_instructions = custom_parser_instructions if custom_parser_instructions else PARSER_INSTRUCTIONS

    prompt = f"""{parser_instructions}

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

        # Normalize to list
        if isinstance(data, dict):
            entities = [data]
        elif isinstance(data, list):
            entities = data
        else:
            raise ValueError("LLM returned invalid JSON type")

        # Fallback: if phone/email missing but regex found candidates, fill them
        best_phone = phone_candidates[0] if phone_candidates else None
        best_email = email_candidates[0] if email_candidates else None

        for ent in entities:
            phone_val = ent.get("phone")
            if best_phone and (phone_val in (None, "", "null")):
                ent["phone"] = best_phone

            email_val = ent.get("contact_email") or ent.get("email")
            if best_email and (email_val in (None, "", "null")):
                ent["contact_email"] = best_email

        return entities

    except Exception as e:
        print(f"[ERROR] LLM extract failed for {url}: {e}")
        return [{"error": str(e)}]


# --- MAIN PIPELINE --------------------------------------------

def llm_scrape_from_seeds(
    seeds_path: str = SEEDS_PATH_DEFAULT,
    output_path: str = OUTPUT_PATH_DEFAULT,
    delay_seconds: float = 1.0,
    user_request: str = "Extract a general profile of each entity.",
    custom_parser_instructions: Optional[str] = None,
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
                custom_parser_instructions=custom_parser_instructions,
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
    request_user = input(
        "Describe what kind of information would you like to extract: "
    )
    llm_scrape_from_seeds(user_request=request_user)
