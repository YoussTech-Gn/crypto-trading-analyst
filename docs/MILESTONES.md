# AI Crypto Trading Analyst

Evidence-driven cryptocurrency market analysis and decision-support system for **Binance Spot (USDT pairs)**, focused on **LONG-only swing trading** across **1D** (market context) and **4H** (setup and entry) timeframes.

> **Safety Notice:** This system is an analysis and decision-support tool. It uses public market data only, never requests or stores exchange API keys or withdrawal permissions, and strictly forbids real-money order execution (`execution.real_orders_enabled: false`).

## Current Status: Milestone 1 — Repository & Data Foundation

Milestone 1 delivers the monorepo structure, strict startup configuration validation, Binance public Spot REST client, configurable symbol discovery with explicit exclusion tracking, deterministic 1D/4H candle series validation (separating unfinished candles and distinguishing delayed availability, stale data, missing gaps, duplicates, and insufficient history), and database migrations/persistence supporting PostgreSQL (production) and SQLite (fast automated testing).

No trading signals or strategy rules are implemented in Milestone 1 (deferred to Milestones 3 and 4 per `PROJECT_SPEC.md`).

## Repository Structure

```text
crypto-trading-analyst/
|-- README.md
|-- PROJECT_SPEC.md                  # Primary project specification & operating rules
|-- .env.example                     # Safe environment variable placeholders
|-- .gitignore
|-- pyproject.toml
|-- docker-compose.yml               # PostgreSQL 16 service definition
|-- config/
|   |-- default.yaml                 # Provisional Milestone 1 configuration defaults
|-- apps/
|   |-- api/
|   |   |-- __init__.py
|   |   |-- main.py                  # FastAPI read-only foundation endpoints
|   |-- web/
|       |-- package.json             # Next.js + TypeScript shell
|       |-- tsconfig.json
|       |-- next.config.mjs
|       |-- src/app/
|           |-- layout.tsx
|           |-- page.tsx
|-- packages/
|   |-- config/
|   |   |-- __init__.py
|   |   |-- settings.py              # Pydantic v2 config schema & safety validator
|   |-- market_data/
|       |-- __init__.py
|       |-- models.py                # Typed DTOs & fail-closed analysis guard
|       |-- client.py                # Public Binance Spot REST client (/api/v3/*)
|       |-- discovery.py             # Symbol eligibility & exclusion reason tracker
|       |-- validator.py             # 1D/4H candle integrity, delay & staleness validator
|       |-- repository.py            # Idempotent persistence for symbols, candles & runs
|-- database/
|   |-- __init__.py
|   |-- session.py                   # Dual-dialect PostgreSQL / SQLite connection adapter
|   |-- migrations/
|   |   |-- 0001_initial_foundation.sql
|   |   |-- runner.py
|   |-- schema/
|       |-- schema.sql
|-- docs/
|   |-- ARCHITECTURE.md
|   |-- DATA_DICTIONARY.md
|   |-- API.md
|   |-- TESTING.md
|   |-- DECISIONS.md
|-- tests/
    |-- unit/
    |   |-- test_config_validation.py
    |   |-- test_symbol_discovery.py
    |   |-- test_candle_validator.py
    |   |-- test_binance_client.py
    |-- integration/
        |-- test_repository_persistence.py
        |-- test_api_endpoints.py
```

## Milestone 2: Market scanner (built, awaiting verification)

```powershell
python scripts/run_scan.py                      # one scan of live public Binance data, saved to the database
uvicorn apps.api.main:app --reload              # API: /api/v1/scans/latest
cd apps/web; npm install; npm run dev           # page: http://localhost:3000/scanner
```
Ranking = 24h quote volume (see ADR-007). The scanner never produces trading signals.

## Verification status (Milestone 1)

| Item | Result |
| --- | --- |
| Automated tests (Python 3.11.17 Linux; Python 3.12.10 Windows) | 34 passed, 0 failed (both) |
| PostgreSQL 18 (Neon branch, migration SQL + upsert + CHECK constraints run as raw SQL) | Passed |
| Migration runner + `DatabaseConnection` + repository against real PostgreSQL (`scripts/verify_postgres.py`, Neon branch) | Passed (2026-11-14, run by the user) |
| Docker Compose PostgreSQL | **Not yet verified** (Docker unavailable) |

Milestone 1 is **recommended for approval**; it is approved only when the user accepts it. See `docs/DECISIONS.md` (ADR-006).

## Running Tests

```bash
python3.11 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

Alternative (no pytest):

```bash
# Using unittest (zero external test runner dependencies required):
python3 -m unittest discover -s tests -t . -v

# Or using pytest (when installed in your environment):
pytest
```

## Status
Milestones 1-5 built. Milestone 6 (strategy lab): 29 recipes in 5 families, managed exits, week-clustered confidence, portfolio combiner, pre-registered freeze and a one-shot alt gate (ADR-024..030). 200+ tests passing. First full run done (ADR-031): no recipe has an edge, the alt gate failed; the learning engine (ADR-034) found only a tiny signal. Now in live paper measurement (ADR-036): `python scripts/forward_journal.py scan` after each 4H close, `settle`, `decide`, `review`. Paper only, no real orders.

**One command for the whole research pass** (needs internet only for the first download; takes hours):

    python scripts/overnight.py

Read `reports/MORNING_REPORT.txt` afterwards. After an interruption run `python scripts/overnight.py --resume` (same data anchor).

## Decisions (read this first)
Every decision, the evidence behind it and the files it changed are in `docs/DECISIONS.md` (one page, with an index). Every future decision MUST be added there before the work is considered done.

## Milestone 3 - Analysis engine
Run on live public data (read-only): `python scripts/run_analysis.py BTCUSDT`
Definitions: `docs/ANALYSIS_DEFINITIONS.md`. Tests: `pytest` (78 passed on Linux 3.11).

## Milestone 4 - Paper signals
`python scripts/run_scan.py` then `python scripts/run_signals.py` (or pass symbols). API: `GET /api/v1/signals?decision=SIGNAL|NO_TRADE`.
Prints the SIGNAL list, a histogram of why symbols are NO_TRADE, and the symbols closest to a signal. Paper only.
- Run everything with one command: python scripts/run_all.py (writes reports/latest_run.txt).

## Milestone 5 - Backtest
`python scripts/run_backtest.py` (see docs/BACKTEST.md). Fewer than 30 trades is labelled INSUFFICIENT_SAMPLE.

Failures: every script writes reports/failure_<script>.txt (expected or unexpected, cause, advice).
