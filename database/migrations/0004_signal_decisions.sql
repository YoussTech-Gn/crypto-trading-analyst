-- Migration: 0004_signal_decisions
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
