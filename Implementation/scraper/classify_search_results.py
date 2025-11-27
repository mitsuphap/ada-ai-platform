import os
import json
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# Load env
try:
    load_dotenv()
except:
    pass

API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set in the environment. "
        "Check docker-compose.yml and .env file."
    )

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-2.5-flash")


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

MIN_CONFIDENCE = 0.5  # adjust if you want


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def load_ndjson(path):
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


def classify_batch(batch, domain_description, labels):
    """
    Calls Gemini to classify a batch of search results into the provided labels.
    """
    prompt = f"""
You are a classifier for a data pipeline.

{domain_description.strip()}

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

Here are the items (with index, title, url, snippet, query, rank):

{json.dumps(batch, indent=2, ensure_ascii=False)}
"""

    resp = model.generate_content(prompt)
    text = (getattr(resp, "text", "") or "").strip()

    lines = [ln.strip() for ln in text.splitlines() if "|||" in ln]
    results = []

    for line in lines:
        parts = line.split("|||", 3)
        if len(parts) < 4:
            continue

        url, label, confidence_str, reason = [p.strip() for p in parts]

        # Normalize label
        if label not in labels:
            label = "other"

        # Parse confidence
        try:
            confidence = float(confidence_str)
        except ValueError:
            confidence = 0.0

        results.append(
            {
                "url": url,
                "label": label,
                "confidence": confidence,
                "reason": reason,
            }
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


def classify_with_llm(raw_path, output_path, batch_size=10):
    rows = load_ndjson(raw_path)
    print(f"Loaded {len(rows)} raw results")

    out_file = Path(output_path)
    with out_file.open("w", encoding="utf-8") as f_out:
        for idx, batch in enumerate(chunk_list(rows, batch_size)):
            print(f"[LLM] Processing batch {idx}")

            minimal_batch = [
                {
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": r["snippet"],
                    "query": r["query"],
                    "rank": r["rank"],
                }
                for r in batch
            ]

            labels = classify_batch(
                minimal_batch,
                domain_description=DOMAIN_DESCRIPTION,
                labels=LABELS,
            )
            lookup = {item["url"]: item for item in labels}

            for r in batch:
                info = lookup.get(r["url"], {})
                r["label"] = info.get("label", "other")
                r["confidence"] = info.get("confidence", 0.0)
                r["reason"] = info.get("reason", "no reason provided")

                # Filter logic: keep only certain labels if configured
                if KEEP_LABELS is None:
                    # Keep everything
                    f_out.write(json.dumps(r, ensure_ascii=False) + "\n")
                else:
                    if (
                        r["label"] in KEEP_LABELS
                        and r["confidence"] >= MIN_CONFIDENCE
                    ):
                        f_out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Classification complete. Results saved to {output_path}")


if __name__ == "__main__":
    raw_file = "search_results_raw.ndjson"
    out_file = "search_results_classified.ndjson"

    classify_with_llm(
        raw_path=raw_file,
        output_path=out_file,
        batch_size=10,
    )
