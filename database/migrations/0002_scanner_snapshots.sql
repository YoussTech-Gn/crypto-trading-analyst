-- Migration: 0002_scanner_snapshots
-- Scope: Milestone 2 (market scanner). Stores each scan with the exact inputs used
-- so the ranking can be recomputed and verified later.

CREATE TABLE IF NOT EXISTS scan_snapshots (
    snapshot_id VARCHAR(64) PRIMARY KEY,
    created_at_utc VARCHAR(64) NOT NULL,
    scanner_version VARCHAR(32) NOT NULL,
    params_json TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    evaluated_count INTEGER NOT NULL CHECK (evaluated_count >= 0),
    ranked_count INTEGER NOT NULL CHECK (ranked_count >= 0),
    shortlisted_count INTEGER NOT NULL CHECK (shortlisted_count >= 0),
    non_target_quote_skipped INTEGER NOT NULL DEFAULT 0 CHECK (non_target_quote_skipped >= 0)
);

CREATE INDEX IF NOT EXISTS idx_scan_snapshots_created
    ON scan_snapshots (created_at_utc DESC);

CREATE TABLE IF NOT EXISTS scan_rankings (
    snapshot_id VARCHAR(64) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('SHORTLISTED', 'RANKED_NOT_SHORTLISTED', 'EXCLUDED')),
    rank INTEGER CHECK (rank IS NULL OR rank > 0),
    quote_volume DOUBLE PRECISION,
    price_change_percent DOUBLE PRECISION,
    spread_bps DOUBLE PRECISION,
    exclusion_reasons_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (snapshot_id, symbol),
    FOREIGN KEY (snapshot_id) REFERENCES scan_snapshots (snapshot_id) ON DELETE CASCADE,
    CHECK ((status = 'EXCLUDED' AND rank IS NULL) OR (status <> 'EXCLUDED' AND rank IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_scan_rankings_snapshot_rank
    ON scan_rankings (snapshot_id, rank);
