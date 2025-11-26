import os
import json
import google.generativeai as genai

API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
CX = os.getenv("GOOGLE_CSE_CX")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-2.5-flash")



def generate_queries_with_gemini(user_text: str, n: int = 5) -> list[str]:
    """
    Take one natural-language sentence and return a list of search queries.

    Example input:
        "I want gyms near Vancouver that are cheap"
    Possible output:
        [
          "cheap gym memberships Vancouver BC -reddit -blog -list -directory",
          "24 hour fitness gym Vancouver membership price -top -best -review",
          ...
        ]
    """

    prompt = f"""
    You are an expert Google Search query generator for a general-purpose data
    discovery system.

    Your job:
    - Take a single user request (what they are looking for).
    - Expand it into EXACTLY {n} high-quality Google Search queries.

    The goal:
    - Find pages that are most likely to be useful for the user's request.
    - Prefer official / primary sources when possible (e.g. the business/site itself,
    the product page, the service page), unless the user explicitly wants reviews
    or directories.

    User request:
    "{user_text}"

    Rules for generating queries:
    1. Each query must be a short phrase suitable for Google Search.
    2. Always include any hints in the user request, such as:
        - location (city, country, region)
        - type of place (gym, restaurant, service, store, etc.)
        - topic (e.g. geology jobs, data science bootcamps, student housing)
    3. Prefer queries that lead to specific, high-value pages, for example:
        - official websites
        - product/service detail pages
        - contact pages
        - pricing/subscription pages
    4. Unless the user explicitly wants lists/directories, try to avoid generic:
        - “top X”, “best X”
        - “list”, “directory”, “review sites”
    5. You MAY use negative filters like:
        - -reddit -blog -medium -substack -list -directory -top -best
        BUT only if they make sense.
    6. The {n} queries must be distinct, not tiny variations of each other.
    7. Make the queries concrete and actionable, not just "gym Vancouver".
        Prefer more specific phrasing that matches how people search.

    Output format (VERY IMPORTANT):
    - Return a JSON array of EXACTLY {n} strings.
    - Example: ["query 1", "query 2", "query 3"]
    - No extra keys, no explanations, no comments, no markdown.
    """

    try:
        resp = model.generate_content(prompt)
        raw = (resp.text or "").strip()

        # Since we forced application/json, resp.text should already be JSON
        data = json.loads(raw)

        # Keep only strings
        queries = [q for q in data if isinstance(q, str)]

    except Exception as e:
        print(f"[ERROR] Failed to parse queries from Gemini: {e}")
        queries = []

    # Very defensive fallback: if nothing parsed, just reuse the user text
    if not queries:
        queries = [user_text.strip()]

    # Deduplicate and strip
    cleaned: list[str] = []
    seen = set()
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            cleaned.append(q)

    return cleaned


if __name__ == "__main__":
    # quick manual test
    example = "I want more poetry presses in Canada"
    qs = generate_queries_with_gemini(example, n=5)
    print("User input:", example)
    print("Generated queries:")
    for q in qs:
        print(" -", q)