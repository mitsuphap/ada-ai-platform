"""Persistence helpers for scraper runs and their extracted results.

Replaces the previous approach of writing shared ndjson files in a single
output directory (which caused concurrent requests to overwrite each other).
Each pipeline execution gets its own row in core.runs and its results in
core.results, keyed by run_id.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("ada.runs")


def create_run(db: Session, prompt: str) -> int:
    """Create a new run row and return its id."""
    row = db.execute(
        text(
            "INSERT INTO core.runs (prompt, status) "
            "VALUES (:prompt, 'running') RETURNING id"
        ),
        {"prompt": prompt},
    ).mappings().first()
    db.commit()
    return int(row["id"])


def update_run_status(db: Session, run_id: int, status: str, error: Optional[str] = None) -> None:
    db.execute(
        text(
            "UPDATE core.runs SET status = :status, error = :error, updated_at = now() "
            "WHERE id = :id"
        ),
        {"status": status, "error": error, "id": run_id},
    )
    db.commit()


def save_results(db: Session, run_id: int, results: List[Dict[str, Any]]) -> int:
    """Persist scraper result records for a run. Returns the number saved."""
    if not results:
        return 0

    rows = []
    for r in results:
        rows.append(
            {
                "run_id": run_id,
                "url": r.get("url"),
                "title": r.get("title"),
                "scraped_status": r.get("scraped_status"),
                "payload": json.dumps(r.get("llm_payload"), ensure_ascii=False)
                if r.get("llm_payload") is not None
                else None,
            }
        )

    db.execute(
        text(
            "INSERT INTO core.results (run_id, url, title, scraped_status, payload) "
            "VALUES (:run_id, :url, :title, :scraped_status, CAST(:payload AS JSONB))"
        ),
        rows,
    )
    db.commit()
    return len(rows)


def get_results(db: Session, run_id: int) -> List[Dict[str, Any]]:
    """Return persisted results for a run in the shape the frontend expects."""
    rows = db.execute(
        text(
            "SELECT url, title, scraped_status, payload, scraped_at "
            "FROM core.results WHERE run_id = :run_id ORDER BY id"
        ),
        {"run_id": run_id},
    ).mappings().all()

    results = []
    for row in rows:
        payload = row["payload"]
        # psycopg2 may return JSONB as dict already, or as str depending on config.
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (ValueError, TypeError):
                payload = None
        results.append(
            {
                "url": row["url"],
                "title": row["title"],
                "scraped_status": row["scraped_status"],
                "scraped_at": row["scraped_at"].isoformat() if row["scraped_at"] else None,
                "llm_payload": payload,
            }
        )
    return results
