# pick_urls_to_scrape.py
import json
from pathlib import Path

LABELS_OF_INTEREST = {
    "press_directory",
    "magazine_directory",
    "agent_directory",
    "single_press_site",
}

def load_ndjson(path):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows

def main(
    classified_path="search_results_classified.ndjson",
    output_path="chosen_seeds.ndjson",
):
    rows = load_ndjson(classified_path)

    # maybe only show interesting labels
    interesting = [r for r in rows if r.get("label") in LABELS_OF_INTEREST]

    print(f"Found {len(interesting)} interesting results:\n")

    for idx, r in enumerate(interesting, start=1):
        print(f"{idx}. [{r.get('label')}] (conf={r.get('confidence', 0):.2f})")
        print(f"   Title : {r.get('title')}")
        print(f"   URL   : {r.get('url')}")
        print(f"   Query : {r.get('query')}")
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

    print(f"\nYou selected {len(selected)} URLs.")

    with open(output_path, "w", encoding="utf-8") as f_out:
        for r in selected:
            # keep only what your seed needs
            seed = {
                "url": r["url"],
                "label": r["label"],
                "source_query": r["query"],
                "title": r["title"],
            }
            f_out.write(json.dumps(seed, ensure_ascii=False) + "\n")

    print(f"Saved seeds to {output_path}")

if __name__ == "__main__":
    main()