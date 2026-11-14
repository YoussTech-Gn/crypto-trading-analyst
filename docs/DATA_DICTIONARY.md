# Data Dictionary & Schema Roadmap

Per Clarification #7, this document explicitly reconciles the tables **implemented in Milestone 1** versus the tables **deferred to Milestones 2–6**.

---

## 1. Tables Implemented in Milestone 1 (`0001_initial_foundation.sql`)

### 1.1 `schema_migrations`
Tracks applied SQL schema migrations in lexical order.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `version` | `VARCHAR(64)` | `PRIMARY KEY` | Migration stem (e.g., `0001_initial_foundation`). |
| `description` | `TEXT` | `NOT NULL` | Human-readable migration description. |
| `applied_at_utc` | `VARCHAR(64)` | `NOT NULL` | ISO-8601 UTC timestamp when the migration was applied. |

### 1.2 `symbols`
Stores all evaluated Binance exchange symbols and their eligibility/exclusion audit trail.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `symbol` | `VARCHAR(32)` | `PRIMARY KEY` | Trading pair ticker (e.g., `BTCUSDT`). |
| `base_asset` | `VARCHAR(24)` | `NOT NULL` | Base asset ticker (e.g., `BTC`). |
| `quote_asset` | `VARCHAR(24)` | `NOT NULL` | Quote asset ticker (e.g., `USDT`). |
| `exchange_status` | `VARCHAR(32)` | `NOT NULL` | Binance status (`TRADING`, `BREAK`, `HALT`, etc.). |
| `is_spot_trading_allowed` | `INTEGER` | `NOT NULL CHECK IN (0, 1)` | Boolean flag (`1` = true, `0` = false). |
| `is_eligible` | `INTEGER` | `NOT NULL CHECK IN (0, 1)` | `1` if all discovery gates pass, `0` if excluded. |
| `exclusion_reasons_json` | `TEXT` | `NOT NULL DEFAULT '[]'` | JSON array of explicit exclusion reason codes. |
| `evaluated_at_utc` | `VARCHAR(64)` | `NOT NULL` | ISO-8601 UTC timestamp of evaluation. |

### 1.3 `candles`
Stores validated, **closed** historical `1d` and `4h` candles. Unfinished candles are never persisted here.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `symbol` | `VARCHAR(32)` | `PK, FK -> symbols(symbol)` | Trading pair ticker. |
| `timeframe` | `VARCHAR(8)` | `PK, CHECK IN ('1d', '4h')` | Candle interval (`1d` or `4h`). |
| `open_time_ms` | `BIGINT` | `PK, CHECK (> 0)` | UTC candle open timestamp in epoch milliseconds. |
| `close_time_ms` | `BIGINT` | `NOT NULL CHECK (> open_time_ms)` | UTC candle close timestamp in epoch milliseconds. |
| `open` | `DOUBLE PRECISION` | `NOT NULL CHECK (> 0)` | Opening price. |
| `high` | `DOUBLE PRECISION` | `NOT NULL CHECK (>= low, open, close)` | Highest price during interval. |
| `low` | `DOUBLE PRECISION` | `NOT NULL CHECK (<= open, close)` | Lowest price during interval. |
| `close` | `DOUBLE PRECISION` | `NOT NULL CHECK (> 0)` | Closing price. |
| `volume` | `DOUBLE PRECISION` | `NOT NULL CHECK (>= 0)` | Base asset volume. |
| `quote_volume` | `DOUBLE PRECISION` | `NOT NULL CHECK (>= 0)` | Quote asset (USDT) volume. |
| `trade_count` | `BIGINT` | `NOT NULL CHECK (>= 0)` | Number of trades in candle interval. |
| `ingested_at_utc` | `VARCHAR(64)` | `NOT NULL` | ISO-8601 UTC timestamp when row was upserted. |

### 1.4 `data_validation_runs`
Audit table recording every validation run executed by `CandleValidator`.

