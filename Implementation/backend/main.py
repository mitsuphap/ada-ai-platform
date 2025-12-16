# main.py (updated)
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.db import get_engine, get_db
from app.auto_generator import auto_generate_all_routers, get_available_auto_tables
from pydantic import BaseModel
from typing import List, Optional
import sys
from pathlib import Path
import tempfile
import os
import json

# Manual routers removed - using auto-generation only

app = FastAPI(
    title="Ada Automated Data Intelligence",
    description="Self-generating REST API with automatic endpoint creation based on database schema",
    version="2.0.0"
)

# Add rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS: enable during dev; tighten origins later ---
# Note: FastAPI CORS doesn't support wildcards like "*.vercel.app", use "*" for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for now (can restrict later)
    allow_credentials=False,  # Must be False when using "*" for origins
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "message": "Hello, Publishing Industry Data Intelligence Platform Auto-Generated API!",
        "docs": "/docs",
        "auto_api_prefix": "/auto"
    }

@app.get("/health")
def health_check():
    # Simple health check - app is healthy if it can respond
    # Don't check database here to keep health check fast
    return {"status": "ok"}

@app.get("/debug/schema/{table_name}")
def debug_table_schema(table_name: str, db: Session = Depends(get_db)):
    """Debug endpoint to check what columns exist in a table"""
    try:
        from sqlalchemy import inspect
        inspector = inspect(db.bind)
        columns = inspector.get_columns(table_name, schema="core")
        
        column_info = [
            {
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True)
            }
            for col in columns
        ]
        
        return {
            "table_name": table_name,
            "schema": "core",
            "columns": column_info,
            "column_count": len(column_info),
            "column_names": [col["name"] for col in column_info]
        }
    except Exception as e:
        return {"error": str(e), "table_name": table_name}


