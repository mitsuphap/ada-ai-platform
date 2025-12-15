"""
test_stage_timing.py - Test timing of individual stages with different configurations
"""
import time
import sys
from pathlib import Path

# Add parent directory to path to import scraper modules
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

from benchmark.benchmark_utils import PerformanceTimer

# Import functions
from llm_scrape_from_seeds import llm_scrape_from_seeds
from classify_search_results import classify_with_llm
from Google_search import call_google_search_save
from query_generator import generate_queries_with_gemini


def test_scraping_timing():
    """Test scraping with different worker counts"""
    # Check output directory
    test_seeds = parent_dir / "output" / "search_results_classified.ndjson"
    
    if not test_seeds.exists():
        print("Error: output/search_results_classified.ndjson not found.")
        print("Please run classification first (or discovery_search.py + classify_search_results.py)")
        return
    
    user_request = "Extract contact information and details."
    
    print("Testing scraping performance with different worker counts...\n")
    
    for workers in [1, 3, 5, 10]:
        print(f"\n{'='*60}")
        print(f"Testing with {workers} LLM workers")
        print(f"{'='*60}\n")
        
        timer = PerformanceTimer(f"scraping_{workers}_workers")
        timer.add_metadata("llm_workers", workers)
        timer.start()
        
        llm_scrape_from_seeds(
            seeds_path=str(test_seeds),
            output_path=str(parent_dir / "output" / f"discovered_sites_{workers}workers.ndjson"),
            user_request=user_request,
            max_workers=10,
            timer=timer
        )
        
        timer.end()
        timer.print_summary()
        
        output_dir = parent_dir / "benchmarks"
        output_dir.mkdir(exist_ok=True)
        timer.save(str(output_dir / f"scraping_{workers}workers.json"))


def test_classification_timing():
    """Test classification with different batch sizes"""
    # Check output directory
    test_raw = parent_dir / "output" / "search_results_raw.ndjson"
    
    if not test_raw.exists():
        print("Error: output/search_results_raw.ndjson not found.")
        print("Please run Google search first (discovery_search.py)")
        return
    
    print("Testing classification performance with different batch sizes...\n")
    
    for batch_size in [5, 10, 20]:
        print(f"\n{'='*60}")
        print(f"Testing with batch_size={batch_size}")
        print(f"{'='*60}\n")
        
        timer = PerformanceTimer(f"classification_batch{batch_size}")
        timer.add_metadata("batch_size", batch_size)
        timer.start()
        
        classify_with_llm(
            raw_path=str(test_raw),
            output_path=str(parent_dir / "output" / f"search_results_classified_batch{batch_size}.ndjson"),
            batch_size=batch_size,
            timer=timer
        )
        
        timer.end()
        timer.print_summary()
        
        output_dir = parent_dir / "benchmarks"
        output_dir.mkdir(exist_ok=True)
        timer.save(str(output_dir / f"classification_batch{batch_size}.json"))


def test_google_search_timing():
    """Test Google search timing"""
    test_query = "test query for benchmarking"
    
    print("Testing Google search performance...\n")
    
    timer = PerformanceTimer("google_search_test")
    timer.start()
    
    queries = ["test query 1", "test query 2", "test query 3"]
    call_google_search_save(
        queries,
        output_path=str(parent_dir / "output" / "search_results_test.ndjson"),
        timer=timer
    )
    
    timer.end()
    timer.print_summary()
    
    output_dir = parent_dir / "benchmarks"
    output_dir.mkdir(exist_ok=True)
    timer.save(str(output_dir / "google_search_test.json"))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        stage = sys.argv[1].lower()
        if stage == "scraping":
            test_scraping_timing()
        elif stage == "classification":
            test_classification_timing()
        elif stage == "google":
            test_google_search_timing()
        else:
            print(f"Unknown stage: {stage}")
            print("Available stages: scraping, classification, google")
    else:
        print("Usage: python test_stage_timing.py <stage>")
        print("\nAvailable stages:")
        print("  scraping       - Test scraping with different worker counts")
        print("  classification - Test classification with different batch sizes")
        print("  google         - Test Google search timing")
        print("\nExample: python test_stage_timing.py scraping")

