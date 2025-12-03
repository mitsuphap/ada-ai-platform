"""
llm_scrape_from_seeds.py

Reads search_results_classified.ndjson (URLs picked by the user),
downloads each page (now in PARALLEL), and uses Gemini to extract structured
info.

Output: discovered_sites.ndjson (one JSON per URL/entity).
"""
import os
import re
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup
import requests
import google.generativeai as genai

# Import timing utilities (optional, will work without it)
try:
    from benchmark.benchmark_utils import PerformanceTimer
except ImportError:
    # Fallback for when benchmark module is not available
    try:
        from benchmark_utils import PerformanceTimer
    except ImportError:
        PerformanceTimer = None

SEEDS_PATH_DEFAULT = "output/search_results_classified.ndjson"
OUTPUT_PATH_DEFAULT = "output/discovered_sites.ndjson"

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

def is_valid_phone(phone_str: str) -> bool:
    """Validate that a phone number string is actually a phone number, not a date or other number."""
    digits = re.sub(r"\D", "", phone_str)
    # Must have 7-15 digits
    if not (7 <= len(digits) <= 15):
        return False
    # Reject if it looks like a year range (e.g., "2012-2014")
    if re.search(r'\d{4}[\s\-]+\d{4}', phone_str):
        return False
    # Reject if it's just 4 digits (likely a year)
    if len(digits) == 4 and re.match(r'^\d{4}$', phone_str.strip()):
        return False
    # Reject if it contains common date patterns
    if re.search(r'(19|20)\d{2}', phone_str) and len(digits) <= 8:
        return False
    # Must contain at least one space, dash, or parenthesis (typical phone formatting)
    # OR be a long international number
    if len(digits) >= 10:
        if not re.search(r'[\s\-\(\)]', phone_str):
            # Long number without formatting might be valid international
            return True
        return True
    # For shorter numbers, require some formatting
    return bool(re.search(r'[\s\-\(\)]', phone_str))

def extract_phone_candidates(text: str) -> List[str]:
    """Extract phone numbers from text, filtering out false positives like dates."""
    matches = {m.group(0).strip() for m in PHONE_REGEX.finditer(text)}
    cleaned = []
    for m in matches:
        if is_valid_phone(m):
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
   - For directory/list pages: Try to match emails to specific people by looking for patterns
     like "Name: [name], Email: [email]" or "[name] ([email])" or "[email] ([name])".

4. If ANY phone number appears anywhere:
   - Set "phone" to that value (or the most general one).
   - Do NOT leave "phone" null in that case.
   - IMPORTANT: Only extract actual phone numbers (7-15 digits with proper formatting).
   - REJECT date ranges like "2012-2014", years like "2024", or other non-phone numbers.

5. For directory/list pages with multiple people:
   - Extract each person as a separate entity.
   - If emails/phones are listed but not clearly matched to names, try to infer matches
     based on proximity in the text (emails near names).
   - If contact info is mentioned but not directly associated, include it in "extra" field.

6. Only set "contact_email": null and "phone": null if there is truly no email
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
    - Search the ENTIRE page content, including footers, sidebars, and contact sections.
    - Look for email patterns near the person's name or title.

  * For a directory/list page:
    - return an array of objects, each with at least "name" and "contact_email" where available.
    - Extract ALL people mentioned, even if some don't have emails.
    - For each person, try to find their associated email by:
      * Looking for patterns like "Name: [name], Email: [email]"
      * Finding emails near their name in the text
      * Checking if there's a general contact email that could be used
    - If emails aren't on this page, check if there are links to individual profile pages
      and mention this in the "extra" field.

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
    if not url:
        return None
    try:
        resp = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None


