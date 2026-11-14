-- Canonical Schema Snapshot (Milestone 1: Repository & Data Foundation)
-- Synchronized with database/migrations/0001_initial_foundation.sql

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at_utc VARCHAR(64) NOT NULL
);

CREATE TABLE IF NOT EXISTS symbols (
    symbol VARCHAR(32) PRIMARY KEY,
    base_asset VARCHAR(24) NOT NULL,
    quote_asset VARCHAR(24) NOT NULL,
    exchange_status VARCHAR(32) NOT NULL,
    is_spot_trading_allowed INTEGER NOT NULL CHECK (is_spot_trading_allowed IN (0, 1)),
    is_eligible INTEGER NOT NULL CHECK (is_eligible IN (0, 1)),
    exclusion_reasons_json TEXT NOT NULL DEFAULT '[]',
    evaluated_at_utc VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_symbols_eligible
    ON symbols (is_eligible, quote_asset);

CREATE TABLE IF NOT EXISTS candles (
    symbol VARCHAR(32) NOT NULL,
    timeframe VARCHAR(8) NOT NULL CHECK (timeframe IN ('1d', '4h')),
    open_time_ms BIGINT NOT NULL CHECK (open_time_ms > 0),
    close_time_ms BIGINT NOT NULL CHECK (close_time_ms > open_time_ms),
    open DOUBLE PRECISION NOT NULL CHECK (open > 0),
    high DOUBLE PRECISION NOT NULL CHECK (high > 0 AND high >= low AND high >= open AND high >= close),
    low DOUBLE PRECISION NOT NULL CHECK (low > 0 AND low <= open AND low <= close),
    close DOUBLE PRECISION NOT NULL CHECK (close > 0),
    volume DOUBLE PRECISION NOT NULL CHECK (volume >= 0),
    quote_volume DOUBLE PRECISION NOT NULL CHECK (quote_volume >= 0),
    trade_count BIGINT NOT NULL CHECK (trade_count >= 0),
    ingested_at_utc VARCHAR(64) NOT NULL,
    PRIMARY KEY (symbol, timeframe, open_time_ms),
    FOREIGN KEY (symbol) REFERENCES symbols (symbol) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_open
    ON candles (symbol, timeframe, open_time_ms DESC);

CREATE TABLE IF NOT EXISTS data_validation_runs (
    run_id VARCHAR(64) PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    timeframe VARCHAR(8) NOT NULL CHECK (timeframe IN ('1d', '4h')),
    evaluated_at_utc VARCHAR(64) NOT NULL,
    is_valid INTEGER NOT NULL CHECK (is_valid IN (0, 1)),
    analysis_allowed INTEGER NOT NULL CHECK (analysis_allowed IN (0, 1)),
    freshness_status VARCHAR(64) NOT NULL,
    closed_candle_count INTEGER NOT NULL CHECK (closed_candle_count >= 0),
    unfinished_candle_count INTEGER NOT NULL CHECK (unfinished_candle_count >= 0),
    required_min_closed_candles INTEGER NOT NULL CHECK (required_min_closed_candles > 0),
    max_close_delay_seconds INTEGER NOT NULL CHECK (max_close_delay_seconds > 0),
    expected_latest_closed_open_time_ms BIGINT NOT NULL,
    actual_latest_closed_open_time_ms BIGINT,
    close_delay_seconds DOUBLE PRECISION,
    issues_json TEXT NOT NULL DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_validation_runs_symbol_tf
    ON data_validation_runs (symbol, timeframe, evaluated_at_utc DESC);

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

ALTER TABLE scan_rankings ADD COLUMN category VARCHAR(32) NOT NULL DEFAULT 'CRYPTO';

-- Scope: Milestone 4 (paper signals). One row per symbol and 4H candle, SIGNAL or NO_TRADE with reasons.
-- Paper only. Nothing here places orders.

CREATE TABLE IF NOT EXISTS signal_decisions (
    signal_id VARCHAR(64) PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    decision VARCHAR(16) NOT NULL CHECK (decision IN ('SIGNAL', 'NO_TRADE')),
    created_at_utc VARCHAR(64) NOT NULL,
    setup_candle_open_time_ms BIGINT NOT NULL,
    signal_version VARCHAR(32) NOT NULL,
    analysis_version VARCHAR(32) NOT NULL DEFAULT '',
    entry_price DOUBLE PRECISION,
    stop_price DOUBLE PRECISION,
    target_price DOUBLE PRECISION,
    risk_reward DOUBLE PRECISION,
    signal_time_ms BIGINT,
    valid_until_ms BIGINT,
    reasons_json TEXT NOT NULL DEFAULT '[]',
    checks_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    params_json TEXT NOT NULL,
    CHECK (
        decision = 'NO_TRADE'
        OR (entry_price IS NOT NULL AND stop_price IS NOT NULL AND target_price IS NOT NULL
            AND stop_price < entry_price AND entry_price < target_price)
    )
);

CREATE INDEX IF NOT EXISTS idx_signal_decisions_created
    ON signal_decisions (created_at_utc DESC);

CREATE INDEX IF NOT EXISTS idx_signal_decisions_symbol
    ON signal_decisions (symbol, created_at_utc DESC);