@app.get("/auto/tables")
def list_auto_tables(db: Session = Depends(get_db)):
    """Return the list of auto-generated tables after exclusions"""
    try:
        tables = get_available_auto_tables(db)
        return {"tables": tables, "count": len(tables)}
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database not available. Scraper endpoints (/scraper/*) are still functional. Error: {str(e)}"
        )

# Scraper API endpoints - Define models and routes FIRST, before path setup
# Request/Response models
class SearchRequest(BaseModel):
    topic: str
    data_specification: Optional[str] = None

class SearchResponse(BaseModel):
    queries: List[str]
    search_results: List[dict]
    message: str

class SaveSeedsRequest(BaseModel):
    urls: List[str]
    titles: Optional[List[str]] = None
    queries: Optional[List[str]] = None

class ScrapeRequest(BaseModel):
    topic: Optional[str] = None
    data_specification: Optional[str] = None

class LegacyScrapeRequest(BaseModel):
    urls: List[str]
    topic: Optional[str] = None
    data_specification: Optional[str] = None

class ScrapeResponse(BaseModel):
    results: List[dict]
    message: str
    total_available_links: Optional[int] = None
    scraped_count: Optional[int] = None
    has_more: Optional[bool] = None

# Add scraper to path - handle both Docker (/app/scraper) and local dev (../scraper)
scraper_path = Path("/app/scraper")  # Docker: scraper is mounted at /app/scraper
if not scraper_path.exists():
    scraper_path = Path(__file__).parent / "scraper"  # Try sibling to main.py
if not scraper_path.exists():
    scraper_path = Path(__file__).parent.parent / "scraper"  # Local dev: scraper is sibling to backend
if scraper_path.exists():
    sys.path.insert(0, str(scraper_path))
    print(f"✅ Added scraper path to sys.path: {scraper_path}")
else:
    print(f"⚠️  Warning: Scraper path not found. Searched: /app/scraper, {Path(__file__).parent / 'scraper'}, {Path(__file__).parent.parent / 'scraper'}")

# Output directory - mounted at /data in Docker, or use scraper/output locally
OUTPUT_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent.parent / "scraper" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Test route to verify registration works
@app.get("/scraper/test")
def test_scraper_route():
    return {"message": "Scraper routes are working"}

@app.post("/scraper/generate-search")
def generate_and_search(request: SearchRequest, http_request: Request):
    """Step 1: Generate queries from topic and execute Google search, save to search_results_raw.ndjson"""
    try:
        from query_generator import generate_queries_with_gemini
        from Google_search import call_google_search_save
        from verticals import get_vertical_for_request
        
        # Generate queries - incorporate data_specification if provided
        if request.data_specification:
            topic_with_spec = f"{request.topic}. Focus on finding: {request.data_specification}"
        else:
            topic_with_spec = request.topic
        
        # Save user_request to run_context.json in output/ directory (consistent location)
        run_context_path = OUTPUT_DIR / "run_context.json"  # Docker: /data/run_context.json, Local: scraper/output/run_context.json
        run_context_path.parent.mkdir(parents=True, exist_ok=True)
        with open(run_context_path, "w", encoding="utf-8") as f:
            json.dump({"user_request": topic_with_spec}, f, ensure_ascii=False)
        
        # NEW: detect vertical and enhance queries (like discovery_search.py)
        vertical, det = get_vertical_for_request(topic_with_spec)
        if vertical:
            print(f"[vertical] {vertical.name} conf={det.confidence:.2f} reason={det.reason}")
        else:
            print("[vertical] none")
        
        base_queries = generate_queries_with_gemini(topic_with_spec, n=5)
        
        # Apply vertical enhancements (domain anchoring / exact name)
        if vertical:
            queries = vertical.enhance_search_queries(topic_with_spec, base_queries)
            print(f"[API] Vertical-enhanced queries: {len(queries)} queries")
        else:
            queries = base_queries
        
        # Save to search_results_raw.ndjson in output directory (matches script workflow)
        output_path = OUTPUT_DIR / "search_results_raw.ndjson"
        call_google_search_save(queries, output_path=str(output_path), results_per_query=10)
        
        # Load and return results (with deduplication as safety measure)
        results = []
        seen_urls = set()
        if output_path.exists():
            with open(output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        result = json.loads(line)
                        # Deduplicate by URL (normalize for comparison)
                        normalized_url = result.get("url", "").rstrip('/').lower()
                        if normalized_url and normalized_url not in seen_urls:
                            seen_urls.add(normalized_url)
                            results.append(result)
        
        return SearchResponse(
            queries=queries,
            search_results=results,
            message=f"Found {len(results)} unique search results. Saved to search_results_raw.ndjson"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/scraper/search-results")
def get_search_results():
    """Get search results from search_results_raw.ndjson"""
    try:
        results_path = OUTPUT_DIR / "search_results_raw.ndjson"
        
        if not results_path.exists():
            return {
                "search_results": [],
                "message": "No search results found. Run a search first."
            }
        
        results = []
        seen_urls = set()
        with open(results_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    result = json.loads(line)
                    # Deduplicate by URL (normalize for comparison)
                    normalized_url = result.get("url", "").rstrip('/').lower()
                    if normalized_url and normalized_url not in seen_urls:
                        seen_urls.add(normalized_url)
                        results.append(result)
        
        return {
            "search_results": results,
            "message": f"Found {len(results)} unique search results"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scraper/save-seeds")
def save_seeds(request: SaveSeedsRequest):
    """Step 2: Save selected URLs to chosen_seeds.ndjson"""
    try:
        seeds_path = OUTPUT_DIR / "chosen_seeds.ndjson"
        
        seeds = []
        for idx, url in enumerate(request.urls):
            seed = {
                "url": url,
                "label": "user_selected",
                "title": request.titles[idx] if request.titles and idx < len(request.titles) else url,
                "source_query": request.queries[idx] if request.queries and idx < len(request.queries) else "user_selected"
            }
            seeds.append(seed)
        
        # Write to chosen_seeds.ndjson
        with open(seeds_path, 'w', encoding='utf-8') as f:
            for seed in seeds:
                f.write(json.dumps(seed, ensure_ascii=False) + '\n')
        
        return {
            "message": f"Saved {len(seeds)} URLs to chosen_seeds.ndjson",
            "seeds_count": len(seeds),
            "path": str(seeds_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scraper/scrape-seeds", response_model=ScrapeResponse)
def scrape_seeds(request: ScrapeRequest):
    """Step 3: Read chosen_seeds.ndjson and scrape, save to discovered_sites.ndjson"""
    try:
        from llm_scrape_from_seeds import llm_scrape_from_seeds, PARSER_INSTRUCTIONS
        
        seeds_path = OUTPUT_DIR / "chosen_seeds.ndjson"
        output_path = OUTPUT_DIR / "discovered_sites.ndjson"
        
        if not seeds_path.exists():
            raise HTTPException(status_code=404, detail="chosen_seeds.ndjson not found. Please select URLs first.")
        
        # Build user_request (use topic directly, like terminal)
        user_request = request.topic if request.topic else "Extract a general profile of each entity."
        
        # Modify PARSER_INSTRUCTIONS if data_specification provided (but don't duplicate topic)
        custom_instructions = None
        if request.data_specification and request.data_specification != request.topic:
            custom_instructions = PARSER_INSTRUCTIONS + f"\n\nIMPORTANT: The user specifically wants to extract: {request.data_specification}. Make sure to prioritize and extract this information prominently. If this information is not found on the page, set the relevant field(s) to null but ensure you thoroughly search for it."
        
        # Scrape from chosen_seeds.ndjson, save to discovered_sites.ndjson
        llm_scrape_from_seeds(
            seeds_path=str(seeds_path),
            output_path=str(output_path),
            delay_seconds=0.0,  # No delay needed with parallel processing
            user_request=user_request,
            custom_parser_instructions=custom_instructions,
            max_workers=10,  # Parallel HTML fetching
            llm_workers=10  # More parallel LLM workers for faster processing
        )
        
        # Load results
        results = []
        if output_path.exists():
            with open(output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        results.append(json.loads(line))
        
        return ScrapeResponse(
            results=results,
            message=f"Scraped {len(results)} entities. Saved to discovered_sites.ndjson"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scraper/scrape-urls", response_model=ScrapeResponse)
def scrape_selected_urls(request: LegacyScrapeRequest, http_request: Request):
    """Legacy endpoint: Scrape selected URLs with custom data specification (for backward compatibility)"""
    try:
        from llm_scrape_from_seeds import llm_scrape_from_seeds, PARSER_INSTRUCTIONS
        
        # Create seeds file from selected URLs
        seeds = []
        for url in request.urls:
            seeds.append({
                "url": url,
                "label": "single_press_site",  # Default label
                "title": url,
                "source_query": "user_selected"
            })
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ndjson', delete=False) as tmp_seeds:
            seeds_path = tmp_seeds.name
            for seed in seeds:
                tmp_seeds.write(json.dumps(seed, ensure_ascii=False) + '\n')
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ndjson', delete=False) as tmp_output:
            output_path = tmp_output.name
        
        # Build user_request (use topic directly, like terminal)
        user_request = request.topic if request.topic else "Extract a general profile of each entity."
        
        # Modify PARSER_INSTRUCTIONS if data_specification provided (but don't duplicate topic)
        custom_instructions = None
        if request.data_specification and request.data_specification != request.topic:
            custom_instructions = PARSER_INSTRUCTIONS + f"\n\nIMPORTANT: The user specifically wants to extract: {request.data_specification}. Make sure to prioritize and extract this information prominently. If this information is not found on the page, set the relevant field(s) to null but ensure you thoroughly search for it."
        
        # Scrape with topic context
        llm_scrape_from_seeds(
            seeds_path=seeds_path,
            output_path=output_path,
            delay_seconds=0.0,  # No delay needed with parallel processing
            user_request=user_request,
            custom_parser_instructions=custom_instructions,
            max_workers=10,  # Parallel HTML fetching
            llm_workers=10  # More parallel LLM workers for faster processing
        )
        
        # Load results
        results = []
        with open(output_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        
        # Clean up
        os.unlink(seeds_path)
        os.unlink(output_path)
        
        return ScrapeResponse(
            results=results,
            message=f"Scraped {len(results)} entities"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scraper/search-and-scrape-auto", response_model=ScrapeResponse)
def search_and_scrape_auto(request: ScrapeRequest):
    """Complete automated flow: Search -> Classify -> Filter (confidence >= 0.95) -> Auto-scrape"""
    import time
    start_time = time.time()
    stage_times = {}
    
    try:
        # Validate topic is provided
        if not request.topic:
            raise HTTPException(status_code=400, detail="Topic is required")
        
        from query_generator import generate_queries_with_gemini
        from Google_search import call_google_search_save
        from classify_search_results import classify_with_llm
        from llm_scrape_from_seeds import llm_scrape_from_seeds, PARSER_INSTRUCTIONS
        from verticals import get_vertical_for_request
        
        # Step 1: Generate queries and search
        step_start = time.time()
        if request.data_specification:
            topic_with_spec = f"{request.topic}. Focus on finding: {request.data_specification}"
        else:
            topic_with_spec = request.topic
        
        # Save user_request to run_context.json in output/ directory (consistent location)
        run_context_path = OUTPUT_DIR / "run_context.json"  # Docker: /data/run_context.json, Local: scraper/output/run_context.json
        run_context_path.parent.mkdir(parents=True, exist_ok=True)
        with open(run_context_path, "w", encoding="utf-8") as f:
            json.dump({"user_request": topic_with_spec}, f, ensure_ascii=False)
        
        # NEW: detect vertical and enhance queries (like discovery_search.py)
        vertical, det = get_vertical_for_request(topic_with_spec)
        if vertical:
            print(f"[vertical] {vertical.name} conf={det.confidence:.2f} reason={det.reason}")
        else:
            print("[vertical] none")
        
        base_queries = generate_queries_with_gemini(topic_with_spec, n=5)
        
        # Apply vertical enhancements (domain anchoring / exact name)
        if vertical:
            queries = vertical.enhance_search_queries(topic_with_spec, base_queries)
            print(f"[API] Vertical-enhanced queries: {len(queries)} queries")
        else:
            queries = base_queries
        
        raw_results_path = OUTPUT_DIR / "search_results_raw.ndjson"
        call_google_search_save(queries, output_path=str(raw_results_path), results_per_query=10)
        stage_times["query_generation_and_search"] = time.time() - step_start
        print(f"[TIMING] Query generation + search: {stage_times['query_generation_and_search']:.2f}s")
        
        # Step 2: Classify search results (already filters by confidence >= 0.95)
        step_start = time.time()
        classified_results_path = OUTPUT_DIR / "search_results_classified.ndjson"
        # Build user_request for classification (use topic_with_spec)
        user_request_for_classify = topic_with_spec
        classify_with_llm(
            raw_path=str(raw_results_path),
            output_path=str(classified_results_path),
            user_request=user_request_for_classify,
            batch_size=20,  # Larger batches = fewer API calls
            max_workers=5  # More parallel workers for classification
        )
        stage_times["classification"] = time.time() - step_start
        print(f"[TIMING] Classification: {stage_times['classification']:.2f}s")
        
        # Step 3: Check if we have any classified results
        # Note: classify_with_llm already filters by confidence >= 0.95 and KEEP_LABELS
        # So search_results_classified.ndjson contains only filtered results (like terminal workflow)
        if not classified_results_path.exists():
            return ScrapeResponse(
                results=[],
                message="No classified results found. Classification may have failed.",
                total_available_links=0,
                scraped_count=0,
                has_more=False
            )
        
        # Count total available links for reporting
        total_available = 0
        with open(classified_results_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    total_available += 1
        
        if total_available == 0:
            return ScrapeResponse(
                results=[],
                message="No results found with confidence >= 0.95 after classification.",
                total_available_links=0,
                scraped_count=0,
                has_more=False
            )
        
        # Step 4: Build user_request for scraping (use topic directly, like terminal)
        # Match terminal workflow: pass the full topic as user_request
        user_request = request.topic if request.topic else "Extract a general profile of each entity."
        print(f"[API] Received topic: {request.topic}")
        print(f"[API] Using user_request: {user_request}")
        
        # Modify PARSER_INSTRUCTIONS if data_specification provided (but don't duplicate topic)
        custom_instructions = None
        if request.data_specification and request.data_specification != request.topic:
            custom_instructions = PARSER_INSTRUCTIONS + f"\n\nIMPORTANT: The user specifically wants to extract: {request.data_specification}. Make sure to prioritize and extract this information prominently. If this information is not found on the page, set the relevant field(s) to null but ensure you thoroughly search for it."
        
        # Step 5: Scrape automatically from search_results_classified.ndjson (like terminal)
        # Use classified file directly instead of creating chosen_seeds.ndjson
        step_start = time.time()
        output_path = OUTPUT_DIR / "discovered_sites.ndjson"
        print(f"[API] Output will be written to: {output_path}")
        # Ensure output file is cleared before scraping (in case of previous runs)
        if output_path.exists():
            output_path.unlink()
            print(f"[API] Cleared existing output file")
        llm_scrape_from_seeds(
            seeds_path=str(classified_results_path),  # Read directly from classified file (like terminal)
            output_path=str(output_path),
            delay_seconds=0.0,  # No delay needed with parallel processing
            user_request=user_request,
            custom_parser_instructions=custom_instructions,
            max_workers=10,  # Parallel HTML fetching
            llm_workers=10  # More parallel LLM workers for faster processing
        )
        stage_times["scraping"] = time.time() - step_start
        print(f"[TIMING] Scraping: {stage_times['scraping']:.2f}s")
        
        # Load and return results
        step_start = time.time()
        results = []
        if output_path.exists():
            with open(output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        results.append(json.loads(line))
        stage_times["loading_results"] = time.time() - step_start
        
        total_time = time.time() - start_time
        stage_times["total"] = total_time
        print(f"[TIMING] Loading results: {stage_times['loading_results']:.2f}s")
        print(f"[TIMING] TOTAL API TIME: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        
        return ScrapeResponse(
            results=results,
            message=f"Scraped {len(results)} URLs (confidence >= 0.95). {total_available} total links were available. Processing time: {total_time:.1f}s",
            total_available_links=total_available,
            scraped_count=len(results),
            has_more=False  # All filtered results are scraped in one go (like terminal)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scraper/scrape-more", response_model=ScrapeResponse)
def scrape_more(request: ScrapeRequest):
    """Scrape the next batch of links (next 10) from remaining candidates"""
    try:
        # Validate topic is provided
        if not request.topic:
            raise HTTPException(status_code=400, detail="Topic is required")
        
        from llm_scrape_from_seeds import llm_scrape_from_seeds, PARSER_INSTRUCTIONS
        
        # Load all candidates
        all_candidates_path = OUTPUT_DIR / "all_candidates.ndjson"
        if not all_candidates_path.exists():
            raise HTTPException(status_code=404, detail="No candidates found. Please run a search first.")
        
        # Load already scraped URLs to avoid duplicates
        discovered_sites_path = OUTPUT_DIR / "discovered_sites.ndjson"
        scraped_urls = set()
        if discovered_sites_path.exists():
            with open(discovered_sites_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        result = json.loads(line)
                        url = result.get("url", "")
                        if url:
                            scraped_urls.add(url.rstrip('/').lower())
        
        # Load all candidates and filter out already scraped ones
        all_candidates = []
        with open(all_candidates_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    candidate = json.loads(line)
                    normalized_url = candidate.get("url", "").rstrip('/').lower()
                    if normalized_url not in scraped_urls:
                        all_candidates.append(candidate)
        
        if len(all_candidates) == 0:
            return ScrapeResponse(
                results=[],
                message="No more links to scrape. All available links have been scraped.",
                total_available_links=0,
                scraped_count=0,
                has_more=False
            )
        
        # Sort and take next 5
        all_candidates.sort(key=lambda x: (-x.get("confidence", 0.0), x.get("rank", 999)))
        next_batch = all_candidates[:5]
        
        # Create seeds file for this batch
        seeds_path = OUTPUT_DIR / "chosen_seeds.ndjson"
        with open(seeds_path, 'w', encoding='utf-8') as f:
            for candidate in next_batch:
                seed = {
                    "url": candidate["url"],
                    "label": candidate.get("label", "highly_relevant"),
                    "title": candidate.get("title", candidate["url"]),
                    "source_query": candidate.get("source_query", "auto_selected")
                }
                f.write(json.dumps(seed, ensure_ascii=False) + '\n')
        
        # Build user_request for scraping (use topic directly, like terminal)
        user_request = request.topic if request.topic else "Extract a general profile of each entity."
        
        # Modify PARSER_INSTRUCTIONS if data_specification provided (but don't duplicate topic)
        custom_instructions = None
        if request.data_specification and request.data_specification != request.topic:
            custom_instructions = PARSER_INSTRUCTIONS + f"\n\nIMPORTANT: The user specifically wants to extract: {request.data_specification}. Make sure to prioritize and extract this information prominently. If this information is not found on the page, set the relevant field(s) to null but ensure you thoroughly search for it."
        
        # Scrape this batch (append to existing file)
        temp_output_path = OUTPUT_DIR / "discovered_sites_temp.ndjson"
        llm_scrape_from_seeds(
            seeds_path=str(seeds_path),
            output_path=str(temp_output_path),
            delay_seconds=0.0,  # No delay needed with parallel processing
            user_request=user_request,
            custom_parser_instructions=custom_instructions,
            max_workers=10,  # Parallel HTML fetching
            llm_workers=10  # More parallel LLM workers for faster processing
        )
        
        # Append new results to existing discovered_sites.ndjson
        new_results = []
        if temp_output_path.exists():
            with open(temp_output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        new_results.append(json.loads(line))
            
            # Append to main file
            with open(discovered_sites_path, 'a', encoding='utf-8') as f:
                for result in new_results:
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
            
            # Clean up temp file
            temp_output_path.unlink()
        
        # Calculate remaining
        remaining_count = len(all_candidates) - len(next_batch)
        
        return ScrapeResponse(
            results=new_results,
            message=f"Scraped {len(next_batch)} more URLs. {remaining_count} links remaining.",
            total_available_links=len(all_candidates),
            scraped_count=len(new_results),
            has_more=(remaining_count > 0)
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Auto-generate routes for all tables
@app.on_event("startup")
async def startup_event():
    """Generate API routes automatically on startup with fresh schema introspection"""
    # DISABLED: Auto-generation disabled per user request
    print("ℹ️  Auto-generation of API routes is disabled")
    return
    
    db = None
    try:
        # Try to connect to database
        print("🔄 Attempting to connect to database...")
        engine = get_engine()
        
        # Test connection first
        try:
            engine.dispose()
            db = next(get_db())
            # Test query
            db.execute(text("SELECT 1"))
            print("   ✅ Database connection successful")
        except Exception as db_error:
            print(f"   ⚠️  Database not available: {db_error}")
            print("   ℹ️  App will run in scraper-only mode (database endpoints disabled)")
            return  # Exit early, scraper endpoints will still work
        
        # Ensure schema migrations are applied (e.g., extracted_at columns)
        # This ensures new columns added via migration files are present
        try:
            print("🔄 Checking and applying schema migrations...")
            # Run migration to add extracted_at columns if they don't exist
            # This is safe because it uses IF NOT EXISTS
            migration_sql = """
            ALTER TABLE core.publishers ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ DEFAULT now();
            ALTER TABLE core.magazines ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ DEFAULT now();
            ALTER TABLE core.agents ADD COLUMN IF NOT EXISTS extracted_at TIMESTAMPTZ DEFAULT now();
            """
            db.execute(text(migration_sql))
            db.commit()
            print("   ✅ Schema migrations applied")
        except Exception as e:
            print(f"   ⚠️  Migration check failed (may already be applied): {e}")
            db.rollback()
        
        print("🔄 Introspecting database schema...")
        # Generate routers for all tables (this will introspect fresh schema)
        auto_routers = auto_generate_all_routers(db)
        
        # Include auto-generated routers
        for router in auto_routers:
            app.include_router(router)
        
        print(f"✅ Auto-generated {len(auto_routers)} API routers")
        for router in auto_routers:
            print(f"   - {router.prefix}")
        
    except Exception as e:
        import traceback
        print(f"⚠️  Warning: Auto-generation failed: {e}")
        print(f"   Full error: {traceback.format_exc()}")
        print("   ℹ️  App will run in scraper-only mode (database endpoints disabled)")
        # Fall back to manual routers only - scraper endpoints still work
    finally:
        # Always close the database session
        if db:
            try:
                db.close()
            except:
                pass