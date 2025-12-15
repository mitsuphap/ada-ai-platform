import sys
from pathlib import Path

from query_generator import generate_queries_with_gemini
from Google_search import call_google_search_save

# NEW: vertical registry
from verticals import get_vertical_for_request


def main():
    if len(sys.argv) > 1:
        user_text = " ".join(sys.argv[1:])
    else:
        user_text = input("Describe what you want to discover: ").strip()

    if not user_text:
        print("No input provided, exiting.")
        return

    print(f"User request: {user_text}")
    import json
    # Always write to output/ directory (consistent with other outputs)
    run_context_path = Path("output/run_context.json")
    run_context_path.parent.mkdir(parents=True, exist_ok=True)
    with open(run_context_path, "w", encoding="utf-8") as f:
        json.dump({"user_request": user_text}, f, ensure_ascii=False)
    print(f"[DEBUG] Saved run_context.json to {run_context_path}")

    # NEW: detect vertical
    vertical, det = get_vertical_for_request(user_text)
    if vertical:
        print(f"[vertical] {vertical.name} conf={det.confidence:.2f} reason={det.reason}")
    else:
        print("[vertical] none")

    print("Generating queries with Gemini...")
    base_queries = generate_queries_with_gemini(user_text, n=5)

    print("Gemini queries:")
    for q in base_queries:
        print(" -", q)

    # NEW: apply vertical enhancements (domain anchoring / exact name)
    if vertical:
        queries = vertical.enhance_search_queries(user_text, base_queries)
        print("\nVertical-enhanced queries:")
        for q in queries:
            print(" -", q)
    else:
        queries = base_queries

    # Ensure output directory exists
    output_path = "output/search_results_raw.ndjson"
    Path("output").mkdir(exist_ok=True)

    print(f"\nRunning Google CSE search, saving to {output_path} ...")
    call_google_search_save(queries, output_path=output_path)
    print("Done.")


if __name__ == "__main__":
    main()
