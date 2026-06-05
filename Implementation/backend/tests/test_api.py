"""Smoke tests for the FastAPI app. No database or network required."""
from fastapi.testclient import TestClient

import main

# Plain TestClient (no context manager) so the startup lifespan/DB connection
# is not exercised; these routes do not depend on the database.
client = TestClient(main.app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_root():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "docs" in resp.json()


def test_scraper_test_route():
    resp = client.get("/scraper/test")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Scraper routes are working"
