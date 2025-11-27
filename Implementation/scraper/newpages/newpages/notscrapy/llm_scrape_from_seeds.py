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
- "price_numeric" must always be a NUMBER (0, 10, 99.99, etc.). Use 0 when uncertain.
- If the page is a directory or list, each entity in the array should be a separate object.
- Do NOT mention that the HTML is truncated or that you lack information; just leave
  unknown fields as null or empty arrays.

### SPECIAL CONTACT INFO RULES (VERY IMPORTANT)

Most websites (restaurants, stores, small businesses, etc.) include a section called
"Contact Us", "Contact", "Get in Touch", or similar. These sections almost ALWAYS
contain phone numbers and email addresses.

You MUST do the following:

1. Search explicitly for any section headers that contain:
   - "Contact Us"
   - "Contact"
   - "Contact Info"
   - "Get in Touch"
   - "Reach Us"
   - "Support"

2. When such sections exist, treat any phone numbers or emails inside that section
   as **the primary values** for the entity.

3. NEVER leave "phone" or "contact_email" null if a phone or email appears anywhere
   inside a "Contact" section OR anywhere else on the page.

4. If multiple phone numbers or emails exist:
   - choose the most general one from the "Contact" section
   - avoid using social media, reservation platforms, or marketing-specific emails.

5. Only set "phone": null and "contact_email": null if ABSOLUTELY no phone or email
   appear anywhere in the provided text.

Contact information is CRITICAL.
- If any phone-like pattern appears anywhere in the content, you MUST set the "phone"
  field to that value instead of leaving it null.
- If any email address appears anywhere in the content, you MUST set "contact_email"
  (or "email") to that value instead of leaving it null.
- Only leave these fields null if there is truly no phone number or email address
  anywhere in the provided text.

Special guidance when the user request is very specific:
- If the user request only cares about certain information (for example: prices,
  specs, or contact info), you should still output JSON OBJECTS, but you may
  omit unrelated keys or set them to null.
- Focus your effort on extracting the fields that answer the user request well.

Output:
- Output ONLY valid JSON (no comments, no markdown, no backticks, no explanations).
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
    request_user = input(
        "Describe what kind of information would you like to extract: "
    )
    llm_scrape_from_seeds(user_request=request_user)
