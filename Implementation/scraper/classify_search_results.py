import os
import json
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# NEW: vertical registry
from verticals import get_vertical_for_request

# Load env
try:
    load_dotenv()
except:
    pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set in the environment. "
        "Check docker-compose.yml and .env file."
    )

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "models/gemini-2.5-flash",
    generation_config={
        "temperature": 0.0,  # deterministic-ish classification
    },
)

# Brief description of what these search results are about
DOMAIN_DESCRIPTION = """
We have Google search results about GENERAL WEB ENTITIES for my project.
Each result is a webpage that might or might not be relevant.
"""

# Define your own labels for the current task
LABELS = [
    "highly_relevant",
    "somewhat_relevant",
    "irrelevant",
    "other",
]

# Optional: which labels to actually write to output
KEEP_LABELS = [
    "highly_relevant",
    "somewhat_relevant",
]  # or set to None to keep everything

MIN_CONFIDENCE = 0.95  # keep only high confidence results

# NEW: optional batch size guard after strict filtering
MAX_PER_QUERY_AFTER_FILTER = 15  # keep top N per source query to reduce noise


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_ndjson(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i : i + chunk_size]


def _apply_vertical_validation(user_request: str, rows: list, vertical):
    """
    Apply vertical.validate_result() before calling Gemini.
    - Blocks invalid domains
    - Adds _vertical_score_delta and _vertical_reason
    - Optionally re-ranks within each query
    """
    if not vertical:
        return rows

    kept = []
    blocked = 0

    for r in rows:
        cand = {
            "url": r.get("url"),
            "title": r.get("title", ""),
            "snippet": r.get("snippet", ""),
        }
        vr = vertical.validate_result(user_request, cand)
        if not vr.allow:
            blocked += 1
            continue

        r["_vertical_score_delta"] = vr.score_delta
        r["_vertical_reason"] = vr.reason
        kept.append(r)

    print(f"[vertical] kept {len(kept)}/{len(rows)} candidates, blocked {blocked}")

    # Optional: re-rank by score_delta, grouped by query so each query keeps best results
    grouped = {}
    for r in kept:
        q = r.get("query") or r.get("source_query") or "unknown_query"
        grouped.setdefault(q, []).append(r)

    reranked = []
    for q, items in grouped.items():
        items.sort(key=lambda x: x.get("_vertical_score_delta", 0.0), reverse=True)
        if MAX_PER_QUERY_AFTER_FILTER:
            items = items[:MAX_PER_QUERY_AFTER_FILTER]
        reranked.extend(items)

    return reranked


def classify_batch(batch, domain_description, labels, user_request: str, vertical=None):
    """
    Calls Gemini to classify a batch of search results into the provided labels.
    """
    # NEW: vertical-aware description (gives Gemini context without making it do rules)
    vertical_hint = ""
    if vertical:
        vertical_hint = f"""
VERTICAL CONTEXT:
- This request appears to match vertical: {vertical.name}
- Prefer OFFICIAL / authoritative sources.
- If higher-ed: prefer official .edu domains and pages that clearly match the target institution name.
"""

    prompt = f"""
You are a classifier for a data pipeline.

{domain_description.strip()}

User request:
{user_request}

{vertical_hint.strip()}

For each item, choose ONE label from this list:
{labels}

Output format REQUIREMENTS (very important):
- ONE item per line
- NO header line
- NO bullet points
- NO explanations before or after
- Each line MUST be:
  URL|||LABEL|||CONFIDENCE|||REASON

where:
- URL is the item's URL
- LABEL is one of: {labels}
- CONFIDENCE is a float between 0.0 and 1.0
- REASON is a short explanation (no newlines)

Here are the items (with title, url, snippet, query, rank):

{json.dumps(batch, indent=2, ensure_ascii=False)}
""".strip()

    resp = model.generate_content(prompt)
    text = (getattr(resp, "text", "") or "").strip()

    lines = [ln.strip() for ln in text.splitlines() if "|||" in ln]
    results = []

    for line in lines:
        parts = line.split("|||", 3)
        if len(parts) < 4:
            continue

        url, label, confidence_str, reason = [p.strip() for p in parts]

        if label not in labels:
            label = "other"

        try:
            confidence = float(confidence_str)
        except ValueError:
            confidence = 0.0

        results.append(
            {"url": url, "label": label, "confidence": confidence, "reason": reason}
        )

    if not results:
        print("⚠ Gemini returned no parsable lines, using fallback 'other'")
        results = [
            {
                "url": item.get("url"),
                "label": "other",
                "confidence": 0.0,
                "reason": "fallback_due_to_no_parsable_lines",
            }
            for item in batch
        ]

    return results


