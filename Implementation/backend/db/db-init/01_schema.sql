-- ADA AI Platform - base schema
-- Runs automatically by the postgres image on first boot
-- (mounted at /docker-entrypoint-initdb.d via docker-compose).

CREATE SCHEMA IF NOT EXISTS core;

-- A single user request / pipeline execution.
CREATE TABLE IF NOT EXISTS core.runs (
    id          SERIAL PRIMARY KEY,
    prompt      TEXT        NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'pending',  -- pending | running | done | error
    error       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One structured entity extracted during a run.
CREATE TABLE IF NOT EXISTS core.results (
    id              SERIAL PRIMARY KEY,
    run_id          INTEGER     NOT NULL REFERENCES core.runs(id) ON DELETE CASCADE,
    url             TEXT,
    title           TEXT,
    scraped_status  TEXT,
    payload         JSONB,
    scraped_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_results_run_id ON core.results (run_id);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON core.runs (created_at DESC);
