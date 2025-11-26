import os
import json
import google.generativeai as genai

API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
CX = os.getenv("GOOGLE_CSE_CX")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-2.5-flash")



def _extract_json_array(text: str) -> list[str]:
    """
    Try to extract a JSON array from Gemini's response text.
    If parsing fails, return an empty list.
    """
    try:
        # Sometimes the model might wrap JSON with extra text.
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        snippet = text[start : end + 1]
        data = json.loads(snippet)
        if isinstance(data, list):
            # Keep only strings
            return [q for q in data if isinstance(q, str)]
    except Exception:
        pass
    return []


def generate_queries_with_gemini(user_text: str, n: int = 5) -> list[str]:
    """
    Take one natural-language sentence and return a list of search queries.
    Example input:
        "I want more poetry presses in Canada"
    Output:
        [
          "poetry presses Canada submission guidelines",
          "Canadian small poetry presses open submissions",
          ...
        ]
    """
    prompt = f"""
                You are an expert search-query generator for a publishing data intelligence system.

Your job: expand a single user request (e.g., “I want horror agents in Canada”) into
N high-quality Google Search queries that will return *direct* pages for a single
press, magazine, or agent — NOT directories or lists.

===========================
RULES FOR QUERY GENERATION
===========================

1. Each query must be a short phrase suitable for Google Search.
2. Always include any user hints about:
   - genre (e.g., horror, romance, poetry)
   - region (e.g., Canada, UK, US)
3. STRICTLY avoid generating queries that lead to:
   - directories ("literary agents list", "publisher directory")
   - listicles (“top agents”, “best publishers 2025”)
   - Reedsy resource pages
   - JerichoWriters list pages
   - WritersUnion directories
   - Reddit, Medium, Substack, blog posts, advice articles
   - any website that lists multiple agents/presses
4. Queries should target SINGLE-ENTITY pages such as:
   - agency homepages
   - literary agent submission guidelines
   - “contact us” pages
   - “query guidelines” pages
   - press submission guidelines
   - magazine submission pages
5. Prefer keywords that bias Google toward official pages:
   - “literary agency”
   - “literary agent”
   - “publisher submissions”
   - “magazine submissions”
   - “query guidelines”
   - “query email”
   - “contact”
   - “submissions”
6. Use negative filters to avoid lists:
   - `-list -directory -top -best -archive -blog -medium -reddit -substack -jerichowriters -reedsy`
7. Queries must be distinct from one another.
8. Output exactly N queries, one per line, no numbering, no bullets, no extra text.

===========================
OUTPUT FORMAT
===========================

Return ONLY the list of queries.
Do not explain them.
Do not add JSON.
Do not add commentary.

One query per line. Nothing else."""


    resp = model.generate_content(prompt)
    text = resp.text.strip()
    queries = _extract_json_array(text)

    # Very defensive fallback: if nothing parsed, just reuse the user text
    if not queries:
        queries = [user_text.strip()]

    # Deduplicate and strip
    cleaned = []
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