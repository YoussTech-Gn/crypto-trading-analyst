-- Migration: 0001_initial_foundation
-- Target dialect: PostgreSQL 15+ (compatible with SQLite 3.35+ via migration runner)
-- Scope: Milestone 1 (Repository and Data Foundation) ONLY.
-- Tables implemented in Milestone 1:
--   1. schema_migrations       (tracks applied migration versions)
--   2. symbols                 (discovered exchange symbols & eligibility/exclusion audit)
--   3. candles                 (validated closed historical 1d and 4h candles)
--   4. data_validation_runs    (audit log of candle series integrity & staleness checks)
-- Deferred tables (documented in docs/DATA_DICTIONARY.md):
--   - Milestone 2: scan_snapshots, scan_rankings
--   - Milestone 3: structure_events, liquidity_levels, fvg_zones
--   - Milestone 4: strategy_versions, signals
--   - Milestone 5: backtest_runs, backtest_trades
--   - Milestone 6: paper_positions, paper_orders

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
