"""
run_benchmark.py - Run full pipeline with timing
"""
import sys
import os
import time
from pathlib import Path

# Load environment variables first (before importing modules that need them)
try:
    from dotenv import load_dotenv
    # Try loading from current directory, parent directory, and project root
    env_paths = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]
    for env_path in env_paths:
        if env_path.exists():
            load_dotenv(env_path)
            print(f"Loaded environment from: {env_path}")
            break
    else:
        # Try default load_dotenv() which searches current directory and parents
        load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed. Using system environment variables only.")

# Check for required environment variables
missing_vars = []
if not os.getenv("GEMINI_API_KEY"):
    missing_vars.append("GEMINI_API_KEY")
if not os.getenv("GOOGLE_CSE_API_KEY"):
    missing_vars.append("GOOGLE_CSE_API_KEY")
if not os.getenv("GOOGLE_CSE_CX"):
    missing_vars.append("GOOGLE_CSE_CX")

if missing_vars:
    print("\n" + "="*60)
    print("ERROR: Missing required environment variables:")
    for var in missing_vars:
        print(f"  - {var}")
    print("\nPlease set these environment variables:")
    print("  1. Create a .env file in the scraper directory with:")
    print("     GEMINI_API_KEY=your_key_here")
    print("     GOOGLE_CSE_API_KEY=your_key_here")
    print("     GOOGLE_CSE_CX=your_cx_here")
    print("\n  2. Or set them in PowerShell:")
    print("     $env:GEMINI_API_KEY='your_key_here'")
    print("     $env:GOOGLE_CSE_API_KEY='your_key_here'")
    print("     $env:GOOGLE_CSE_CX='your_cx_here'")
    print("="*60 + "\n")
    sys.exit(1)

# Add parent directory to path to import scraper modules
import sys
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from benchmark.benchmark_utils import PerformanceTimer

# Import your pipeline functions
from query_generator import generate_queries_with_gemini
from Google_search import call_google_search_save
from classify_search_results import classify_with_llm
from llm_scrape_from_seeds import llm_scrape_from_seeds


def run_full_pipeline(user_request: str, benchmark_name: str = "pipeline"):
    """Run the full pipeline with detailed timing"""
    
    timer = PerformanceTimer(benchmark_name)
    timer.start()
    
    # Stage 1: Query Generation
    with timer.stage("query_generation"):
        queries = generate_queries_with_gemini(user_request, n=5)
        timer.add_metadata("queries_generated", len(queries))
        print(f"Generated {len(queries)} queries:")
        for q in queries:
            print(f"  - {q}")
    
    # Ensure output directory exists
    output_dir = parent_dir / "output"
    output_dir.mkdir(exist_ok=True)
    
    # Stage 2: Google Search
    raw_results_path = str(output_dir / "search_results_raw.ndjson")
    with timer.stage("google_search"):
        call_google_search_save(
            queries, 
            raw_results_path, 
            timer=timer
        )
    
    # Stage 3: Classification
    classified_path = str(output_dir / "search_results_classified.ndjson")
    with timer.stage("classification"):
        classify_with_llm(
            raw_results_path,
            classified_path,
            batch_size=10,
            max_workers=3,  # Parallel batch processing
            timer=timer
        )
    
    # Stage 4: Scraping
    discovered_path = str(output_dir / "discovered_sites.ndjson")
    with timer.stage("scraping"):
        llm_scrape_from_seeds(
            seeds_path=classified_path,
            output_path=discovered_path,
            user_request=user_request,
            max_workers=10,
            llm_workers=5,  # Parallel LLM processing
            timer=timer
        )
    
    timer.end()
    return timer


if __name__ == "__main__":
    if len(sys.argv) < 2:
        user_request = input("Enter your search request: ")
        benchmark_name = "pipeline_run"
    elif len(sys.argv) == 2:
        # Only user request provided
        user_request = sys.argv[1]
        benchmark_name = "pipeline_run"
    else:
        # User request and benchmark name provided
        user_request = sys.argv[1]
        benchmark_name = sys.argv[2]
    
    print(f"\nRunning benchmark: {benchmark_name}")
    print(f"User request: {user_request}\n")
    
    timer = run_full_pipeline(user_request, benchmark_name)
    
    # Save results (in parent directory's benchmarks folder)
    output_dir = parent_dir / "benchmarks"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"{benchmark_name}_{int(time.time())}.json"
    
    timer.save(str(output_file))
    timer.print_summary()
    
    print(f"\nBenchmark saved to: {output_file}")