def classify_with_llm(raw_path, output_path, batch_size=10, user_request: str = ""):
    rows = load_ndjson(raw_path)
    print(f"Loaded {len(rows)} raw results")

    if not user_request:
        # If you don't pass it, default to something; but BEST is to pass same request used in discovery_search
        user_request = "Classify results for relevance."

    # NEW: detect vertical once for this run
    vertical, det = get_vertical_for_request(user_request)
    if vertical:
        print(f"[vertical] {vertical.name} conf={det.confidence:.2f} reason={det.reason}")
    else:
        print("[vertical] none")

    # NEW: strict vertical filtering before any LLM calls
    rows = _apply_vertical_validation(user_request, rows, vertical)

    out_file = Path(output_path)
    passed_count = 0
    total_classified = 0

    with out_file.open("w", encoding="utf-8") as f_out:
        for idx, batch in enumerate(chunk_list(rows, batch_size)):
            print(f"[LLM] Processing batch {idx}")

            minimal_batch = [
                {
                    "title": r.get("title"),
                    "url": r.get("url"),
                    "snippet": r.get("snippet"),
                    "query": r.get("query"),
                    "rank": r.get("rank"),
                }
                for r in batch
            ]

            labels = classify_batch(
                minimal_batch,
                domain_description=DOMAIN_DESCRIPTION,
                labels=LABELS,
                user_request=user_request,
                vertical=vertical,
            )
            lookup = {item["url"]: item for item in labels}

            for r in batch:
                info = lookup.get(r["url"], {})
                r["label"] = info.get("label", "other")
                r["confidence"] = info.get("confidence", 0.0)
                r["reason"] = info.get("reason", "no reason provided")
                total_classified += 1

                # NEW: carry vertical debug info forward
                if vertical:
                    r["vertical"] = vertical.name
                    r["vertical_reason"] = r.get("_vertical_reason")
                    r["vertical_score_delta"] = r.get("_vertical_score_delta")

                # Filter logic
                if KEEP_LABELS is None:
                    f_out.write(json.dumps(r, ensure_ascii=False) + "\n")
                    passed_count += 1
                else:
                    if r["label"] in KEEP_LABELS and r["confidence"] >= MIN_CONFIDENCE:
                        f_out.write(json.dumps(r, ensure_ascii=False) + "\n")
                        passed_count += 1
                    else:
                        print(
                            f"  Filtered out: {r['url'][:60]}... "
                            f"label={r['label']}, confidence={r['confidence']:.2f}"
                        )

    print(f"Classification complete. Results saved to {output_path}")
    print(
        f"  Total classified: {total_classified}, Passed filter: {passed_count} "
        f"(confidence >= {MIN_CONFIDENCE}, labels: {KEEP_LABELS})"
    )


if __name__ == "__main__":
    import time

    raw_file = "search_results_raw.ndjson"
    out_file = "search_results_classified.ndjson"

    import json
    try:
        request_user = json.load(open("run_context.json", "r", encoding="utf-8")).get("user_request", "")
    except:
        request_user = ""
    if not request_user:
          request_user = input("Enter the SAME user request you searched with: ").strip()


    start = time.time()
    classify_with_llm(
        raw_path=raw_file,
        output_path=out_file,
        batch_size=30,
        user_request=request_user,
    )
    end = time.time()
    print(f"Completed in {end - start:.2f} seconds.")
