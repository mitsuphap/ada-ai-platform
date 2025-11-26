# main.py (updated)
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from app.db import get_engine, get_db
from app.auto_generator import auto_generate_all_routers, get_available_auto_tables

# Import your existing manual routers
from app.routers.publishers import router as publishers_router
from app.routers.admin import router as admin_router
from app.routers.metrics import router as metrics_router
from app.routers.agents import router as agents_router
from app.routers.magazines import router as magazines_router
from app.routers.genres import router as genres_router
from app.routers.search import router as search_router

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

# register manual routes
app.include_router(publishers_router) 
app.include_router(admin_router)
app.include_router(metrics_router)
app.include_router(agents_router)
app.include_router(magazines_router)
app.include_router(genres_router)
app.include_router(search_router)

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