import sys

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
    with open("run_context.json", "w", encoding="utf-8") as f:
        json.dump({"user_request": user_text}, f, ensure_ascii=False)



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

    output_path = "search_results_raw.ndjson"

    print(f"\nRunning Google CSE search, saving to {output_path} ...")
    call_google_search_save(queries, output_path=output_path)
    print("Done.")


if __name__ == "__main__":
    main()
