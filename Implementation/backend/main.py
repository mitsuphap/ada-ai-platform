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
from app import runs as runs_repo
from pydantic import BaseModel
from typing import List, Optional
import sys
from pathlib import Path
import tempfile
import os
import json
import logging
from contextlib import asynccontextmanager

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("ada")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Introspect the database on startup and register auto-generated CRUD routers.

    If the database is unavailable the app still boots in scraper-only mode so the
    /scraper/* endpoints keep working.
    """
    logger.info("Starting up: attempting database connection for auto-generated API...")
    db = None
    try:
        get_engine().dispose()
        db = next(get_db())
        db.execute(text("SELECT 1"))
        auto_routers = auto_generate_all_routers(db)
        for router in auto_routers:
            app.include_router(router)
        logger.info("Registered %d auto-generated API routers", len(auto_routers))
    except Exception as e:
        logger.warning("Database/auto-API unavailable (%s); running in scraper-only mode", e)
    finally:
        if db:
            db.close()
    yield


app = FastAPI(
    title="Ada Automated Data Intelligence",
    description="Self-generating REST API with automatic endpoint creation based on database schema",
    version="2.0.0",
    lifespan=lifespan,
)

# Add rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS ---
# Origins are read from CORS_ALLOW_ORIGINS (comma-separated). Falls back to local
# dev origins so the app still works out of the box. Avoid the insecure "*" default.
_cors_env = os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000,http://localhost:5173")
ALLOWED_ORIGINS = [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
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
    run_id: Optional[int] = None

class LegacyScrapeRequest(BaseModel):
    urls: List[str]
    topic: Optional[str] = None
    data_specification: Optional[str] = None

class ScrapeResponse(BaseModel):
    results: List[dict]
    message: str
    run_id: Optional[int] = None
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
    logger.info("Added scraper path to sys.path: %s", scraper_path)
else:
    logger.warning("Scraper path not found near %s", Path(__file__).parent)

# Output directory - mounted at /data in Docker, or use scraper/output locally
OUTPUT_DIR = Path("/data") if Path("/data").exists() else Path(__file__).parent.parent / "scraper" / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_working_dir(run_id: int) -> Path:
    """Per-run scratch directory for intermediate ndjson files.

    Isolating intermediate files per run prevents concurrent requests from
    overwriting each other's shared files (the previous behaviour).
    """
    d = OUTPUT_DIR / "runs" / str(run_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _build_custom_instructions(request: "ScrapeRequest", base_instructions: str) -> Optional[str]:
    """Augment parser instructions when a distinct data_specification is given."""
    if request.data_specification and request.data_specification != request.topic:
        return (
            base_instructions
            + f"\n\nIMPORTANT: The user specifically wants to extract: {request.data_specification}. "
            "Make sure to prioritize and extract this information prominently. If this information is "
            "not found on the page, set the relevant field(s) to null but ensure you thoroughly search for it."
        )
    return None


def _load_ndjson_results(path: Path) -> List[dict]:
    """Read an ndjson file into a list of dicts (empty list if missing)."""
    results: List[dict] = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
    return results

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
        
        # Detect vertical and enhance queries
        vertical, det = get_vertical_for_request(topic_with_spec)
        if vertical:
            logger.info("Vertical %s (conf=%.2f)", vertical.name, det.confidence)

        base_queries = generate_queries_with_gemini(topic_with_spec, n=5)
        queries = vertical.enhance_search_queries(topic_with_spec, base_queries) if vertical else base_queries
        
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
def search_and_scrape_auto(request: ScrapeRequest, db: Session = Depends(get_db)):
    """Complete automated flow: Search -> Classify -> Filter (confidence >= 0.95) -> Auto-scrape.

    Each call is tracked as a row in core.runs; intermediate ndjson files live in a
    per-run directory (so concurrent requests don't collide), and final results are
    persisted to core.results keyed by run_id.
    """
    import time

    if not request.topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    if request.data_specification:
        topic_with_spec = f"{request.topic}. Focus on finding: {request.data_specification}"
    else:
        topic_with_spec = request.topic

    run_id = runs_repo.create_run(db, topic_with_spec)
    work_dir = run_working_dir(run_id)
    start_time = time.time()

    try:
        from query_generator import generate_queries_with_gemini
        from Google_search import call_google_search_save
        from classify_search_results import classify_with_llm
        from llm_scrape_from_seeds import llm_scrape_from_seeds, PARSER_INSTRUCTIONS
        from verticals import get_vertical_for_request

        # Step 1: Generate queries and search (within this run's working dir)
        with open(work_dir / "run_context.json", "w", encoding="utf-8") as f:
            json.dump({"user_request": topic_with_spec}, f, ensure_ascii=False)

        vertical, det = get_vertical_for_request(topic_with_spec)
        if vertical:
            logger.info("Vertical %s (conf=%.2f) for run %d", vertical.name, det.confidence, run_id)

        base_queries = generate_queries_with_gemini(topic_with_spec, n=5)
        queries = vertical.enhance_search_queries(topic_with_spec, base_queries) if vertical else base_queries

        raw_results_path = work_dir / "search_results_raw.ndjson"
        call_google_search_save(queries, output_path=str(raw_results_path), results_per_query=10)

        # Step 2: Classify (filters by confidence >= 0.95 + KEEP_LABELS)
        classified_results_path = work_dir / "search_results_classified.ndjson"
        classify_with_llm(
            raw_path=str(raw_results_path),
            output_path=str(classified_results_path),
            user_request=topic_with_spec,
            batch_size=20,
            max_workers=5,
        )

        if not classified_results_path.exists():
            runs_repo.update_run_status(db, run_id, "done")
            return ScrapeResponse(
                results=[], run_id=run_id,
                message="No classified results found. Classification may have failed.",
                total_available_links=0, scraped_count=0, has_more=False,
            )

        total_available = sum(
            1 for line in classified_results_path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
        if total_available == 0:
            runs_repo.update_run_status(db, run_id, "done")
            return ScrapeResponse(
                results=[], run_id=run_id,
                message="No results found with confidence >= 0.95 after classification.",
                total_available_links=0, scraped_count=0, has_more=False,
            )

        # Step 3: Scrape directly from the classified file
        user_request = request.topic or "Extract a general profile of each entity."
        custom_instructions = _build_custom_instructions(request, PARSER_INSTRUCTIONS)

        output_path = work_dir / "discovered_sites.ndjson"
        llm_scrape_from_seeds(
            seeds_path=str(classified_results_path),
            output_path=str(output_path),
            delay_seconds=0.0,
            user_request=user_request,
            custom_parser_instructions=custom_instructions,
            max_workers=10,
            llm_workers=10,
        )

        results = _load_ndjson_results(output_path)

        # Persist results to the database and mark the run complete.
        runs_repo.save_results(db, run_id, results)
        runs_repo.update_run_status(db, run_id, "done")

        total_time = time.time() - start_time
        logger.info("Run %d finished in %.1fs (%d results)", run_id, total_time, len(results))

        return ScrapeResponse(
            results=results,
            run_id=run_id,
            message=f"Scraped {len(results)} URLs (confidence >= 0.95). {total_available} total links were available. Processing time: {total_time:.1f}s",
            total_available_links=total_available,
            scraped_count=len(results),
            has_more=False,
        )
    except HTTPException:
        runs_repo.update_run_status(db, run_id, "error", "request failed")
        raise
    except Exception as e:
        runs_repo.update_run_status(db, run_id, "error", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scraper/scrape-more", response_model=ScrapeResponse)
def scrape_more(request: ScrapeRequest, db: Session = Depends(get_db)):
    """Scrape the next batch of candidates for an existing run, skipping already-scraped URLs."""
    if not request.run_id:
        raise HTTPException(status_code=400, detail="run_id is required")
    if not request.topic:
        raise HTTPException(status_code=400, detail="Topic is required")

    run_id = request.run_id
    work_dir = run_working_dir(run_id)
    classified_results_path = work_dir / "search_results_classified.ndjson"
    if not classified_results_path.exists():
        raise HTTPException(status_code=404, detail="No candidates found for this run.")

    try:
        from llm_scrape_from_seeds import llm_scrape_from_seeds, PARSER_INSTRUCTIONS

        # URLs already persisted for this run, to avoid re-scraping.
        scraped_urls = {
            (r.get("url") or "").rstrip("/").lower()
            for r in runs_repo.get_results(db, run_id)
            if r.get("url")
        }

        candidates = [
            c for c in _load_ndjson_results(classified_results_path)
            if (c.get("url", "").rstrip("/").lower()) not in scraped_urls
        ]
        if not candidates:
            return ScrapeResponse(
                results=[], run_id=run_id,
                message="No more links to scrape. All available links have been scraped.",
                total_available_links=0, scraped_count=0, has_more=False,
            )

        candidates.sort(key=lambda x: (-x.get("confidence", 0.0), x.get("rank", 999)))
        next_batch = candidates[:5]

        seeds_path = work_dir / "chosen_seeds.ndjson"
        with open(seeds_path, "w", encoding="utf-8") as f:
            for candidate in next_batch:
                f.write(json.dumps({
                    "url": candidate["url"],
                    "label": candidate.get("label", "highly_relevant"),
                    "title": candidate.get("title", candidate["url"]),
                    "source_query": candidate.get("source_query", "auto_selected"),
                }, ensure_ascii=False) + "\n")

        user_request = request.topic or "Extract a general profile of each entity."
        custom_instructions = _build_custom_instructions(request, PARSER_INSTRUCTIONS)

        batch_output_path = work_dir / "discovered_sites_more.ndjson"
        llm_scrape_from_seeds(
            seeds_path=str(seeds_path),
            output_path=str(batch_output_path),
            delay_seconds=0.0,
            user_request=user_request,
            custom_parser_instructions=custom_instructions,
            max_workers=10,
            llm_workers=10,
        )

        new_results = _load_ndjson_results(batch_output_path)
        runs_repo.save_results(db, run_id, new_results)

        remaining_count = len(candidates) - len(next_batch)
        return ScrapeResponse(
            results=new_results,
            run_id=run_id,
            message=f"Scraped {len(next_batch)} more URLs. {remaining_count} links remaining.",
            total_available_links=len(candidates),
            scraped_count=len(new_results),
            has_more=(remaining_count > 0),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/scraper/runs/{run_id}")
def get_run_results(run_id: int, db: Session = Depends(get_db)):
    """Fetch persisted results for a previous run."""
    try:
        results = runs_repo.get_results(db, run_id)
        return {"run_id": run_id, "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
