import os
import time
import json
import requests
from datetime import datetime, timezone
from pathlib import Path
import google.generativeai as genai

API_KEY = os.getenv("GOOGLE_CSE_API_KEY")
if not API_KEY:
    raise RuntimeError("GOOGLE_CSE_API_KEY is not set in the environment.")

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("models/gemini-2.5-flash")
LABELS = [
    "press_directory",
    "magazine_directory",
    "agent_directory",
    "single_press_site",
    "contest_listing",
    "blog_post",
    "other",
]

# HELPERS############################
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
    """Yield successive chunk_size-sized chunks from lst."""
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def classify_batch(batch):
    
   # Calls Gemini-API using google.generativeai and returns a JSON list.
    
    prompt = f"""
        You are a classifier for a publishing data pipeline.

        We have Google search results about literary presses, magazines, and agents.

        For each item, choose ONE label from this list:
        {LABELS}

        Output format REQUIREMENTS (very important):
        - ONE item per line
        - NO header line
        - NO bullet points
        - NO explanations before or after
        - Each line MUST be:
          URL|||LABEL|||CONFIDENCE|||REASON

         where:
         - URL is the item's URL
         - LABEL is one of: {LABELS}
         - CONFIDENCE is a float between 0.0 and 1.0
         - REASON is a short explanation (no newlines)

        Here are the items (with index, title, url, snippet, query, rank):

        {json.dumps(batch, indent=2, ensure_ascii=False)} """
    
    model =genai.GenerativeModel("models/gemini-2.5-flash")
    resp= model.generate_content(prompt)
    text=(resp.text or "").strip()

    lines = [ln.strip() for ln in text.splitlines() if "|||" in ln]
    results = []
    for line in lines:
        parts = line.split("|||",3)
        if len(parts) < 4:
            continue
        url, label, confidence_str, reason = [p.strip() for p in parts]
        #clean label
        if label not in LABELS:
            label = "other"
        #parse confidence
        try:
            confidence = float(confidence_str)
        except ValueError:
            confidence = 0.0
        
        results.append({
            "url": url,
            "label": label,
            "confidence": confidence,
            "reason": reason,
        })

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
#main PIPELINE
def classify_with_llm(raw_path, output_path,batch_size=10):
    rows=load_ndjson(raw_path)
   
    
    print(f"Loaded {len(rows)} raw results")

    out_file=Path(output_path)
    with out_file.open("w", encoding="utf-8") as f_out:
        for idx, batch in enumerate(chunk_list(rows, batch_size)):
            print(f"[LLM] Processing batch {idx}")  

            minimal_batch =[
                {
                    "title": r["title"],
                    "url": r["url"],
                    "snippet": r["snippet"],
                    "query": r["query"],
                    "rank": r["rank"],
                }
                for r in batch
            ]     

            labels= classify_batch(minimal_batch)
            lookup={item["url"]: item for item in labels}

            for r in batch:
                info = lookup.get(r["url"], {})
                r["label"] = info.get("label", "other")
                r["confidence"] = info.get("confidence", 0.0)
                r["reason"] = info.get("reason", "no reason provided")

                # Only keep high-value targets
                if (
                    r["label"]
                    in ["single_press_site", "agent_directory", "magazine_directory"]
                    and r["confidence"] >= 0.7
                ):
                    f_out.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Classification complete. Results saved to {output_path}")

if __name__ == "__main__":
    #ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    raw_file =  f"search_results_raw.ndjson"   # <-- change if your raw file name is fixed
    out_file = f"search_results_classified.ndjson"

    classify_with_llm(
        raw_path=raw_file,
        output_path=out_file,
        batch_size=10,
    )

 