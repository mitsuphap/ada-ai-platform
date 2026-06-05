"""Shared pytest setup.

Several scraper/backend modules read API keys at import time and raise if they
are missing, so we set harmless dummy values here BEFORE any test module imports
them. No real network calls are made; the AI/search clients are always mocked.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("GOOGLE_CSE_API_KEY", "test-cse-key")
os.environ.setdefault("GOOGLE_CSE_CX", "test-cx")

BACKEND_DIR = Path(__file__).resolve().parent.parent
SCRAPER_DIR = BACKEND_DIR.parent / "scraper"

for p in (BACKEND_DIR, SCRAPER_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
