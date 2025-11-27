import os
import sys
from datetime import datetime, timezone

from query_generator import generate_queries_with_gemini
from Google_search import call_google_search_save


def main():
    if len(sys.argv) > 1:
        user_text = " ".join(sys.argv[1:])
    else:
        user_text = input("Describe what you want to discover: ").strip()

    if not user_text:
        print("No input provided, exiting.")
        return

    print(f"User request: {user_text}")
    print("Generating queries with Gemini...")
    queries = generate_queries_with_gemini(user_text, n=5)

    print("Gemini queries:")
    for q in queries:
        print(" -", q)

    #ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    output_path = f"search_results_raw.ndjson"

    print(f"Running Google CSE search, saving to {output_path} ...")
    call_google_search_save(queries, output_path=output_path)
    print("Done.")


if __name__ == "__main__":
    main()