| Column | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `run_id` | `VARCHAR(64)` | `PRIMARY KEY` | UUID of the validation run. |
| `symbol` | `VARCHAR(32)` | `NOT NULL` | Validated symbol. |
| `timeframe` | `VARCHAR(8)` | `NOT NULL CHECK IN ('1d', '4h')` | Validated timeframe (`1d` or `4h`). |
| `evaluated_at_utc` | `VARCHAR(64)` | `NOT NULL` | Reference UTC timestamp used for validation. |
| `is_valid` | `INTEGER` | `NOT NULL CHECK IN (0, 1)` | `1` if valid, `0` otherwise. |
| `analysis_allowed` | `INTEGER` | `NOT NULL CHECK IN (0, 1)` | `1` if downstream analysis is permitted, `0` if blocked. |
| `freshness_status` | `VARCHAR(64)` | `NOT NULL` | Enum value from `DataFreshnessStatus`. |
| `closed_candle_count` | `INTEGER` | `NOT NULL CHECK (>= 0)` | Count of closed candles in series. |
| `unfinished_candle_count` | `INTEGER` | `NOT NULL CHECK (>= 0)` | Count of unfinished forming candles separated. |
| `required_min_closed_candles` | `INTEGER` | `NOT NULL CHECK (> 0)` | Configured minimum closed candle requirement. |
| `max_close_delay_seconds` | `INTEGER` | `NOT NULL CHECK (> 0)` | Configured maximum delay after expected close (default 300s). |
| `expected_latest_closed_open_time_ms` | `BIGINT` | `NOT NULL` | Expected open timestamp of most recently completed UTC bar. |
| `actual_latest_closed_open_time_ms` | `BIGINT` | `NULL` | Actual open timestamp of latest closed bar in dataset. |
| `close_delay_seconds` | `DOUBLE PRECISION` | `NULL` | Measured delay in seconds behind expected close boundary. |
| `issues_json` | `TEXT` | `NOT NULL DEFAULT '[]'` | JSON array of structured `CandleValidationIssue` objects. |

---

## 2. Tables Deferred to Future Milestones

To honor Section 10 of `PROJECT_SPEC.md` ("Do not create empty modules for every directory on day one. Introduce components as their phase begins"), the following tables are intentionally deferred:

* **Milestone 2 (Market Scanner)**:
  * `scan_snapshots`: Stores timestamped 24-hour market scan metadata and configuration inputs.
  * `scan_rankings`: Stores per-symbol 24h quote volume, percentage change, spread, relative volume, and shortlist rank.
* **Milestone 3 (Analysis Engine)**:
  * `structure_events`: Stores confirmed 1D/4H swing highs/lows, HH/HL/LH/LL labels, BOS, and CHoCH events.
  * `liquidity_levels`: Stores reference liquidity pools and confirmed sweep events.
  * `fvg_zones`: Stores detected 3-candle Fair Value Gaps, boundaries, and mitigation/invalidation timestamps.
* **Milestone 4 (Strategy & Signal Engine)**:
  * `strategy_versions`: Stores versioned strategy parameter sets (`baseline-1.0`, etc.).
  * `signals`: Stores structured signal contracts (`WATCHLIST`, `PENDING_ENTRY`, `ACTIVE`, `EXPIRED`, `INVALIDATED`, `COMPLETED`, `NO_TRADE`).
* **Milestone 5 (Backtesting)**:
  * `backtest_runs` and `backtest_trades`: Stores historical simulation configurations, trade fills, fees/slippage, and performance metrics.
* **Milestone 6 (Paper Trading)**:
  * `paper_positions` and `paper_events`: Stores live-data simulated position lifecycles.

## Milestone 2 tables (migration 0002_scanner_snapshots)
* `scan_snapshots`: `snapshot_id`, `created_at_utc`, `scanner_version`, `params_json`, `inputs_json` (exact inputs used), counts, `non_target_quote_skipped`.
* `scan_rankings`: one row per evaluated symbol per snapshot: `status` (SHORTLISTED / RANKED_NOT_SHORTLISTED / EXCLUDED), `rank` (NULL only when EXCLUDED, enforced by CHECK), `quote_volume`, `price_change_percent`, `spread_bps`, `exclusion_reasons_json`.

## signal_decisions (migration 0004)
One row per symbol and 4H candle. decision is SIGNAL or NO_TRADE. A SIGNAL requires stop < entry < target (database CHECK). reasons_json, checks_json, evidence_json and params_json keep the explanation.
