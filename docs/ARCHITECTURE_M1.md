# Architecture Overview (Milestone 1: Repository & Data Foundation)

## 1. System Boundary & Safety Guarantees

The AI Crypto Trading Analyst is structured as a modular monorepo with a strict API boundary between the **Next.js frontend** (`apps/web`) and the **Python FastAPI backend** (`apps/api`) backed by reusable domain packages (`packages/*`) and a relational persistence layer (`database/`).

### Enforced Safety Boundaries (Milestone 1)

1. **Public Market Data Only**: `BinancePublicClient` (`packages/market_data/client.py`) restricts requests to `/api/v3/*` public Spot endpoints (`/api/v3/exchangeInfo`, `/api/v3/klines`). No API key or secret fields exist in configuration or client constructors.
2. **Real Order Execution Disabled**: `ExecutionConfig` (`packages/config/settings.py`) validates `real_orders_enabled == False` at startup and raises `ConfigValidationError` if set to `True`.
3. **Closed-Candle Evaluation Only**: `TimeframesConfig` enforces `use_closed_candles == True`. `CandleValidator` (`packages/market_data/validator.py`) separates unfinished forming candles (`close_time_ms >= reference_time_ms`) from closed candles before any persistence or downstream analysis.
4. **Fail-Closed Data Integrity Gate**: `CandleValidationResult.require_valid_for_analysis()` raises `UnreliableMarketDataError` whenever data is empty, malformed, out-of-order, duplicated, missing internal bars, delayed beyond or within the candle-availability window, stale, or below minimum history depth (`200` 1D / `500` 4H closed candles).

## 2. Milestone 1 Component Responsibilities

| Component | Path | Responsibility |
| :--- | :--- | :--- |
| **Configuration Loader** | `packages/config/settings.py` | Loads and validates `config/default.yaml` + environment overrides via Pydantic v2. |
| **Binance Public Client** | `packages/market_data/client.py` | Retrieves Spot `exchangeInfo` and `1d`/`4h` `klines` with retry/backoff and rate-limit header tracking. |
| **Symbol Discovery** | `packages/market_data/discovery.py` | Filters active USDT Spot pairs and records every exclusion reason for non-eligible symbols. |
| **Candle Validator** | `packages/market_data/validator.py` | Separates unfinished candles and classifies `FRESH`, `DELAYED_CANDLE_AVAILABILITY`, `STALE_DATA`, `MISSING_CANDLES`, `DUPLICATE_CANDLES`, `OUT_OF_ORDER_TIMESTAMPS`, `MALFORMED_CANDLE_DATA`, and `INSUFFICIENT_HISTORY`. |
| **Persistence & Migrations** | `database/` & `packages/market_data/repository.py` | Applies versioned SQL migrations (`0001_initial_foundation.sql`) and idempotently persists symbols, closed candles, and validation audit runs across PostgreSQL and SQLite. |
| **Backend API** | `apps/api/main.py` | Exposes `/api/v1/health`, `/api/v1/config`, `/api/v1/symbols`, and `/api/v1/candles/{symbol}/{timeframe}`. |
| **Web Shell** | `apps/web/` | Responsive Next.js + TypeScript shell displaying system status and safety invariants. |
