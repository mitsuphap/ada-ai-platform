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
    title="Automated Data Intelligence for Publishing & Beyond",
    description="Self-generating REST API with automatic endpoint creation based on database schema",
    version="2.0.0"
)

# Add rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS: enable during dev; tighten origins later ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "*"],
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
    # Touch the DB so health reflects actual readiness
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
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
    tables = get_available_auto_tables(db)
    return {"tables": tables, "count": len(tables)}

# Scraper API endpoints
# Add scraper to path - handle both Docker (/app/scraper) and local dev (../scraper)
scraper_path = Path(__file__).parent / "scraper"  # Docker: scraper is sibling to main.py
if not scraper_path.exists():
    scraper_path = Path(__file__).parent.parent / "scraper"  # Local dev: scraper is sibling to backend
if scraper_path.exists():
    sys.path.insert(0, str(scraper_path))

# Request/Response models
class SearchRequest(BaseModel):
    topic: str
    data_specification: Optional[str] = None

class SearchResponse(BaseModel):
    queries: List[str]
    search_results: List[dict]
    message: str

class ScrapeRequest(BaseModel):
    urls: List[str]
    data_specification: Optional[str] = None

class ScrapeResponse(BaseModel):
    results: List[dict]
    message: str

@app.post("/scraper/generate-search", response_model=SearchResponse)
def generate_and_search(request: SearchRequest, http_request: Request):
    """Generate queries from topic and execute Google search"""
    try:
        from query_generator import generate_queries_with_gemini
        from Google_search import call_google_search_save
        
        # Generate queries - incorporate data_specification if provided
        if request.data_specification:
            topic_with_spec = f"{request.topic}. Focus on finding: {request.data_specification}"
        else:
            topic_with_spec = request.topic
        queries = generate_queries_with_gemini(topic_with_spec, n=5)
        
        # Create temporary file for search results
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ndjson', delete=False) as tmp:
            tmp_path = tmp.name
        
        # Execute search
        call_google_search_save(queries, output_path=tmp_path, results_per_query=10)
        
        # Load and return results
        results = []
        with open(tmp_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        
        # Clean up temp file
        os.unlink(tmp_path)
        
        return SearchResponse(
            queries=queries,
            search_results=results,
            message=f"Found {len(results)} search results"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scraper/scrape-urls", response_model=ScrapeResponse)
def scrape_selected_urls(request: ScrapeRequest, http_request: Request):
    """Scrape selected URLs with custom data specification"""
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
        
        # Modify PARSER_INSTRUCTIONS if data_specification provided
        custom_instructions = None
        if request.data_specification:
            custom_instructions = PARSER_INSTRUCTIONS + f"\n\nIMPORTANT: The user specifically wants to extract: {request.data_specification}. Make sure to prioritize and extract this information prominently. If this information is not found on the page, set the relevant field(s) to null but ensure you thoroughly search for it."
        
        # Scrape
        llm_scrape_from_seeds(
            seeds_path=seeds_path,
            output_path=output_path,
            delay_seconds=1.0,
            custom_parser_instructions=custom_instructions
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
            message=f"Successfully scraped {len(results)} entities"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Auto-generate routes for all tables
@app.on_event("startup")
async def startup_event():
    """Generate API routes automatically on startup with fresh schema introspection"""
    db = None
    try:
        # Force engine to dispose any cached connections to ensure fresh schema
        engine = get_engine()
        engine.dispose()
        
        # Get fresh database session
        db = next(get_db())
        
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
        # Fall back to manual routers only
    finally:
        # Always close the database session
        if db:
            try:
                db.close()
            except:
                pass