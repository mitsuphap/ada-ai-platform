# pick_urls_to_scrape.py
import json
from pathlib import Path
from typing import List, Dict, Any


def load_ndjson(path: str) -> List[Dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main(
    classified_path: str = "search_results_classified.ndjson",
    output_path: str = "chosen_seeds.ndjson",
) -> None:
    """
    Read search_results_raw.ndjson (from google_search.py),
    show the user a numbered list of results, and let them
    pick which URLs to turn into seeds for scraping.

    This is now GENERIC:
    - It does NOT filter by specific labels.
    - If 'label' / 'confidence' exist, they are shown, but not required.
    """
    rows = load_ndjson(classified_path)

    if not rows:
        print(f"No rows found in {classified_path}")
        return

    # No label filtering anymore – just use all rows
    interesting = rows

    print(f"Found {len(interesting)} results:\n")

    for idx, r in enumerate(interesting, start=1):
  
        conf = r.get("confidence", None)
        title = r.get("title") or ""
        url = r.get("url") or ""
        query = r.get("query") or ""

      

        print(f"   Title : {title}")
        print(f"   URL   : {url}")
        print(f"   Query : {query}")
        print()

    choice = input("Type indexes to scrape (e.g. 1,3,5-7) or 'all': ").strip()

    if choice.lower() == "all":
        selected = interesting
    else:
        indices = set()
        parts = [p.strip() for p in choice.split(",") if p.strip()]
        for p in parts:
            if "-" in p:
                a, b = p.split("-", 1)
                for i in range(int(a), int(b) + 1):
                    indices.add(i)
            else:
                indices.add(int(p))

        selected = [
            r for i, r in enumerate(interesting, start=1) if i in indices
        ]

    print(f"\nYou selected {len(selected)} URL.")

    with open(output_path, "w", encoding="utf-8") as f_out:
        for r in selected:
            seed = {
                "url": r.get("url"),
                "label": r.get("label", "unknown"),
                "source_query": r.get("query"),
                "title": r.get("title"),
            }
            f_out.write(json.dumps(seed, ensure_ascii=False) + "\n")

    print(f"Saved seeds to {output_path}")


if __name__ == "__main__":
    main()
