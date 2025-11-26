import json
from pathlib import Path

# Only run when executed directly, not when imported by Scrapy
if __name__ == "__main__":
    groups = {
        "presses": ["presses1_2025-11-10.ndjson", "publishers2.json", "publishers3.json"],
        "magazines": ["Magazines1_2025-11-10.ndjson", "mangazines2.json", "mangazines3.json"],
        "agents": ["Agents1_2025-11-10.ndjson", "Agents3.json"]
    }

    # Fixed path: "scraper" (singular) not "scrapers" (plural)
    base_dir = Path(__file__).parent  # Use current directory (spiders folder)

    for group, files in groups.items():
        merged = []
        for file in files:
            file_path = base_dir / file
            if file_path.exists():
                try:
                    if file_path.suffix == ".json":
                        with open(file_path, "r", encoding="utf-8") as f:
                            try:
                                data = json.load(f)
                                if isinstance(data, list):
                                    merged.extend(data)
                                elif isinstance(data, dict):
                                    merged.append(data)
                            except json.JSONDecodeError:
                                print(f"⚠️ Skipping corrupted file: {file}")
                    elif file_path.suffix == ".ndjson":
                        with open(file_path, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line:
                                    try:
                                        item = json.loads(line)
                                        merged.append(item)
                                    except json.JSONDecodeError:
                                        print(f"⚠️ Skipping malformed line in {file}")
                except Exception as e:
                    print(f"⚠️ Error processing {file}: {e}")
            else:
                print(f"⚠️ File not found: {file}")
        output_path = base_dir / f"{group}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        print(f"✅ Merged {len(merged)} items into {output_path}")