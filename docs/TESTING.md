# Testing Guide (Milestone 1)

## Test Categories

1. **`tests/unit/test_config_validation.py`**:
   * Verifies `config/default.yaml` loads with all provisional defaults.
   * Verifies fail-closed rejection when `execution.real_orders_enabled=True`, `timeframes.use_closed_candles=False`, invalid quote asset, invalid market type, negative thresholds, or unknown keys are supplied.
2. **`tests/unit/test_symbol_discovery.py`**:
   * Verifies active USDT Spot pairs are marked eligible.
   * Verifies non-USDT pairs, halted pairs, non-spot pairs, stablecoins (`USDCUSDT`, `FDUSDUSDT`), explicit leveraged tokens (`BTCUPUSDT`), and suffix-matched leveraged tokens (`SOLBULLUSDT`, `AVAXDOWNUSDT`) are excluded with exact recorded reasons.
   * Verifies short base tickers (e.g., `UPUSDT`) are not falsely excluded by suffix rules unless explicitly configured.
3. **`tests/unit/test_candle_validator.py`**:
   * Verifies separation of unfinished forming candles from closed candles.
   * Verifies `FRESH` status when `>=200` `1d` or `>=500` `4h` closed candles exist up to the latest completed UTC boundary.
   * Verifies `DELAYED_CANDLE_AVAILABILITY` when the newly closed UTC candle is missing within `max_close_delay_seconds` (e.g., 120s <= 300s) and confirms `analysis_allowed` is `False` (`require_valid_for_analysis()` raises `UnreliableMarketDataError`).
   * Verifies `STALE_DATA` when the newly closed UTC candle is missing after `max_close_delay_seconds` (e.g., 301s > 300s) or lags by multiple intervals.
   * Verifies detection of `MISSING_CANDLES` (internal sequence gaps), `DUPLICATE_CANDLES`, `OUT_OF_ORDER_TIMESTAMPS`, `MALFORMED_CANDLE_DATA` (OHLC envelope violations, negative volume, NaN/Inf, unaligned timestamps), and `INSUFFICIENT_HISTORY`.
4. **`tests/unit/test_binance_client.py`**:
   * Uses `httpx.MockTransport` to test `/api/v3/exchangeInfo` and `/api/v3/klines` parsing, HTTP 429 rate-limit backoff and `Retry-After` handling, HTTP 500 retry recovery, malformed payload rejection, and enforcement of `/api/v3/` public path boundaries.
5. **`tests/integration/test_repository_persistence.py`**:
   * Tests idempotent migrations (`0001_initial_foundation.sql`), symbol upserts, closed-candle upserts, DB-level `CHECK` constraint enforcement (rejecting `high < low` or invalid timeframes at the database level), validation run audit persistence, and PostgreSQL dialect SQL/parameter translation (`%s`) + mock PostgreSQL driver execution.
6. **`tests/integration/test_api_endpoints.py`**:
   * Tests FastAPI endpoints (`/api/v1/health`, `/api/v1/config`, `/api/v1/symbols`, `/api/v1/candles/{symbol}/{timeframe}`) against a migrated database instance.
   * Includes health-endpoint failure path (HTTP 503 when the database is unavailable) and database `ok` field.
7. **`tests/unit/test_symbol_discovery.py`** also covers empty permission metadata (`MISSING_SPOT_PERMISSION`, fail closed).

**Last verified run (2026-11-13):** `pytest -q` under Python 3.11.17 in an isolated virtualenv: 34 passed. PostgreSQL 18 (Neon branch): migration SQL, upsert and CHECK constraints verified as raw SQL; the Python adapter was not run against PostgreSQL.

**2026-11-14:** pytest 34 passed on Windows (Python 3.12.10); `python scripts/verify_postgres.py` against a Neon PostgreSQL 18 branch printed PASS (migrations idempotent, upsert, read-back, CHECK constraint rejection). Docker Compose PostgreSQL still unverified.

## Milestone 2 tests
* `tests/unit/test_scanner.py`: ranking order, 24h gain does not affect rank, every exclusion reason, shortlist cap, non-USDT skipped, replay reproducibility.
* `tests/unit/test_binance_tickers.py`: 24hr/bookTicker parsing, malformed entries dropped, non-list payload rejected.
* `tests/integration/test_scanner_persistence.py`: migration 0002, snapshot round trip + replay, CHECK constraint, scanner API (latest, filter, 404, 422).
* `scripts/verify_postgres.py` also saves, loads and replays a scanner snapshot on real PostgreSQL.
Last run (2026-11-14, Python 3.11 Linux): 47 passed. PostgreSQL run of 0002 pending the user's execution of the script.
