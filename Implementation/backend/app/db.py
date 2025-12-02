import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

load_dotenv()

# Prefer DATABASE_URL (set by Fly.io postgres attach) if available
# Otherwise, construct from individual environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    PG_HOST = os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "db"))
    PG_PORT = os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))
    PG_DB   = os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "ada_db"))
    PG_USER = os.getenv("POSTGRES_USER", os.getenv("DB_USER", "ada"))
    PG_PASS = os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASS", "ada"))
    
    # Convert postgres:// to postgresql+psycopg2:// for SQLAlchemy
    DATABASE_URL = f"postgresql+psycopg2://{PG_USER}:{PG_PASS}@{PG_HOST}:{PG_PORT}/{PG_DB}"
else:
    # Convert postgres:// to postgresql+psycopg2:// for SQLAlchemy if needed
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)

# Create engine with connection pooling and retry settings
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Verify connections before using
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,  # Recycle connections after 1 hour
    connect_args={
        "connect_timeout": 10,  # 10 second connection timeout
        "options": "-c statement_timeout=30000"  # 30 second query timeout
    }
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_engine() -> Engine:
    return engine
