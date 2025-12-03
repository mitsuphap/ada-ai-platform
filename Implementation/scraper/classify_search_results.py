import os
import json
from pathlib import Path
from typing import Optional, Any
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
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

# Load env - try multiple locations
try:
    from pathlib import Path
    env_paths = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]
    loaded = False
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            loaded = True
            break
    if not loaded:
        load_dotenv()  # Try default search
except:
    pass

API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set in the environment.\n"
        "Please set it in one of these ways:\n"
        "1. Create a .env file in the scraper directory\n"
        "2. Set environment variable: $env:GEMINI_API_KEY='your_key'\n"
        "3. Check docker-compose.yml and .env file"
    )

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(
    "models/gemini-2.5-flash",
    generation_config={
        "temperature": 0.0,  # Set to 0 for more consistent/deterministic classification
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

MIN_CONFIDENCE = 0.95  # Filter for high-confidence results (>= 0.95)


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


def classify_with_llm(raw_path, output_path, batch_size=10, max_workers=3, timer: Optional[Any] = None):
    rows = load_ndjson(raw_path)
    print(f"Loaded {len(rows)} raw results")

    if timer:
        timer.add_metadata("batch_size", batch_size)
        timer.add_metadata("max_workers", max_workers)
        timer.add_metadata("num_results", len(rows))

    # Ensure output directory exists
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    batches = list(chunk_list(rows, batch_size))
    out_file = Path(output_path)
    lock = threading.Lock()
    passed_count = [0]  # Use list to allow modification in nested functions
    total_classified = [0]  # Use list to allow modification in nested functions
    all_results = []
    
    def process_batch(batch, idx):
        """Process one batch and return results"""
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

        batch_results = []
        batch_passed = 0
        batch_total = 0
        
        for r in batch:
            info = lookup.get(r["url"], {})
            r["label"] = info.get("label", "other")
            r["confidence"] = info.get("confidence", 0.0)
            r["reason"] = info.get("reason", "no reason provided")
            batch_total += 1

            # Filter logic: keep only certain labels if configured
            if KEEP_LABELS is None:
                # Keep everything
                batch_results.append(r)
                batch_passed += 1
            else:
                if (
                    r["label"] in KEEP_LABELS
                    and r["confidence"] >= MIN_CONFIDENCE
                ):
                    batch_results.append(r)
                    batch_passed += 1
                else:
                    # Debug: print why result was filtered out
                    print(f"  Filtered out: {r['url'][:60]}... label={r['label']}, confidence={r['confidence']:.2f}")
        
        return batch_results, batch_total, batch_passed
    
    def run_parallel_classification():
        # Parallel batch processing (always use parallel)
        print(f"Processing {len(batches)} batches in parallel (max_workers={max_workers})...")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {
                executor.submit(process_batch, batch, idx): idx 
                for idx, batch in enumerate(batches)
            }
            for future in as_completed(future_to_batch):
                try:
                    batch_results, batch_count, batch_passed = future.result()
                    all_results.extend(batch_results)
                    with lock:
                        total_classified[0] += batch_count
                        passed_count[0] += batch_passed
                except Exception as e:
                    print(f"Error processing batch {future_to_batch[future]}: {e}")
    
    if timer:
        with timer.stage("llm_classification"):
            run_parallel_classification()
    else:
        # Still use parallel processing even without timer
        run_parallel_classification()
        
    # Write all results (same for both timer and non-timer paths)
    with out_file.open("w", encoding="utf-8") as f_out:
        for r in all_results:
            f_out.write(json.dumps(r, ensure_ascii=False) + "\n")
    
    if timer:
        timer.add_metadata("results_passed", passed_count[0])
        timer.add_metadata("total_classified", total_classified[0])

    print(f"Classification complete. Results saved to {output_path}")
    print(f"  Total classified: {total_classified[0]}, Passed filter: {passed_count[0]} (confidence >= {MIN_CONFIDENCE}, labels: {KEEP_LABELS})")


if __name__ == "__main__":
    from pathlib import Path
    Path("output").mkdir(exist_ok=True)
    
    raw_file = "output/search_results_raw.ndjson"
    out_file = "output/search_results_classified.ndjson"

    classify_with_llm(
        raw_path=raw_file,
        output_path=out_file,
        batch_size=10,
    )