def fetch_all_html(seeds: List[Dict[str, Any]], max_workers: int = 10):
    """
    Fetch HTML for all seeds in PARALLEL using ThreadPoolExecutor.
    Returns a list of (seed, html) pairs.
    """
    results: List[tuple[Dict[str, Any], Optional[str]]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_seed = {
            executor.submit(fetch_html, seed.get("url")): seed
            for seed in seeds
        }
        for future in as_completed(future_to_seed):
            seed = future_to_seed[future]
            url = seed.get("url")
            try:
                html = future.result()
            except Exception as e:
                print(f"Error fetching {url}: {e}")
                html = None
            results.append((seed, html))
    return results


def prepare_html_for_llm(raw_html: str) -> str:
    soup = BeautifulSoup(raw_html, "html.parser")

    # Try to get main content first
    main = (
        soup.select_one("article")
        or soup.select_one("div.entry-content")
        or soup.select_one("main")
        or soup.body
    )

    main_text = main.get_text("\n", strip=True) if main else ""
    
    # Also extract footer and contact sections (where emails often are)
    footer = soup.select_one("footer")
    footer_text = footer.get_text("\n", strip=True) if footer else ""
    
    # Look for contact-related sections
    contact_sections = soup.select(
        "div.contact, section.contact, div#contact, section#contact, .contact-info, .contact-details"
    )
    contact_text = "\n".join([s.get_text("\n", strip=True) for s in contact_sections])
    
    # Combine all text
    text = main_text
    if footer_text:
        text += "\n\n--- FOOTER ---\n" + footer_text
    if contact_text:
        text += "\n\n--- CONTACT SECTIONS ---\n" + contact_text
    
    # If still no text, fall back to full page
    if not text.strip():
        text = soup.get_text("\n", strip=True)

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
        
        # Try to parse JSON, handle common issues
        try:
            data = json.loads(clean)
        except json.JSONDecodeError as e:
            # If JSON parsing fails, try to extract JSON from the response
            # Sometimes LLM wraps JSON in markdown or adds extra text
            # Try to find JSON object or array in the response
            json_match = re.search(r'(\[.*\]|\{.*\})', clean, re.DOTALL)
            if json_match:
                try:
                    data = json.loads(json_match.group(1))
                except:
                    raise ValueError(f"Failed to parse JSON from LLM response. Error: {e}. Raw response (first 500 chars): {clean[:500]}")
            else:
                raise ValueError(f"Failed to parse JSON from LLM response. Error: {e}. Raw response (first 500 chars): {clean[:500]}")

        # Normalize to list
        if isinstance(data, dict):
            entities = [data]
        elif isinstance(data, list):
            entities = data
        else:
            raise ValueError("LLM returned invalid JSON type")

        # Fallback: if phone/email missing but regex found candidates, fill them
        # But only if user request specifically asks for contact info
        user_wants_contact = any(
            keyword in user_request.lower()
            for keyword in ["email", "contact", "phone", "reach", "address", "phone number"]
        )
        
        best_phone = phone_candidates[0] if phone_candidates else None
        best_email = email_candidates[0] if email_candidates else None

        for ent in entities:
            phone_val = ent.get("phone")
            # Only use regex fallback if LLM didn't extract phone AND user wants contact info
            if best_phone and (phone_val in (None, "", "null")) and user_wants_contact:
                if is_valid_phone(best_phone):
                    ent["phone"] = best_phone

            email_val = ent.get("contact_email") or ent.get("email")
            # Only use regex fallback if LLM didn't extract email AND user wants contact info
            if best_email and (email_val in (None, "", "null")) and user_wants_contact:
                ent["contact_email"] = best_email

        return entities

    except Exception as e:
        print(f"[ERROR] LLM extract failed for {url}: {e}")
        return [{"error": str(e)}]


# --- MAIN PIPELINE --------------------------------------------

def llm_scrape_from_seeds(
    seeds_path: str = SEEDS_PATH_DEFAULT,
    output_path: str = OUTPUT_PATH_DEFAULT,
    delay_seconds: float = 0.0,  # set default to 0 now that we parallel-fetch
    user_request: str = "Extract a general profile of each entity.",
    custom_parser_instructions: Optional[str] = None,
    max_workers: int = 10,
    llm_workers: int = 5,  # NEW: separate workers for LLM calls
    timer: Optional[Any] = None,  # PerformanceTimer if available
) -> None:

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    seeds = load_ndjson(seeds_path)
    print(f"Loaded {len(seeds)} seeds from {seeds_path}")

    if timer:
        timer.add_metadata("num_seeds", len(seeds))
        timer.add_metadata("max_workers", max_workers)
        timer.add_metadata("llm_workers", llm_workers)
        timer.add_metadata("user_request", user_request)

    # 1) PARALLEL FETCH ALL HTML
    if timer:
        with timer.stage("fetch_html"):
            print(f"Fetching HTML for {len(seeds)} URLs in parallel (max_workers={max_workers})...")
            seed_html_pairs = fetch_all_html(seeds, max_workers=max_workers)
    else:
        print(f"Fetching HTML for {len(seeds)} URLs in parallel (max_workers={max_workers})...")
        seed_html_pairs = fetch_all_html(seeds, max_workers=max_workers)

    if timer:
        urls_fetched = len([h for _, h in seed_html_pairs if h is not None])
        timer.add_metadata("urls_fetched", urls_fetched)
        timer.add_metadata("urls_failed", len(seed_html_pairs) - urls_fetched)

    out_file = Path(output_path)
    total = len(seed_html_pairs)
    
    def process_one_url(item_html_pair):
        """Process one URL: extract with LLM"""
        item, html = item_html_pair
        url = item.get("url")
        label = item.get("label", "unknown")
        title = item.get("title", "")
        source_query = item.get("source_query") or item.get("query")
        
        if html is None:
            return [{
                "url": url,
                "label": label,
                "title": title,
                "source_query": source_query,
                "scraped_status": "http_error",
                "scraped_at": None,
                "llm_payload": None,
            }]
        
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
        records = []
        for ent in entities:
            records.append({
                "url": url,
                "label": label,
                "title": title,
                "source_query": source_query,
                "scraped_status": "ok",
                "scraped_at": now_str,
                "llm_payload": ent,
            })
        return records
    
    # 2) PARALLEL LLM PROCESSING (always use parallel, timer is optional)
    all_records = []
    
    def run_parallel_processing():
        print(f"Processing {total} URLs with LLM in parallel (llm_workers={llm_workers})...")
        with ThreadPoolExecutor(max_workers=llm_workers) as executor:
            future_to_pair = {
                executor.submit(process_one_url, pair): idx 
                for idx, pair in enumerate(seed_html_pairs, start=1)
            }
            for future in as_completed(future_to_pair):
                idx = future_to_pair[future]
                try:
                    records = future.result()
                    all_records.extend(records)
                    print(f"[{idx}/{total}] Completed processing")
                except Exception as e:
                    print(f"Error processing URL {idx}: {e}")
                    all_records.append({
                        "scraped_status": "error",
                        "error": str(e),
                    })
    
    if timer:
        with timer.stage("llm_extraction"):
            run_parallel_processing()
    else:
        # Still use parallel processing even without timer
        run_parallel_processing()
    
    # Write all records if using timer
    if timer:
        with out_file.open("w", encoding="utf-8") as f_out:
            for record in all_records:
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
        timer.add_metadata("records_saved", len(all_records))


if __name__ == "__main__":
    import time
    request_user = input(
        "Describe what kind of information would you like to extract: "
    )
    
    # Use timer if available
    if PerformanceTimer:
        timer = PerformanceTimer("scraping")
        timer.start()
        llm_scrape_from_seeds(user_request=request_user, timer=timer)
        timer.end()
        timer.print_summary()
    else:
        start = time.time()
        llm_scrape_from_seeds(user_request=request_user)
        end = time.time()
        print(f"Completed in {end - start:.2f} seconds.")
