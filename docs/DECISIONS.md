# Decision Log (single page)

Every decision taken in this project is recorded here, in one place: WHAT was decided, WHY (the evidence found), the STATUS, and the FILES changed.
`PROJECT_SPEC.md` stays the primary specification. This file explains every choice made on top of it.

## The rule (applies to every future change)
Before a change is considered done, add an entry to this file. Never leave a decision only in chat or in code.
Use the next ADR number, keep it English, and use this template:

```text
## ADR-0NN: short title
* **Date**: YYYY-MM-DD
* **Status**: Accepted | Provisional | Rejected | Superseded by ADR-0MM | Open
* **Decision**: what we do now (and what we explicitly do NOT do)
* **Why / evidence**: the finding that led to it, with numbers and the report or file that shows them
* **Files**: every file created or changed, one line each reason if not obvious
* **Revisit when**: the condition that would reopen it (optional)
```
Rules: a rejected idea is logged too (so it is not retried blindly); a changed decision gets a new ADR and the old one is marked Superseded; numbers come from files in `reports/`, never from memory.

## Index
| ID | Decision | Status | Main files |
|---|---|---|---|
| ADR-001 | Dual-dialect persistence (PostgreSQL + SQLite tests) | Accepted | database/session.py, migrations/0001 |
| ADR-002 | Provisional config defaults and minimum history | Provisional | config/default.yaml |
| ADR-003 | Four-way candle freshness distinction | Accepted | market_data/validator.py |
| ADR-004 | Stablecoin and leveraged-token exclusions with reasons | Accepted | market_data/discovery.py |
| ADR-005 | Milestone 1 database scope | Accepted | docs/DATA_DICTIONARY.md |
| ADR-006 | Milestone 1 fail-closed fixes | Accepted | discovery.py, apps/api/main.py |
| ADR-007 | Scanner design (volume ranking, manual scans) | Accepted | packages/scanner/* |
| ADR-008 | Stablecoin list extended; tokenized stocks and gold stay | Accepted | config/default.yaml |
| ADR-009 | Asset categories (display only) | Accepted | scanner, migration 0003 |
| ADR-010 | Second live-scan review | Accepted | config/default.yaml |
| ADR-011 | Analysis engine and its corrections | Accepted (provisional) | packages/analysis, liquidity, fvg, ... |
| ADR-012 | Paper signal generator | Accepted (provisional) | packages/signals/* |
| ADR-013 | Backtest with 30-trade minimum | Accepted | packages/backtest/* |
| ADR-014 | Post-mortems, lessons, failure reports | Accepted | backtest/postmortem.py, reporting/failure.py |
| ADR-015 | Pre-registered hold-out rule for vetoes | Accepted | scripts/run_backtest.py |
| ADR-016 | Pattern memory across runs | Accepted | backtest/memory.py |
| ADR-017 | Strategy lab (recipes, scorecard, trial penalty) | Accepted (provisional) | packages/strategies/*, scripts/run_lab.py |
| ADR-018 | Working rules (paper only, no Arabic, agent reads reports, ...) | Accepted | reporting/failure.py, postmortem.py |
| ADR-019 | Target mode stays nearest; first_meeting_rr is a variant | Accepted | signals/generator.py |
| ADR-020 | Daily-trend filter stays (thin evidence) | Accepted | signals/generator.py |
| ADR-021 | Hold-out outcome: FVG veto rejected, volume/tight-stop advisory | Accepted, vetoes off | backtest/memory.py |
| ADR-022 | Truncated 4h candles tolerated with a skip rule | Accepted | backtest/engine.py, data.py |
| ADR-023 | Parallel backtest, progress, no partial reports | Accepted | scripts/run_backtest.py |
| ADR-024 | First lab run: findings and ranking fix | Accepted | strategies/scorecard.py, scripts/run_lab.py |
| ADR-025 | M6b: 11 single-part variants of fvg_only, exit management, week-clustered confidence | Accepted | backtest/engine.py, strategies/recipes.py, metrics.py |
| ADR-026 | `--basket alt` is a one-shot gate, used after the recipes are frozen | Accepted | scripts/run_lab.py |
| ADR-027 | M6b first run: no recipe passes; near-edge entry is the one real finding; exit family closed | Accepted | reports/lab_main.* (no code) |
| ADR-028 | M6c: 14 recipes from new families (trend breakout, EMA pullback, RSI dip, BTC regime filter, near-edge combos) | Accepted | packages/strategies/families.py, registry.py |
| ADR-029 | Pre-registered freeze rule, alt-gate verdict and portfolio combiner | Accepted | packages/strategies/freeze.py, portfolio.py |
| ADR-030 | Offline candle cache and the one-command overnight runner | Accepted | packages/backtest/cache.py, scripts/overnight.py |
| ADR-031 | First overnight run (29 recipes): no recipe passes, alt gate FAIL, the whole 4H long-only line closed for now | Accepted | reports/MORNING_REPORT.txt, knowledge/alt_gate.json |
| ADR-032 | H1 daily relative-strength rotation: passed the pre-registered rules, REJECTED by the robustness checks (2021-driven, not on alt) | Rejected | packages/strategies/rotation.py, scripts/run_rotation_study.py |
| ADR-033 | Goal changed to a learning/prediction engine (M7); Claude and Gemini work together through docs/COLLAB.md | Accepted | docs/COLLAB.md |
| ADR-034 | M7-FG1 OHLCV learner: REJECTED (AUC 0.513 main / 0.515 alt, top-decile trades still negative) | Rejected | packages/learning/, scripts/run_m7.py |
| ADR-035 | Automatic Gemini-Claude loop over docs/COLLAB.md, run on the owner's computer | Accepted | scripts/collab_loop.py |
| ADR-036 | Forward paper journal: 3 pre-registered recipes, live signals settled by the backtest rules, owner decisions measured | Accepted | packages/journal/, scripts/forward_journal.py |
| ADR-037 | Third owner decision 'absent'; no decision 4 hours after the candle close -> absent automatically, then frozen | Accepted | packages/journal/forward.py, scripts/forward_journal.py |
| ADR-038 | Scan backfills every missed closed 4H candle (max 7 days, never before 2026-11-14 12:00 UTC); older misses logged as coverage gaps | Accepted | packages/journal/forward.py, scripts/forward_journal.py |
| ADR-039 | Open-source hardening: security fixes, private journal excluded, contributor docs, CI | Accepted | docker-compose.yml, apps/api/main.py, .gitignore, README.md, CONTRIBUTING.md, SECURITY.md, .github/ |

## Open items and pending decisions
* M6a lab run on the main basket is done (ADR-024). `--basket alt` is run once, by the overnight runner, on the frozen recipes (ADR-029).
* M6b first run done (ADR-027). The user then asked for autonomous work (2026-11-14), so the next direction was chosen by the agent: new families (ADR-028).
* Enabling any veto (LOW_VOLUME, TIGHT_STOP) in config needs the user's approval and validation on unseen symbols.
* Next direction is open (see ADR-031, last paragraph). M6c (14 new recipes, portfolio combiner, freeze, alt gate) is built (ADR-028..030); first result in ADR-031. The alt gate is spent (knowledge/alt_gate.json).
* Lab results do not yet feed the pattern memory (planned).
* Full replay of stored signals needs a candle store (later).
* Docker Compose has not been verified. Sector categories (L1, DeFi, AI, meme) are not built: no data source or approved list.
* An offline copy of Binance's monthly kline archive (`data.binance.vision`) would make backtests exactly repeatable. Not decided.

---
## ADR-001: Dual-Dialect Persistence (PostgreSQL Production + SQLite Automated Tests)
* **Date**: 2026-11-13
* **Milestone**: Milestone 1
* **Context**: `PROJECT_SPEC.md` Section 2 specifies PostgreSQL for persistence, and Section 11 requires automated tests for the data client, validation, and migrations.
* **Decision**: Use standard SQL DDL (`database/migrations/0001_initial_foundation.sql`) with `ON CONFLICT (...) DO UPDATE` upserts and `CHECK` constraints supported by both PostgreSQL 15+ and SQLite 3.35+, wrapped in `DatabaseConnection` (`database/session.py`), which translates parameter placeholders (`?` for SQLite, `%s` for PostgreSQL DB-API 2.0 drivers) and enforces `PRAGMA foreign_keys = ON` in SQLite.
* **Why / evidence**: the spec asks for PostgreSQL but automated tests must run fast and offline. Verified later against Neon with `scripts/verify_postgres.py` (passed).
* **Files**: `database/migrations/0001_initial_foundation.sql`, `database/session.py`, `database/migrations/runner.py`, `scripts/verify_postgres.py`.

## ADR-002: Provisional Configuration Defaults & Minimum History Depth
* **Date**: 2026-11-13
* **Milestone**: Milestone 1
* **Context**: `PROJECT_SPEC.md` Section 12 marks several operational thresholds as `configurable`.
* **Decision**: Set provisional engineering defaults in `config/default.yaml` (explicitly marked as non-validated trading assumptions):
  * `min_closed_candles_1d: 200`
  * `min_closed_candles_4h: 500`
  * `max_close_delay_seconds: 300` (5 minutes)
  * `min_quote_volume_24h: 10,000,000` USDT
  * `minimum_reward_to_risk: 2.0`
  * `simulated_equity: 10,000` USDT
  * `risk_per_trade_percent: 1.0`
  * `max_open_positions: 3`
  * `max_spread_bps: 20.0`
* **Why / evidence**: the spec leaves these thresholds configurable and unvalidated, so they are labelled provisional rather than presented as tuned.
* **Files**: `config/default.yaml`, `packages/config/settings.py`.

## ADR-003: Four-Way Distinction Between Unfinished, Delayed, Missing, and Stale Candles
* **Date**: 2026-11-13
* **Milestone**: Milestone 1
* **Context**: Clarification #3 requires not allowing a full candle interval of delay before declaring data stale, using a configurable maximum delay after expected candle close (initially 5 minutes / 300s), and distinguishing unfinished candles, delayed candle availability, missing candles, and stale data.
* **Decision**: In `CandleValidator.validate()` (`packages/market_data/validator.py`):
  1. **Unfinished Candles**: Any candle with `close_time_ms >= reference_time_ms` is separated into `unfinished_candles` and excluded from `closed_candles`.
  2. **Delayed Candle Availability (`DELAYED_CANDLE_AVAILABILITY`)**: When the most recently completed UTC interval closed at `expected_latest_close_boundary_ms`, the bar for that just-completed interval is not yet in `closed_candles`, the immediately preceding bar IS present, and `0 <= (now_ms - expected_latest_close_boundary_ms)/1000 <= max_close_delay_seconds` (default 300s). Downstream analysis is blocked (`analysis_allowed = False`) until the bar arrives.
  3. **Stale Data (`STALE_DATA`)**: When the newly closed bar is still absent after `max_close_delay_seconds` (>300s past the expected UTC close boundary), or when the latest closed bar lags by more than one interval. Downstream analysis is blocked (`analysis_allowed = False`).
  4. **Missing Candles (`MISSING_CANDLES`)**: Internal sequence gaps between consecutive closed candles (`curr.open_time_ms - prev.open_time_ms > interval_ms`). Downstream analysis is blocked (`analysis_allowed = False`).
* **Files**: `packages/market_data/validator.py`, `tests/unit/test_candle_validator.py`.

## ADR-004: Configurable Stablecoin & Leveraged-Token Exclusions with Audit Reasons
* **Date**: 2026-11-13
* **Milestone**: Milestone 1
* **Context**: Clarification #5 requires configurable exclusions for stablecoins and leveraged tokens, recording the reason for every excluded symbol, and documenting any naming-pattern rule.
* **Decision**: `SymbolDiscoveryService` (`packages/market_data/discovery.py`) evaluates:
  1. Quote asset match (`NON_TARGET_QUOTE_ASSET:<quote>`).
  2. Exchange trading status (`EXCHANGE_STATUS_NOT_TRADING:<status>`).
  3. Spot trading permission flags (`SPOT_TRADING_NOT_ALLOWED`, `MISSING_SPOT_PERMISSION`).
  4. Manual exclusion list (`MANUALLY_EXCLUDED_ASSET`).
  5. Configurable stablecoin/fiat base asset list (`EXCLUDED_STABLECOIN_OR_FIAT_BASE:<base>`).
  6. Configurable explicit leveraged token list (`EXCLUDED_LEVERAGED_TOKEN_EXPLICIT:<base>`) plus a documented suffix rule (`EXCLUDED_LEVERAGED_TOKEN_SUFFIX:<suffix>`) that only matches configured suffixes (`UP`, `DOWN`, `BULL`, `BEAR`) when `len(base_asset) >= len(suffix) + 2` so 2–3 character symbols are not falsely matched. Every evaluated symbol is persisted with its full JSON list of exclusion reasons.
* **Files**: `packages/market_data/discovery.py`, `config/default.yaml`, `tests/unit/test_symbol_discovery.py`.

## ADR-005: Reconciled Milestone 1 Database Scope
* **Date**: 2026-11-13
* **Milestone**: Milestone 1
* **Context**: Clarification #7 requires reconciling the database schema with Milestone 1 scope and documenting deferred tables.
* **Decision**: Only `schema_migrations`, `symbols`, `candles`, and `data_validation_runs` are created in `0001_initial_foundation.sql`. Tables for scanner snapshots (`Milestone 2`), market structure/liquidity/FVG (`Milestone 3`), strategy versions/signals (`Milestone 4`), backtesting (`Milestone 5`), and paper trading (`Milestone 6`) are documented as deferred in `docs/DATA_DICTIONARY.md`.
* **Files**: `database/migrations/0001_initial_foundation.sql`, `database/schema/schema.sql`, `docs/DATA_DICTIONARY.md`.

## ADR-006: Milestone 1 Stabilization Fixes (fail-closed behaviour)
* **Date**: 2026-11-13
* **Milestone**: Milestone 1 (stabilization)
* **Decisions** (no strategy or risk threshold changed):
  1. **Missing Spot permission metadata is an exclusion.** `SymbolDiscoveryService` now excludes a symbol with `MISSING_SPOT_PERMISSION` when its permission list is empty, not only when it is non-empty without `SPOT`. Reason: absent data must never make a symbol eligible (fail closed).
  2. **Health endpoint checks the database.** `GET /api/v1/health` runs `SELECT 1`; on failure it returns HTTP 503 with `status: "unavailable"` instead of a false `ok`. Successful responses include `"database": "ok"`.
  3. **SQLite shared connection is thread-safe for the API.** `sqlite3.connect(..., check_same_thread=False)`: FastAPI runs sync endpoints in a worker threadpool. SQLite is for local tests only; PostgreSQL remains the target. A connection pool is deferred until a real concurrency need exists.
  4. **Packaging.** `pyproject.toml` now declares `[tool.setuptools.packages.find]` so `pip install -e ".[dev]"` works.
* **Files**: `packages/market_data/discovery.py`, `apps/api/main.py`, `database/session.py`, `pyproject.toml`, `tests/integration/test_api_endpoints.py`.

## ADR-007: Milestone 2 Scanner Design
* **Date**: 2026-11-14
* **Milestone**: Milestone 2
* **Decisions** (made by the agent under the user's instruction to decide; each is reversible by a new scanner version):
  1. **Ranking is by 24h quote volume only** (descending, ties by symbol). 24h percentage change is displayed but never affects rank or eligibility. No composite score, because PROJECT_SPEC.md lists the inputs without weights and no weights are invented.
  2. **Relative volume is deferred to Milestone 3**, when stored candles for shortlisted assets exist.
  3. **Scans are run manually** (`python scripts/run_scan.py`); scheduling comes with the worker.
  4. **New config value** `universe.max_ticker_age_seconds` (default 300, same value as the candle delay limit): a ticker whose `closeTime` differs from the scan time by more than this is excluded as `STALE_TICKER_DATA`.
  5. **Fail closed per symbol:** missing/invalid/stale ticker or book data, spread above `max_spread_bps`, or volume below `min_quote_volume_24h` excludes the symbol with an explicit reason. Entries with unparsable ticker fields are dropped by the client.
  6. **Reproducibility:** each snapshot stores the exact inputs (tickers, best bid/ask, symbol evaluations) and parameters; `MarketScanner.replay()` recomputes the ranking and must equal the stored one.
  7. Only symbols quoted in the configured quote asset (USDT) are ranked; others are counted in `non_target_quote_skipped`.
  8. Scanner version `scanner-1.0`. Changing any rule requires a new version and a new ADR.
* **Why / evidence**: the spec lists scanner inputs without weights; inventing weights would hide an assumption. Volume ranking is the only rule that needs no invented number.
* **Files**: `packages/scanner/scanner.py`, `packages/scanner/models.py`, `packages/scanner/repository.py`, `packages/market_data/client.py`, `database/migrations/0002_scanner_snapshots.sql`, `scripts/run_scan.py`, `tests/unit/test_scanner.py`, `tests/integration/test_scanner_persistence.py`.

## ADR-008: Stablecoin exclusion list extended after first live scan
* **Date**: 2026-11-14
* **Context**: The first live scan shortlisted USD1USDT, RLUSDUSDT and UUSDT, which are stablecoins and not swing-trade candidates.
* **Decision**: Added USD1, RLUSD, U, USDS, PYUSD to `excluded_stablecoin_base_assets` (config and schema default). No strategy or risk threshold changed.
* **Open question (user decision)**: tokenized stocks/ETFs (e.g. NVDAB, SPCXB, SOXLB, SNDKB, GOOGLB) and gold-backed XAUT also appear in the shortlist. They are not excluded yet.
* **User decision (closed)**: tokenized stocks and gold-backed assets STAY in the scanner. Only stablecoins are excluded.
* **Files**: `config/default.yaml`, `packages/config/settings.py`.

## ADR-009: Asset categories in the scanner
* **Date**: 2026-11-14
* **Decision**: Each scan entry carries a `category`. Categories come only from the explicit `universe.asset_categories` config (category -> base assets); unlisted assets are `CRYPTO`. Initial config: TOKENIZED_STOCK (NVDAB, SPCXB, SOXLB, SNDKB, GOOGLB) and COMMODITY (XAUT, PAXG). Categories are display/filter only and never change rank or eligibility. The mapping is stored in each snapshot (reproducible). Migration `0003_scan_categories` adds the column; `GET /api/v1/scans/latest?category=...` filters.
* **Not done**: sector categories (L1, DeFi, AI, meme) are subjective; they need a data source or a list you approve, so none were invented.
* **Files**: `packages/scanner/scanner.py`, `packages/config/settings.py`, `config/default.yaml`, `database/migrations/0003_scan_categories.sql`, `apps/api/main.py`, `docs/API.md`.

## ADR-010: Second live-scan review (2026-11-14)
* Added RWUSD to the stablecoin exclusions (RWUSDUSDT appeared in the shortlist).
* Extended TOKENIZED_STOCK with tickers seen on Binance whose base asset is `<TICKER>B` (e.g. MUB, CRCLB, AAPLB). The list is explicit and partial; AGPUB was left out because the underlying ticker could not be confirmed. Assets not listed show as CRYPTO. Review the list when new `...B` symbols appear.
* **Files**: `config/default.yaml`, `packages/config/settings.py`.

## ADR-011: Analysis engine (Milestone 3)
- Status: Accepted (parameters provisional, approved by the user).
- Pure-Python deterministic modules: indicators, market_structure, liquidity, fvg, analysis. No look-ahead: swings are confirmed `lookback` candles later and every result carries candle timestamps.
- Sweeps need a close back above the level (reclaim); a close below is a break, not a sweep.
- Missing history fails closed (daily trend not bullish).
- Out of scope: CHoCH, persistence, API, signals (Milestone 4), backtest (Milestone 5).
* **Revisions after reviewing real output (2026-11-14)**:
  * Duplicate sweep levels per candle and stale PREV_DAY_LOW levels that stayed active for days were found in the BTC output. Fix: levels with the same price are deduplicated (PREV_DAY_LOW > EQUAL_LOWS > SWING_LOW), sweeps are grouped per candle (`sweep_events`), and previous-day levels expire at the end of their own UTC day. Regression tests added.
  * `run_analysis.py` fetches 600 four-hour and 300 daily candles. Fetching 500 left only 499 closed 4H candles (one is unfinished) against the validator minimum of 500, which wrongly excluded BTC and SOL.
* **Files**: `packages/indicators/core.py`, `packages/market_structure/swings.py`, `packages/liquidity/levels.py`, `packages/fvg/detector.py`, `packages/analysis/engine.py`, `packages/config/settings.py` (AnalysisConfig), `config/default.yaml`, `scripts/run_analysis.py`, `docs/ANALYSIS_DEFINITIONS.md`, `tests/unit/test_analysis.py`.

## ADR-012: Paper signal generator (Milestone 4)
- Status: Accepted (parameters provisional, approved by the user).
- SIGNAL only if all checks pass: daily trend bullish, sell-side sweep within the last 6 four-hour candles, an open (UNTOUCHED or ENTERED) bullish FVG formed after the sweep, ATR available, stop below entry, price above stop, price within 1 ATR above entry, a target (nearest confirmed swing high above entry and price), reward-to-risk >= strategy.minimum_reward_to_risk.
- Entry = FVG midpoint. Stop = sweep low - 0.25 ATR. Valid for 6 candles from the setup candle close.
- NO_TRADE lists failed checks. Dependent checks that cannot be evaluated are omitted, their root cause is listed.
- One stored decision per symbol and 4H candle (idempotent). The decision stores checks, evidence and params. Full replay from candles needs a candle store, which is a later item.
- Paper only. No orders, no keys.
* **Revisions**: the closest-to-signal list in `run_signals.py` now excludes symbols with invalid data and lists them separately (it was misleading). Scripts save their output to `reports/` so the agent can read results without copy and paste (user request).
* **Files**: `packages/signals/generator.py`, `packages/signals/repository.py`, `packages/config/settings.py` (SignalConfig), `database/migrations/0004_signal_decisions.sql`, `database/schema/schema.sql`, `apps/api/main.py`, `scripts/run_signals.py`, `scripts/run_all.py`, `tests/unit/test_signals.py`, `docs/API.md`.

## ADR-013: Backtest (Milestone 5)
- Status: Accepted. Minimum sample of 30 trades set by the user: below it the verdict is INSUFFICIENT_SAMPLE and no conclusion is allowed.
- Walk-forward: at each closed 4H candle only 4H candles up to it and 1D candles already closed by then are visible. Same windows as live analysis (600 four-hour, 300 daily).
- Conservative fills: limit buy fills at the entry price (never better), only the stop is checked on the fill candle, stop wins ties, stop slippage 0.05%, fees 0.1% per side, timeout after 30 candles, one position per symbol, trades still open at the data end are not counted.
- Verdicts: INSUFFICIENT_SAMPLE, NEGATIVE (avg R <= 0), MARGINAL, PROMISING (lower bound of the 95% Wilson interval of the win rate is above the break-even win rate implied by realised average win and loss R).
- Trades are pooled across symbols to reach the sample size. The report warns when one symbol supplies more than half of the trades.
- Limit: one historical period, parameters not tuned or validated out-of-sample. A good result is not proof of edge.
* **Why / evidence**: the user rejected a verdict on a small sample ("30 trades, not 12"). With 30+ trades a good result is still not proof; any defect found must lead to fixing the maths and the pattern.
* **Files**: `packages/backtest/engine.py`, `packages/backtest/metrics.py`, `packages/backtest/data.py`, `scripts/run_backtest.py`, `packages/config/settings.py` (BacktestConfig), `tests/unit/test_backtest.py`, `docs/BACKTEST.md`.

## ADR-014: Post-mortems, lessons and failure reports
- Status: Accepted (requested by the user).
- Every backtest trade gets a post-mortem. Losses are EXPECTED (within 1.5 R, a rational budgeted risk) or UNEXPECTED (gap through the stop, a wrong risk estimate). Wins are CLEAN, NORMAL, LUCKY (nearly stopped) or TIMEOUT.
- Entry-time flags (tight stop, thin reward-to-risk, deep sweep, tiny FVG, hot RSI, low volume) mark patterns that could have been vetoed. Outcome facts (fast failure, near miss) are descriptive only.
- The algorithm learns only through lessons confirmed out of sample: a flag must hurt in the earlier 60% of trades and still hurt in the later 40%. Confirmed lessons map to optional vetoes in config (signals.min_risk_atr, max_sweep_penetration_pct, min_fvg_size_atr, max_rsi, min_relative_volume, strategy.minimum_reward_to_risk). All vetoes are OFF by default and are enabled only with user approval. No automatic self-tuning, to avoid overfitting.
- Every script runs under run_guarded: a failed run writes reports/failure_<script>.txt with category, expected or unexpected, cause, advice, and a traceback for unexpected bugs. A backtest where no symbol can be downloaded is a failure, not an empty result.
* **Why**: the user asked that every failure produce a report with the cause and whether it was expected, that the algorithm avoid repeating foolish mistakes, and that successes be analysed too, not only failures.
* **Files**: `packages/backtest/postmortem.py`, `packages/reporting/failure.py`, `packages/reporting/__init__.py`, `scripts/run_backtest.py`, `tests/unit/test_postmortem.py`.

## ADR-015: Hold-out validation of vetoes (provisional values, user-approved 2026-11-14)
- Vetoes `min_fvg_size_atr=0.25` and `min_relative_volume=0.8` were suggested by lessons learned on the LAST 730 days (in-sample).
- They are enabled only via CLI flags for a test. Config defaults stay OFF.
- The test runs on the OLDER 730 days (`--end-offset-days 730`), which was never examined. Rule decided BEFORE running: if the hold-out has >=30 trades and avg_R is not better than the same window without vetoes, the vetoes are rejected and nothing is tuned further.
* **Outcome**: see ADR-021. The result was inconclusive on the first hold-out and negative on the second; the rule did not give a clean pass.
* **Files**: `scripts/run_backtest.py` (flags `--end-offset-days`, `--min-fvg-size-atr`, `--min-relative-volume`).

## ADR-016: Pattern memory (knowledge/pattern_memory.json)
- Every clean backtest (no vetoes, no experiment) records per-flag evidence by independent window. Re-running a window replaces it.
- Status: INSUFFICIENT (<2 windows) / MIXED / WATCH (hurt in >=2 windows) / RECURRING_HAZARD (hurt in >=3 windows, never helped).
- New signals are annotated with pattern-risk (advisory only). The memory never changes the strategy by itself. Promotion of a RECURRING_HAZARD to a veto needs the user's approval and a fresh unseen window.
- `scripts/rebuild_pattern_memory.py` rebuilds the file from reports/backtest_*.json.
* **Why**: the user wants the system to remember patterns that repeat and indicate a decline, not just log runs. Counting independent windows (not runs) prevents one period being counted three times.
* **Files**: `packages/backtest/memory.py`, `knowledge/pattern_memory.json`, `scripts/rebuild_pattern_memory.py`, `scripts/run_backtest.py`, `scripts/run_signals.py`, `tests/unit/test_pattern_memory.py`.

## ADR-017: Strategy lab (Milestone 6a, provisional values approved by the user 2026-11-14)
- A strategy is a recipe: context + trigger + entry + exit (+ optional filters). Recipes are pure functions of the analysis dict and share one backtester, fills, fees and windows, so comparisons are fair.
- First recipes isolate components: sweep_fvg (baseline), sweep_only (value of the FVG), fvg_only (value of the sweep), bos_retest (different idea).
- Scorecard per recipe: goal check (provisional: pooled avg R >= +0.20, PF >= 1.3, at most 1 negative window, max drawdown <= 20R, >= 100 pooled trades), what is missing, and why (win rate vs breakeven, fast stops, timeouts, small wins).
- Multiple-testing guard: `knowledge/lab_trials.json` counts recipes tried; the confidence bar uses a Bonferroni z for that count, and a pass requires the lower confidence bound of pooled avg R to be above 0.
- Out of scope for 6a: combining recipes (M6c), more recipes (M6b). Pattern memory is not fed by the lab yet.
- Hold-out by symbols: `--basket alt` runs symbols the recipes never saw.
* **Why**: the user decided we build MANY strategies from components, test all of them, find the one closest to the goal, learn what it lacks and why, and combine parts into one strategy that is integrated in terms of measured performance. The FVG is a component to study, not something to discard.
* **Files**: `packages/strategies/base.py`, `packages/strategies/recipes.py`, `packages/strategies/scorecard.py`, `packages/strategies/__init__.py`, `packages/backtest/engine.py` (pluggable `generator`), `packages/backtest/data.py` (`load_validated`), `scripts/run_lab.py`, `knowledge/lab_trials.json` (created on first run), `tests/unit/test_strategies.py`.

## ADR-018: Working rules for this project (user)
* **Date**: 2026-11-14
* **Status**: Accepted
* **Rules**:
  1. Paper only, public data only, no keys, no real orders. NO_TRADE is a valid result.
  2. Milestones are built one at a time. The user approves a finished milestone with "ok" and a plan with provisional values with "depend".
  3. The agent reads result files in `reports/` itself. The user is never asked to copy and paste output.
  4. Live commands that need Binance are run by the user: the agent environment cannot reach Binance (checked: api.binance.com, data-api.binance.vision and data.binance.vision all unreachable from both the cloud container and the local VM). This is an allow-list limit, not an IP block, so a different IP or proxy provider is not needed and would route data through a third party.
  5. No Arabic anywhere in the project: code, reports, error messages and docs are English. Arabic is for the chat only.
  6. Every decision is logged in this file (see the rule at the top).
* **Files changed for rule 5**: `packages/reporting/failure.py`, `packages/backtest/postmortem.py`, `scripts/run_backtest.py`, `docs/DECISIONS.md`.

## ADR-019: Target mode stays "nearest"; "first_meeting_rr" is a variant
* **Date**: 2026-11-14
* **Status**: Accepted (config default unchanged)
* **Decision**: `signals.target_mode` keeps the default `nearest` (nearest confirmed swing high). `first_meeting_rr` (first swing high that already pays the minimum reward-to-risk) is available as `--target-mode` and is what the lab recipes use.
* **Why / evidence**: with `nearest` only about 5% of candidates pass REWARD_TO_RISK_OK, so the first backtest produced 4 trades (INSUFFICIENT_SAMPLE). With `first_meeting_rr` the same period produced 54 trades: NEGATIVE, avg R -0.202, win rate 29.6% against a break-even of 36.4%, 0 unexpected losses.
* **Files**: `packages/signals/generator.py`, `packages/config/settings.py`, `config/default.yaml`, `scripts/run_backtest.py`.

## ADR-020: The daily-trend filter stays (experiment result)
* **Date**: 2026-11-14
* **Status**: Accepted, evidence thin
* **Decision**: keep DAILY_TREND_BULLISH as a required check. `--experiment-no-daily-gate` exists only to measure its value and its report is labelled "NOT the strategy".
* **Why / evidence**: without the filter, 99 trades, avg R -0.691, 11 unexpected gap-through-stop losses (worst UNIUSDT -12.77R). Trades inside a bullish daily regime: n=4, avg R -1.16. Outside: n=95, avg R -0.67. The filter blocks a clearly worse regime, but the bullish sample is only 4, so this is not conclusive.
* **Files**: `packages/signals/generator.py` (`ignored_checks`), `packages/backtest/engine.py` (`ignore_daily_gate`), `scripts/run_backtest.py`.

## ADR-021: Hold-out windows and the outcome of the FVG and volume vetoes
* **Date**: 2026-11-14
* **Status**: Accepted. Vetoes NOT enabled in config.
* **Method**: three independent 730-day windows ending 0, 730 and 1460 days ago (`--end-offset-days`). Pre-registered rule (ADR-015): accept the vetoes only with at least 30 pooled hold-out trades and a better average R.
* **Evidence (target `first_meeting_rr`, 25 symbols, fees and slippage included)**:
  * Window 0 (most recent): 54 trades, avg R -0.202, win 29.6%, break-even 36.4%.
  * Window 730: 81 trades, avg R -0.292, win 25.9%, break-even 35.7%. With vetoes: 18 trades, avg R +0.010 (INSUFFICIENT_SAMPLE).
  * Window 1460: 53 trades, avg R -0.283, win 24.5%, break-even 33.7%. With vetoes: 16 trades, avg R -0.533.
  * Pooled hold-outs: baseline 134 trades avg R -0.289; with vetoes 34 trades avg R -0.246. The rule passes by the letter (0.04 R better) but both are losing and the difference is noise.
* **Decisions**:
  1. The FVG-size VETO is rejected: TINY_FVG reversed in window 1460 (+0.03 with the flag, -0.70 without) and the pattern memory shows MIXED. The FVG itself is NOT discarded: it stays a component to study in the lab (user decision).
  2. LOW_VOLUME (pooled -0.61 with, +0.03 without, 87 and 101 trades) and TIGHT_STOP (pooled -0.74 with, -0.16 without, 34 and 154 trades) are RECURRING_HAZARD in the pattern memory. They are shown as advisories only. Turning one into a veto needs the user's approval.
  3. Even without LOW_VOLUME trades the average is about 0: the current idea shows no demonstrated edge.
  4. All history since 2020 is now used for testing. New hypotheses must be validated on different symbols (`--basket alt`) or by forward paper trading.
* **Files**: `scripts/run_backtest.py`, `packages/backtest/memory.py`, `knowledge/pattern_memory.json`.

## ADR-022: Binance history defect (truncated 4h candles) is tolerated with a skip rule
* **Date**: 2026-11-14
* **Status**: Accepted
* **Problem**: the window ending 1460 days ago failed for every symbol with MALFORMED_CANDLE_DATA. A first guess (clip the window start) was wrong: the defect was inside the window.
* **Evidence** (`scripts/scan_data_anomalies.py`): BTC and ETH have 7 and SOL 6 four-hour candles with a duration shorter than 4h, all between 2020-06-28 and 2021-09-29 (for example 2020-06-28 and 2021-04-20 last 2 hours). No gaps, no defects after 2021-09-29, and the daily series is clean.
* **Decision**:
  1. The validator is NOT relaxed. A 4h candle is tolerated only if the duration is its sole problem.
  2. The backtester skips every step whose 60 previous candles or whose possible trade path (signal expiry plus maximum hold) touches such a candle. The rule uses the defect position only, never prices.
  3. The window never starts before 2020-05-01. The validator is given the window end as its reference time, so old windows are not judged stale against today.
  4. The failure classifier treats MALFORMED_CANDLE_DATA as an expected data-quality failure, and skipped symbols now print their first real issue.
* **Result**: window 1460 tolerated 125 truncated candles and skipped 7,791 steps. Six symbols that did not exist then were excluded (SUI, ARB, APT and others).
* **Known caveat**: if defects cluster in volatile days (maintenance), skipping them could hide hard trades. Not measured yet.
* **Files**: `packages/backtest/engine.py` (`tainted_open_times`), `packages/backtest/data.py` (`load_validated`), `scripts/run_backtest.py`, `scripts/scan_data_anomalies.py`, `packages/reporting/failure.py`, `tests/unit/test_backtest_taint.py`, `tests/unit/test_failure_classification.py`.

## ADR-023: Backtest runs in parallel, reports progress, and never saves partial results
* **Date**: 2026-11-14
* **Status**: Accepted
* **Why / evidence**: the first experiment printed nothing for minutes and the user pressed Ctrl+C. That was not a bug, but silence looked like one.
* **Decision**: per-symbol progress lines, automatic worker count, and on Ctrl+C no report is written (a partial result is not trusted).
* **Files**: `scripts/run_backtest.py`.

## ADR-024: First lab run (main basket): what it showed, and the ranking fix
* **Date**: 2026-11-14
* **Status**: Accepted. No recipe meets the goal.
* **Evidence** (`reports/lab_main.txt`, 3 windows, 25 symbols, 4 recipes tried, z=2.24):
  * fvg_only: 844 trades, avg R -0.123, CI lower -0.241, win 29.9% vs break-even 33.7%. Per window: -0.06, -0.208, -0.033.
  * bos_retest: 333 trades, avg R -0.138, win 33.0% vs 38.4%; 80 of 333 trades timed out.
  * sweep_fvg (current strategy): 188 trades, avg R -0.264, win 26.6% vs 35.3%.
  * sweep_only: 2066 trades, avg R -0.479; 988 of 1541 losses hit the stop within 2 candles.
* **What it tells us** (measurements, not yet proofs):
  1. The sweep trigger adds nothing: sweep_fvg (-0.264) is worse than fvg_only (-0.123) on the same entry and exit.
  2. The FVG midpoint entry helps: same sweep trigger, entering at the close (-0.479) versus the FVG midpoint (-0.264) is a +0.21 R difference. The FVG is the best component found so far.
  3. All four recipes fail the same way: win rate 4 to 13 points below break-even, and they share the same context (daily bullish) and the same exit (first swing high that pays RR 2). The common parts are the first suspects, not the triggers.
  4. fvg_only is close to zero in two of three windows (-0.06 and -0.03) but is still reliably negative pooled (upper CI bound about -0.005).
* **Decisions**:
  1. Next step (M6b) varies EXIT, STOP and CONTEXT components first, with fvg_only as the base, and reports fee drag in R per recipe (stops this tight make 0.2% round-trip fees expensive in R).
  2. Defect fixed: the scorecard "closeness" was `1 - unmet/6`, so all four recipes tied at 0.17 and the column said nothing. Replaced by `criteria_met` (count out of 6, no invented weights); ranking is by criteria_met, then by the CI lower bound of avg R.
  3. The pooled drawdown (for example 1016 R for sweep_only) is the cumulative loss of a losing series, not a separate risk figure. Read it only for recipes with a positive average.
* **Not done**: the 3 windows share one symbol basket and overlapping market regimes; trades are clustered per symbol, so the CI is optimistic. `--basket alt` is the independent check.
* **Files**: `packages/strategies/scorecard.py`, `scripts/run_lab.py`, `reports/lab_main.txt`, `reports/lab_main.json`.

## ADR-025: M6b - single-part variants of fvg_only, exit management, week-clustered confidence
* **Date**: 2026-11-14
* **Status**: Accepted (user approved the plan with "depend"). Recipe constants are PROVISIONAL.
* **Decision**:
  1. Eleven new recipes, each built on `fvg_only` and changing exactly ONE part (a unit test enforces this):
     entry `fvg_entry_upper` (limit at the near edge of the gap) and `fvg_entry_lower` (far edge);
     stop `fvg_stop_half` (gap low - 0.5 ATR), `fvg_stop_2atr` (- 2 ATR), `fvg_stop_struct` (last swing low before the gap - 0.25 ATR, never closer than 1 ATR to the entry);
     exit `fvg_exit_1r`, `fvg_exit_1_5r` (fixed targets), `fvg_exit_be` (stop to the entry after +1R), `fvg_exit_partial` (half at +1R, then break-even stop, rest to the structural target), `fvg_exit_time` (exit at the close after 8 candles if the best excursion is below +0.5R);
     filter `fvg_volume` (relative volume >= 1.0).
  2. The exit variants trade the SAME setups as `fvg_only` (the setup still needs a structural target that pays 2R); only the management differs, so the comparison is clean.
  3. Exit management lives in the backtester as `ExitPlan` (default: none, the old path is unchanged). Conservative rules: levels are checked only after the fill candle; a stop wins a tie; a break-even stop applies from the NEXT candle and pays the same stop slippage and fees as any stop (it is not free); R is always measured against the original risk.
  4. The scorecard confidence bound now uses the WIDER of the naive and the time-clustered standard error (trades grouped by calendar week of the fill, Liang-Zeger variance). Reason: trades on different symbols in the same week share one market move.
  5. The lab reports fee drag in R, the number of unfilled orders and "missed winners" (price reached the target without ever touching the limit), so adverse selection of limit entries is measured instead of assumed.
  6. One lab job now runs all recipes over one (window, symbol) and shares one analysis cache (the analysis does not depend on the recipe). Results are identical to running each recipe alone (unit test) and the run is several times faster.
  7. `fvg_volume` came from looking at earlier windows (LOW_VOLUME hazard), so it is a data-informed trial: it needs unseen data (ADR-026 or forward paper trading) before anyone trusts it.
* **Why / evidence** (from `reports/lab_main.json`, `fvg_only`, 844 trades):
  * 54% of trades reach +1R but only about 25% reach the target; 35% of the losing trades touched +1R before the stop. A crude upper bound for a fixed 0.75R target is +0.108 avg R (hit rate 68% versus 62% break-even). It ignores same-candle ties and uses already-seen data, so it is a hypothesis, not a result, and it is below the +0.20 goal.
  * Average fee cost on winning trades is 0.086 R.
  * Clustering by calendar week (181 clusters) makes the standard error 1.45 times larger: the 95% interval of `fvg_only` avg R is [-0.27, +0.03], so it is neither reliably negative nor positive. The old bound was too optimistic.
  * Stop width is not what hurts `fvg_only`: avg R by risk quartile (in ATR) was -0.12, -0.16, -0.13, -0.08 (the widest was the best). The 3 stop variants test this directly.
* **Reviewed and NOT adopted (external statistical review, 2026-11-14)**:
  * "Stop distance inflation" as the cause of the losses: not visible in our data (see above).
  * Cornish-Fisher bound: applied to the raw sample skew it over-penalises (the skew of a MEAN shrinks with the square root of n). If a skew correction is needed later, use a block bootstrap by week.
  * Effective number of independent trials (M_eff) instead of Bonferroni: wrong direction now, because no recipe has a positive average yet. Revisit only when one does.
  * Empirical-Bayes shrinkage for pattern memory, and 0.5x/1.0x tiered position sizing: deferred / out of scope (signals are measured in R, paper only).
  * Invented thresholds such as `n_effective >= 60`: no evidence, not used.
  * Chain-overlap clustering of holding periods: replaced by calendar-week buckets (chaining merges trades into a few huge clusters). The reviewer's sample code also contained a syntax error.
* **Files**: `packages/backtest/engine.py` (ExitPlan, simulate_managed, Trade.fee_r, analysis cache), `packages/backtest/__init__.py`, `packages/backtest/metrics.py` (time_clustered_mean_se), `packages/strategies/recipes.py`, `packages/strategies/scorecard.py`, `scripts/run_lab.py`, `tests/unit/test_exit_plan.py`, `tests/unit/test_backtest_plan.py`, `tests/unit/test_strategies.py`.
* **Revisit when**: a recipe shows a positive average with a clustered lower bound above 0.

## ADR-026: `--basket alt` is a one-shot gate
* **Date**: 2026-11-14
* **Status**: Accepted
* **Decision**: Do not use `--basket alt` to choose, change or weight recipes. Run it once, after the M6b recipes (and later the M6c combination) are frozen on the main basket, and write the result in this log whatever it is.
* **Why / evidence**: every time window since 2020-05-01 has already been used on the main basket (ADR-021). If `alt` guides design choices it becomes a second training set and nothing unseen is left.
* **Limit to remember**: `alt` covers the SAME dates and the same market beta as the main basket, so it tests the choice of symbols, not a change of market regime. Only forward paper trading is truly out of sample.
* **Files**: `scripts/run_lab.py` (the `alt` basket already exists), `docs/DECISIONS.md`.
* **Revisit when**: the M6c strategy is frozen and forward paper trading starts.

## ADR-027: First M6b run (15 recipes, main basket): no recipe passes; what we learned
* **Date**: 2026-11-14
* **Status**: Accepted. No recipe is adopted into `config/default.yaml`. The `alt` gate (ADR-026) is NOT run because nothing is worth freezing.
* **Evidence** (`reports/lab_main.txt` and `.json`; z=2.71 for 15 recipes tried; all numbers are after fees and slippage):
  * Every recipe fails 5 of 6 criteria. Best by avg R: `fvg_entry_upper` -0.032 (828 trades, win 33.1% vs 34.1% break-even, windows -0.004 / -0.048 / -0.029), `fvg_volume` -0.042, `fvg_stop_2atr` -0.087. `fvg_only` -0.123, `sweep_fvg` -0.264, `bos_retest` -0.138. The week-clustered 95% interval of the best one, [-0.19, +0.12], contains zero: the best of 15 is not distinguishable from zero (winner's curse applies).
  * Regression check: `fvg_only`, `sweep_fvg`, `sweep_only`, `bos_retest` reproduced the previous run exactly (844, 188, 2066, 333 trades; same avg R), so the recipe refactor and the shared analysis cache changed nothing.
  * Gross edge (avg R plus fee drag) is about -0.04 R for `fvg_only` and about zero for most variants; only the near-edge entry (+0.037) and the volume filter (+0.039) are slightly positive, against fee drag of 0.07 to 0.14 R. The stop-width result (`fvg_stop_half` -0.156, `fvg_only` -0.123, `fvg_stop_2atr` -0.087) is mostly cost: gross is -0.020, -0.045, -0.042, while fee drag falls from 0.137 to 0.079 to 0.045 R as the stop widens.
  * **Adverse selection of limit entries is real and measured.** Entry position along the gap: near edge -0.032, midpoint -0.123, far edge -0.137; fill rate 77% / 72% / 68%. On matched setups both orders filled, the deeper entry has the better price (near edge minus midpoint: -0.063 R, week-clustered 95% interval [-0.09, -0.03]) but the set of setups differs: 181 trades that ONLY the near-edge limit caught (price tapped the gap and left) averaged +0.456 R (clustered SE 0.145), while 197 trades only the midpoint caught averaged -0.182 R. Likewise 211 trades the far-edge limit missed averaged +0.197 R. Setups that fall deep into the gap are weaker than setups that only tap its edge.
  * Exit management is not a lever: fixed 1R -0.154 (win 46.8% vs 54.4% break-even, avg win 0.91 R), fixed 1.5R -0.118, break-even stop -0.153, half at 1R -0.154, time exit -0.123. Paired differences against `fvg_only` were -0.002 to -0.030 with intervals covering zero.
  * Correction of ADR-025: the earlier estimate that a 0.75R target could reach +0.108 R was wrong. It used the best excursion of each trade, which overstated the hit rate (54% versus 46.8% measured at 1R: same-candle ties, and the trade set changes when a symbol is freed earlier). Counterfactuals built from excursions are not evidence; only simulated exits are.
  * Minor: about 0.5% of trades appear in two adjacent windows (4 duplicated signals at the window edges because the first 200 daily candles are warm-up). Not material.
* **Decisions**:
  1. Retire exit variants of `fvg_only`: no more exit experiments on this family.
  2. The near-edge entry becomes the BASE for the next experiments (as a hypothesis, not as a config change). Candidate combinations (near edge + wide stop, near edge + volume) are data-informed trials and count against the multiple-testing penalty.
  3. Realistic target: this family, even combined, tops out around break-even before a new source of edge is found. The +0.20 R goal is not reachable by tuning its parts.
  4. Next direction (open, needs the user's choice): (a) combine only components with positive marginal contribution and freeze for the `alt` gate; (b) add structurally different families (trend breakout with a trailing stop, higher-timeframe setups that cut fee drag, regime filters such as a BTC trend filter).
* **Files**: no code changed. Evidence: `reports/lab_main.txt`, `reports/lab_main.json`.

---
## ADR-028: M6c - 14 recipes from structurally different families
* **Date**: 2026-11-14
* **Status**: Accepted (lab parameters are PROVISIONAL; nothing is adopted into `config/default.yaml`)
* **Decision**: Add 14 recipes to the lab, so 29 are tried (Bonferroni z about 2.92, stricter than before):
  * trend breakout with a trailing stop and no profit target: `brk20_trail`, `brk55_trail`, `brk20_vol_trail` (relative volume >= 1.5), `brk20_btc_trail` (BTC daily bullish). Close above the highest high of the previous N 4H candles, daily trend bullish, close above the 4H EMA50, stop 2 ATR, trail 1R behind the best high once +1R is reached, 120-candle limit;
  * EMA pullback: `pullback_ema20` (structural target) and `pullback_ema20_trail`: EMA20 > EMA50, the candle's low touched the EMA20 and it closed back above it on a green candle; stop below the last 5 lows (never closer than 1 ATR);
  * RSI dip: `rsi_dip_30`, `rsi_dip_35`: daily uptrend, 4H RSI crosses back up through the level, stop 1.5 ATR, target 2R (the project minimum), 12-candle limit;
  * `fvg_btc` (fvg_only + BTC daily trend filter) and 5 `combo_*` recipes that combine the near-edge entry (the one real finding of ADR-027) with the 2 ATR stop, the volume filter and the BTC filter.
* **Why / evidence**: ADR-027 showed the FVG family tops out near break-even (gross edge about zero before fees, fee drag 0.05 to 0.14 R) and that exits, stops and filters cannot fix that inside the family. New sources of edge are needed: trend following (few trades, big winners, so fees weigh less), buying pullbacks inside a trend, and a market-regime filter (alt coins follow BTC). The combos are data-informed (parts chosen after seeing the main-basket windows), so they are the least trustworthy results and must be read through the alt gate.
* **Honest limits**: all constants were fixed before running the families, none tuned. The trend recipes carry a 50R cap that is never reached, so their `planned_rr` is meaningless. The BTC regime needs the BTC daily series; when it is missing the `*_btc` recipes fail closed (no trade).
* **Files**: `packages/strategies/families.py`, `packages/strategies/registry.py` (ALL_RECIPES, build_recipes moved here), `packages/strategies/recipes.py` (BASE_RECIPES, `require_btc_bullish`), `packages/analysis/engine.py` (`features`), `packages/backtest/engine.py` (trailing stop, regime input), `tests/unit/test_strategies.py` (24 tests).
* **Revisit when**: the overnight run shows which family, if any, has a clustered lower bound above 0.

## ADR-029: Pre-registered freeze rule, alt-gate verdict and portfolio combiner
* **Date**: 2026-11-14
* **Status**: Accepted. This rule was written before the 29-recipe run it will be applied to; it must not be edited after seeing that result.
* **Decision**:
  * Freeze: from the main-basket result, keep recipes with at least 100 trades, rank by the week-clustered lower confidence bound of avg R, take the top 3 with at most 2 from one family. No human choice.
  * Portfolio: merge the frozen recipes' trades per window sorted by fill time, one open position per symbol, a shared setup counts once, scored with the same scorecard.
  * Alt gate (ADR-026, used once): run only the frozen recipes and their portfolio on the 25 alt symbols. PASS = at least 100 trades, avg R >= 0.10, profit factor >= 1.15, at most 1 negative window, and avg R > 0 on the main basket. WEAK = at least 100 trades and avg R > 0 but not PASS. FAIL = avg R <= 0. INCONCLUSIVE = fewer than 100 trades. The overall verdict is the best one among the frozen recipes and the portfolio. The result is stored in `knowledge/alt_gate.json`; the runner refuses to run it a second time.
* **Why / evidence**: ADR-027 closed the alt gate "because nothing is worth freezing". The user then asked for the whole pass to run unattended, so the rule is fixed in advance: the verdict is mechanical and cannot be argued afterwards. Spending the gate on three near-copies would waste it, hence the family cap. The portfolio is how "integrated performance" is measured: the lab reports the pooled result of the combined recipes instead of assuming that combining helps.
* **Limits to remember** (ADR-026): alt has the same dates and the same market beta, so PASS only means the symbol choice was not luck. It does not prove an edge; forward paper trading is the only real out-of-sample test. A winner of 29 recipes also carries the winner's curse, which the Bonferroni z only partly covers.
* **Files**: `packages/strategies/freeze.py`, `packages/strategies/portfolio.py`, `tests/unit/test_freeze_portfolio.py` (7 tests), `tests/unit/test_overnight.py`.
* **Revisit when**: the first forward paper results exist, or the freeze picks near-duplicates despite the family cap.

## ADR-030: Offline candle cache and the one-command overnight runner
* **Date**: 2026-11-14
* **Status**: Accepted
* **Decision**: `packages/backtest/cache.py` stores closed candles per (symbol, timeframe) in `data/cache/` with one contiguous covered range. `scripts/run_lab.py` gained `--cache-dir`, `--offline`, `--as-of` (fixes the window anchor) and `--tag`. `scripts/overnight.py` runs: cache download (the only step that needs the network), the main lab, the freeze, the alt gate once, and writes `reports/MORNING_REPORT.txt`. Every stage is isolated (a failure writes `reports/failure_overnight_<stage>.txt` and the others go on); `--resume` reuses the same anchor date, so a crash can be restarted without changing the data. State is in `knowledge/overnight_status.json`.
* **Why / evidence**: the user asked for unattended work and the agent's sandbox cannot reach Binance, so the single download is done by the user's machine and everything after it is repeatable offline (the agent can also rerun experiments on the cached files). A smoke run on synthetic candles (2 symbols, 5 recipes) went through the offline path and the regime series end to end.
* **Limits**: the previous live-data result is kept as `reports/lab_main_m6b.*`; the new main result is not comparable number-for-number because the anchor date moved. `alt_gate.json` blocks a second alt run: delete that file only with a new ADR.
* **Files**: `packages/backtest/cache.py`, `packages/backtest/data.py`, `scripts/run_lab.py`, `scripts/overnight.py`, `.gitignore` (data/cache/).
* **Revisit when**: the run is slow (add a monthly-archive source) or the cache shows gaps.

---
## ADR-031: First overnight run (29 recipes, anchor 2026-11-14 08:00 UTC): no recipe passes, alt gate FAIL
* **Date**: 2026-11-14
* **Status**: Accepted. Nothing is adopted into `config/default.yaml`. The alt gate (ADR-026) is now used and `knowledge/alt_gate.json` blocks a second run.
* **Evidence** (`reports/MORNING_REPORT.txt`, `lab_main.txt`, `lab_alt.txt`; all numbers after fees and slippage; z=2.92 for 29 recipes; the whole pass took about 20 minutes: 9 for the download, 8 for the main lab, 2 for alt):
  * Main basket: no recipe meets the goal and none has a week-clustered lower bound above 0. The best lower bound is `brk55_trail` at -0.12 R. Best by criteria met: `rsi_dip_30` (3 of 6, but avg R -0.013 on 124 trades, so it passes the weak criteria only). Best avg R: `brk20_btc_trail` +0.131 (366 trades, PF 1.26, drawdown 21.8 R, 0 negative windows).
  * Per family, best avg R and family mean: breakout +0.131 / +0.056, fvg +0.082 / -0.078, rsi -0.013 / -0.024, pullback -0.015 / -0.043, smc (sweep, bos) -0.138 / -0.294. The breakout family is the only one with a positive mean, but its lower bounds are -0.12 to -0.20.
  * Frozen by the ADR-029 rule: `brk55_trail`, `brk20_btc_trail`, `pullback_ema20_trail`. Their portfolio on main: 1186 trades, avg R -0.000, PF 1.00 (199 of 1575 setups were shared; combining three weak ideas gave nothing).
  * **Alt gate, all FAIL**: `brk55_trail` -0.022 (320 trades), `brk20_btc_trail` -0.063 (245), `pullback_ema20_trail` -0.119 (770), portfolio -0.079 (934). The best main recipe, `brk20_btc_trail`, was +0.323 / +0.008 / +0.248 by window on main and -0.002 / -0.050 / -0.136 on alt, on the same dates. That is what the winner's curse looks like: its main result came from the choice of symbols (and of 29 tries), not from the rule.
  * Fee drag is 0.03 to 0.06 R per trade for the trend recipes, lower than for the FVG family, but their gross edge is about zero too (average win 1.0 to 1.3 R, win rate 48 to 49% against a 45 to 50% break-even).
* **What this closes**: on Binance Spot, long only, 4H setup, 0.1% fee per side, none of the 29 rules (FVG, sweep, break of structure, breakout with trailing stop, EMA pullback, RSI dip, BTC filter, combinations) shows a statistically supported edge. Not closed: other timeframes, other markets, other data (funding, open interest, order flow), a sector or relative-strength selection, and longer holding periods (the daily chart).
* **Limits**: the alt basket shares dates and market beta, so this FAIL says the main-basket gains do not transfer to other symbols; it does not prove that no edge exists. Several parameters (2 ATR stop, 120-candle limit, RSI 30/35, 20/55 lookbacks) were fixed in advance and never tuned, so a better-tuned version could differ, but tuning on these windows is exactly what the gate is meant to prevent. 6 main-basket symbols have no data in the oldest window (SUI, ARB, TAO, ENA, APT, OP too short) and fail closed.
* **Next direction (needs a decision, not made by the agent)**: (a) a daily-timeframe family with weekly rebalancing and relative strength across symbols, where 0.1% fees matter far less; (b) forward paper trading of the system with signals logged from now on, which is the only real out-of-sample test; (c) stop trading research and use the lab as a risk and journaling tool. The agent recommends (a) and (b) together, because (a) needs only the cached daily candles.
* **Files**: `reports/MORNING_REPORT.txt`, `reports/lab_main.*`, `reports/lab_alt.*`, `reports/lab_main_m6b.*` (the earlier live run), `knowledge/frozen_candidates.json`, `knowledge/alt_gate.json`, `knowledge/overnight_status.json`.
* **Revisit when**: a new family has a clustered lower bound above 0 on the main basket (a second alt gate would then need a new basket and a new ADR), or forward paper results exist.

---
## ADR-032: Hypothesis H1, daily relative-strength rotation (PRE-REGISTERED before any run)
* **Date**: 2026-11-14
* **Status**: Rejected (2026-11-14, see the result lines at the end of this entry). Written BEFORE the first run; parameters and kill rule were not changed after seeing the result.
* **Origin**: external research proposal `docs/GEMINI_PROPOSAL.md` (Gemini, 2026-11-14), checked by the agent: its numbers match `reports/` exactly. Its web links are search-redirect URLs that cannot be verified from here, so its literature and price claims are treated as UNVERIFIED.
* **Hypothesis**: among the main-basket coins, the ones with the best volatility-adjusted 28-day momentum keep outperforming for about a week, enough to beat simply holding BTC while BTC is above its 50-day EMA.
* **Fixed parameters**:
  * Universe: the 25 main-basket symbols, daily candles from `data/cache` only (no download). A symbol is eligible on rebalance date t only with >= 60 closed daily candles before t and a close on the day before t.
  * Score: ln(C[t-1] / C[t-29]) / standard deviation of the last 28 daily log returns.
  * Regime gate: BTCUSDT daily close > EMA(50) of daily closes, on the last closed candle before t. If false: 100% USDT.
  * Portfolio: equal weight top K=3 by score; rebalance every 7 days at 00:00 UTC, executed at the last daily close; weights drift between rebalances.
  * Costs: 0.10% fee + 0.05% slippage on each unit of traded weight (|w_new - w_drifted|).
  * Period: 2020-07-01 (60 days after the first clean candle) to the overnight anchor 2026-11-14 08:00 UTC.
* **Benchmark**: BTC-EMA50 timing (100% BTC when the same gate is on, else USDT), same cadence and costs. Context only: BTC buy and hold.
* **Kill rule** (REJECT if ANY holds): (1) the 95% lower bound of mean weekly excess return over the benchmark (moving-block bootstrap, 4-week blocks, 10000 resamples, seed 7) is <= 0 on the Monday rebalance; (2) H1's annualised Sharpe <= the benchmark's; (3) the sign of mean excess return differs across the 7 rebalance weekdays; (4) mean excess return <= 0 at doubled costs (0.20% fee + 0.05% slippage).
* **Known bias**: the cache holds only coins still listed in November 2026 (no LUNA, FTT or delisted coins), so a positive result is an upper bound and would need a survivorship-free universe before any paper trading. The main basket dates are already spent (ADR-021); this is a different structure (cross-sectional, daily), but it still counts as trial 30.
* **Files**: `packages/strategies/rotation.py`, `scripts/run_rotation_study.py`, `tests/unit/test_rotation.py`, `reports/rotation_h1.txt`.
* **Result of the pre-registered run** (2026-11-14, `reports/rotation_h1.txt`): none of the 4 kill rules fired. Monday: H1 CAGR +127.7%, Sharpe 1.45, max drawdown 60.1%; benchmark BTC-EMA50 +38.7%, Sharpe 0.97, drawdown 42.1%; weekly excess +0.0126, 95% block-bootstrap interval [+0.0024, +0.0234]; positive on all 7 weekdays (Sunday lower bound +0.0000); +0.0122 at doubled costs. Pre-registered verdict: SURVIVES.
* **Why that is not yet believed**: (a) 2021 carries it: weekly excess by year 2020 -0.007, 2021 +0.056, 2022 +0.000, 2023 +0.019, 2024 +0.003, 2025 +0.004, 2026 +0.001; (b) the main basket was chosen in 2026 among coins that are big NOW (SOL, INJ, AVAX...), so ranking 2021 momentum inside it uses hindsight about which coins would survive and grow.
* **Added robustness checks (written after seeing the pass, BEFORE running them; they can only make the test stricter, never rescue a failure)**: H1 is REJECTED if ANY of these fails, with the same parameters and kill rules 1, 2 and 4 on Monday:
  * R1: the main basket with all of 2021 removed from the excess series (weeks of 2021 dropped, not re-simulated): 95% lower bound must be > 0;
  * R2: the alt basket (25 coins that are smaller or faded since 2021: BCH, ETC, XLM, SAND, MANA, AXS...), same BTC gate, as a universe with much less hindsight; this is a new use of the alt candles for a new hypothesis, not a rerun of the ADR-026 gate (no recipe is chosen or changed by it);
  * R3: the union of both baskets (50 coins).
* **Robustness result: REJECTED.** R1 main without 2021: excess +0.0045 per week, 95% interval [-0.0030, +0.0127]: FAIL. R2 alt basket: H1 Sharpe 0.97 equal to the benchmark's 0.97, excess +0.0138 per week, interval [-0.0020, +0.0343]: FAIL (by year: 2021 +0.080, every other year between -0.014 and +0.009). R3 main+alt (50 coins): passes (Sharpe 1.29 vs 0.97, interval [+0.0050, +0.0359]), but it contains the main basket's hindsight and the same 2021.
* **What we learned**: rotation into the strongest coins earned almost all of its edge in the 2021 alt-season; outside it the point estimate is still positive (+0.3% to +1.5% per week in most years) but not distinguishable from zero, and it costs a deeper drawdown (60 to 66% against 42%). Unlike the 4H recipes (ADR-031) the sign is positive almost everywhere, so this is "not proven", not "disproven". Max drawdown of 60%+ alone makes it unfit for small accounts.
* **Not done and why**: no parameter (K, lookback, gate) was changed to rescue it; that would be tuning on spent data. A survivorship-free universe (delisted coins from `data.binance.vision`) is the only test that could change this verdict, and it would need a new ADR.

---
## ADR-033: New goal (learning pattern engine, M7) and a two-assistant workflow
* **Date**: 2026-11-14
* **Status**: Accepted (owner's decision)
* **Decision**: The owner states that profit is not the goal for now; the goal is an algorithm that learns from repeated historical patterns, predicts, and combines patterns into one decision. Work is split: Claude owns code, experiments, tests and this log; Gemini researches, writes hypothesis cards and reviews every result. They discuss in `docs/COLLAB.md` (append-only threads, every claim cites a file or a link). Accepted thread decisions become ADRs here.
* **Why**: ADR-031 and ADR-032 showed hand-written rules do not hold up; a learner over all candles measures in one test whether OHLCV holds any learnable signal. A second assistant reviewing each run reduces self-deception (one builds, the other tries to break).
* **Files**: `docs/COLLAB.md` (thread T-1 opened with the M7 proposal).
* **Revisit when**: T-1 reaches a DECISION.

---
## ADR-034: M7-FG1, learning engine on cached OHLCV (PRE-REGISTERED, agreed in docs/COLLAB.md T-1)
* **Date**: 2026-11-14
* **Status**: Rejected (2026-11-14, result below). Spec fixed before any code ran.
* **Rows**: every closed 4H candle t of every symbol, from 2020-05 + 200 candles of warm-up, where the 4H series has no gap in [t-200, t+30].
* **Primary label (the only one that decides)**: entry = open[t+1]; risk = 1.5 x ATR14[t]; target = entry + 2.0 x ATR14[t]; stop = entry - 1.5 x ATR14[t]; bars t+1..t+30; the stop wins when one candle touches both; otherwise exit at close[t+30]. Net R = (exit - entry)/risk minus fees 0.1% of entry and of exit, minus 0.05% slippage on stops. y = 1 if net R > 0. Secondary (report only): the same with +1.5/-1.0 ATR; beta-stripped sign of (coin minus BTC) return from open[t+1] to close[t+18].
* **Features** (all known at the close of t, scale-free): (close-EMA20)/ATR, (close-EMA50)/ATR, (close-max high of previous 20)/ATR, (close-min low of previous 20)/ATR, RSI14, relative volume (volume / mean of previous 20), ROC 6 and 24 candles, ATR%/price, its percentile over 200 candles, daily ROC 20 and 60 and daily close > daily EMA50 (last CLOSED daily candle), bars since the last bullish 3-candle gap (low[i] > high[i-2]) capped at 50, distance from close to that gap's top in ATR, bars since the last sweep (low below the previous 20-candle low and close back above it) capped at 50, close above the previous 20-candle high (break flag); BTC: daily close > EMA50, ROC 6 and 24; coin minus BTC ROC 6, 24 and daily ROC 20; cross-sectional percentile at t of ROC 24 and relative volume among active symbols.
* **Walk-forward**: first train 2020-05..2021-11; then 90-day test folds; train always on all earlier MAIN rows ending 42 candles (7 days) before the fold; ALT rows are never trained on, only predicted. Scalers, bins and priors are fitted inside the train window only. Row weight 1/active_symbols_at_t.
* **Learners**: (a) frequency table on at most 3 features (quantile bins from the train window, a bucket needs >= 25 distinct weeks, shrinkage toward the train base rate); (b) L2 logistic regression (standardised in-fold); (c) gradient trees only if (b) beats the control.
* **Controls**: 2-feature regime model [btc daily bullish, ATR%]; shuffled-label run (AUC must be 0.50 +/- 0.01); 10 boundary rows checked for max(feature time) < label entry time.
* **Kill rule (ANY = REJECTED)**: (1) out-of-sample AUC < 0.53, or AUC minus control AUC < 0.02 or its week-bootstrap 95% lower bound <= 0; (2) top-decile predictions as trades (one open position per symbol, the label's net R) have a week-clustered 95% lower bound of avg R <= 0 on MAIN or on ALT, judged separately; (3) top-decile avg R negative in >= 2 of 3 eras (2020-22, 2022-24, 2024-26); (4) top-decile calibration error |mean predicted - realised| > 0.05.
* **Known limits**: survivorship in the cache (coins listed in Nov 2026); simplified event definitions; 4H OHLCV already failed as rules (ADR-031), so a REJECT is the expected outcome and would close OHLCV-only learning before FG2 (funding, OI, taker-buy) is downloaded.
* **Result** (`reports/m7_fg1.txt`, 643,754 rows, 21 folds, 518,252 out-of-sample rows, 143 s): REJECTED by kill rules 1, 2 and 3 on both baskets and 4 on alt.
  * AUC: main 0.5129, alt 0.5154 (alt was never trained on). Control [btc daily bullish, ATR%] 0.487 / 0.489; frequency table 0.498 / 0.500. Model minus control +0.026, week-bootstrap 95% [+0.005, +0.043] on both baskets.
  * Top decile as trades (one position per symbol): main 3,353 trades, avg R -0.066, 95% [-0.143, +0.011]; alt 3,660 trades, -0.048, [-0.126, +0.031]. Base avg R of all rows is -0.123 / -0.134, so the model's best 10% are about +0.07 R better than random, not enough to pay costs. Eras main -0.171 / +0.038 / -0.124.
  * Most used features: distance to EMA50 and EMA20 in ATR (top 3 in all 21 folds), then coin minus BTC 20-day return and ATR percentile.
* **Shuffled-label control was 0.483, outside the pre-registered 0.50 +/- 0.01.** This is recorded as a kill but read as a mis-set tolerance, not leakage: a model fitted on permuted labels cannot see the future, and the 2-feature control is also below 0.5 (0.487), so out-of-sample AUC moves by about +/-0.02 just from regime shifts when rows of the same weeks move together. Consequence: AUC differences below about 0.02 are noise in this data, and the true signal (0.513-0.515) is at the edge of that noise. The tolerance is not changed after the fact; a future run should set it from a repeated-shuffle distribution.
* **What we learned**: (1) OHLCV holds a tiny, consistent ranking signal (it appears on coins the model never saw, mostly "how far price is from its moving averages"), but it is far below the cost of trading; (2) the frequency-table version of "pattern memory" (the closest thing to "a pattern that repeated") is no better than chance; (3) this closes OHLCV-only learning for this label. Per the T-1 plan the next step is FG2 (taker-buy share, funding, open interest), judged by its gain over FG1 on the same rows.
* **Files**: `packages/learning/dataset.py`, `packages/learning/model.py`, `scripts/run_m7.py`, `tests/unit/test_learning.py` (8 tests), `reports/m7_fg1.*`.

---
## ADR-035: Automatic discussion loop between Gemini and Claude
* **Date**: 2026-11-14
* **Status**: Accepted (owner's request: no more manual copy and paste)
* **Decision**: `scripts/collab_loop.py` alternates the Gemini CLI (reviewer) and the Claude Code CLI (lab runner) on the owner's computer. Each turn reads `docs/COLLAB.md` and appends one block; Claude may pre-register, code, test and run offline experiments (tools limited to file edits and python/pytest commands). The loop stops after N rounds (default 4), when a block contains `LOOP: STOP` (a question for the owner), or when an assistant appends nothing. Log: `reports/collab_loop.log`; each turn's raw output: `reports/collab_last_<agent>.txt`.
* **Why**: the agent's own sandbox and the device VM cannot reach Google's API (proxy: "no rule allows host generativelanguage.googleapis.com"), so the loop cannot run from the chat session; both CLIs already work on the owner's machine with his sign-ins.
* **Safety**: every rule of this log still applies inside the loop (pre-registration before runs, no rule change after a result, no orders, no downloads unless an ADR says so). The owner reads COLLAB.md and DECISIONS.md after each loop.
* **Files**: `scripts/collab_loop.py`.
* **Update 2026-11-14 (loop runs on the owner's computer)**: the loop started 3 times and stopped each time at Gemini's turn. `reports/collab_last_gemini.txt` shows Google's server answering `503 This model is currently experiencing high demand` on every retry (two runs ended with exit 130, i.e. stopped by hand during the retries). The loop code worked as designed. Added: `--retries` (default 3) with `--wait-min` (default 10) between tries, and `--gemini-model` to choose a less loaded model.

---
## ADR-036: Forward paper journal (roadmap step 4)
* **Date**: 2026-11-14
* **Status**: Accepted. Tracked recipes and the verdict rule are PRE-REGISTERED here, before the first live signal.
* **Context**: the owner's plan document ("Digital trading project: goal, analysis and conclusions", 14 Nov) has 5 steps: read-only security, written numeric rules, a clean backtest with a locked sample, 2-3 months of live paper trading, then tiny real money. Steps 1-3 are done in this repository (ADR-021..035). Its "first rule" (a false break of a low, closed back above it, 4H, long only) is `sweep_only`: `packages/liquidity/levels.py` `detect_sweeps` requires the candle's low below a sell-side level (previous-day low, equal lows, swing low) by a minimum penetration AND a close back above it, entry at the close. It was already tested: 2,066 trades, avg R -0.479 (ADR-031), the worst of 29.
* **Decision**:
  * Tracked recipes: `brk55_trail` (best clustered lower bound on main), `brk20_btc_trail` (best avg R on main), `sweep_only` (the owner's chosen first rule, kept so his own rule is measured live and not only in the backtest). None of them passed the alt gate; the journal measures, it does not recommend.
  * `scripts/forward_journal.py scan` runs after each 4H close on the main basket with public data; a SIGNAL on the last closed candle becomes a record with entry, stop, target, the reasons FOR (passed checks, sweep/FVG evidence) and AGAINST (its backtest and alt results). `settle` re-runs `simulate_order`, the exact backtest rules (fill window, stop wins ties, fees 0.1% per side, 0.05% stop slippage, exit plan), on the candles seen since. `decide` records the owner's choice (taken with his real price, or skipped), mood 1-5 and a note; skipped signals are recorded too. `review` writes `reports/forward_review.txt`: system R per recipe with week-clustered intervals, the owner's taken vs skipped results, and his manual-execution cost (his R minus the system's R).
  * Verdict rule per recipe (looked at only at 100 and at 200 closed signals): upper 95% bound < 0 -> KILLED; lower bound > 0 -> PASSED (the owner may then consider the tiny-real-money step); otherwise continue to 200, where an interval that still contains 0 -> KILLED. The owner may replace this rule with his own wording before the first signal of a recipe is settled; after that it is frozen.
* **Why**: every historical sample is spent (ADR-026, ADR-031); only data that does not exist yet can test a rule without bias. Recording the owner's decisions next to the system's measures the question his plan asks ("system versus me").
* **Limits**: about 1-3 signals per day across 25 coins is expected, so 100 closed signals per recipe may take months; a market entry at the candle close assumes the scan runs soon after the close (`scan_lag_min` is stored). Paper only: no order is ever sent.
* **Files**: `packages/journal/forward.py`, `scripts/forward_journal.py`, `tests/unit/test_forward_journal.py` (8 tests), `knowledge/forward_journal.jsonl` (created on first scan). Full suite: 220 passed.
* **First live scan** (2026-11-14 16:05 UTC, owner's machine): 0 new signals, 0 symbols skipped; the data path works end to end.
* **Handoff** (2026-11-14): the owner moves the work from the claude.ai chat to Claude Code in VS Code. `CLAUDE.md` (repository root) carries the rules and the current state so a new session starts with them.
* **Verdict rule FROZEN** (2026-11-15): the owner accepts the verdict rule above, unchanged, for all three recipes, including `sweep_only` (his own rule). Evidence that this came before any settlement: `knowledge/forward_journal.jsonl` was empty (0 records) at the time of acceptance. From now on the rule cannot be replaced or softened for any of the three recipes; extra checks may only make it stricter (rule 2 of CLAUDE.md).

---
## ADR-037: Third owner decision "absent" in the forward journal
* **Date**: 2026-11-15
* **Status**: Accepted (owner's request). Written before any signal exists: `knowledge/forward_journal.jsonl` had 0 records.
* **Context**: ADR-036 compares the owner's "taken" and "skipped" signals. A signal that arrives while he is asleep or away is neither a choice to take nor a choice to skip; counting it as "skipped" would make his skipping look like judgment when it was only absence.
* **Decision**:
  * `decide ID absent` records "I was not there". The system's R for an absent signal is computed as usual and counts in the recipe's verdict (ADR-036, unchanged). Absent signals are left out of the taken-versus-skipped comparison and shown on their own line in `review`.
  * A signal with no decision more than 4 hours after its signal candle CLOSED (candle open + 4h + 4h) is marked "absent" automatically (`owner.auto = true`) by any command (`scan`, `settle`, `list`, `decide`, `review`).
  * Added by Claude, stricter than the request: once the 4-hour window has passed, `decide` refuses to record or change a decision. Without this the owner could see the outcome and then call the signal "taken" or "skipped" (hindsight bias). Within the window a decision may still be corrected.
* **Why**: the comparison "the system versus me" only means something if each label reflects a decision made before the outcome was known.
* **Limits**: the 4-hour window is measured against the computer's clock when a command runs; if no command runs for a long time, the mark is applied at the next run with the same result (the window is judged against the candle close, not the run time).
* **Files**: `packages/journal/forward.py` (`DECISIONS`, `DECISION_WINDOW_MS`, `auto_absent`, `decision_window_open`, review line), `scripts/forward_journal.py` (`mark_absent`, `decide` window check), `tests/unit/test_forward_journal.py` (3 new tests). Full suite: 223 passed.

---
## ADR-038: Scan backfill of missed 4H candles (no daytime-only sample)
* **Date**: 2026-11-15
* **Status**: Accepted (owner's request). Written before any signal exists: `knowledge/forward_journal.jsonl` had 0 records.
* **Context**: `scan` analysed only the last closed 4H candle. When the computer is asleep or off (Task Scheduler does not run then), the signals of the missed candles were never recorded, not even as "absent". The journal would hold mostly daytime signals and the verdict at 100 signals (ADR-036) would be judged on a biased sample.
* **Decision** (pre-registered constants in `packages/journal/forward.py`):
  * `scan` analyses every closed 4H candle of each symbol that it has not analysed yet, oldest first. Each candle is analysed with only the data closed at that candle's close, sliced exactly as the backtester does: the last 600 4H candles ending at it, the daily candles fully closed by its close (`closed_daily_count`), and BTC's daily regime at that time.
  * `BACKFILL_MAX_MS` = 7 days: candles that closed more than 7 days before the scan are not analysed. They are written as a coverage gap (symbol, first and last candle) in `knowledge/forward_scan_state.json` and listed at the top of `review`, so a missing period is visible and never silent.
  * Added by Claude, stricter than the request: `JOURNAL_START_OPEN_MS` = 2026-11-14 12:00 UTC, the candle analysed by the first live scan (2026-11-14 16:05 UTC). Backfill never goes earlier. Without this, the first backfill would reach 7 days back and re-enter the backtest sample (anchor 2026-11-14 08:00 UTC, ADR-031).
  * A backfilled signal keeps its original candle time; its record has `backfilled: true` and its real `scan_lag_min`. If its candle closed more than 4 hours before the scan it is marked "absent" at once (ADR-037). Its system R counts in the verdict like any other signal.
  * Per-symbol progress (`last_open_ms`) is advanced only after that symbol's data was fetched and validated; a symbol skipped fail-closed is backfilled at the next scan.
  * The live candle is now analysed with 600 4H candles, as in the backtest (before: 599, because the unfinished candle was dropped from a 600-candle fetch).
* **Why**: a verdict is only as good as the sample. Signals that arrive while the owner sleeps must be in the sample, with the same rules as the others.
* **Verification** (2026-11-14 16:21 UTC, on temporary files, the real journal untouched): first scan analysed 25 candles (one per symbol, the 12:00 UTC candle), second scan 0 (no duplicate work). A test run with the start moved 3 days earlier analysed 475 candles (25 x 19) without error. Both found 0 signals: at that time 0 of 25 coins and BTC had a bullish daily trend, and all three recipes require one, so long periods without signals are expected in a falling market.
* **Known limit, not changed here**: the backtest skips new signals of a symbol while one of its trades is open; the journal records every signal. Aligning the two would change ADR-036's sample and needs its own ADR before the first settled signal.
* **Files**: `packages/journal/forward.py` (`BACKFILL_MAX_MS`, `JOURNAL_START_OPEN_MS`, `backfill_plan`, `backfilled` field, gaps in `review`), `scripts/forward_journal.py` (`cmd_scan`, `load_state`/`save_state`), `knowledge/forward_scan_state.json` (git-ignored), `tests/unit/test_forward_journal.py` (6 new tests). Full suite: 229 passed.

---
## ADR-039: Open-source hardening before the first public push
* **Date**: 2026-11-14
* **Status**: Accepted (owner's request: a public repository that other programmers can join and understand easily)
* **Security fixes** (found by an audit of the code and configuration; no secret was found anywhere and Git had no commit yet, so no history needs cleaning):
  * `docker-compose.yml`: PostgreSQL was published on all network interfaces with a well-known password; now bound to `127.0.0.1` and the password comes from `POSTGRES_PASSWORD`.
  * `.env.example`: `API_HOST` 0.0.0.0 -> 127.0.0.1; default database is SQLite (no password at all); the PostgreSQL example uses `CHANGE_ME`.
  * `apps/api/main.py`: the `symbol` path parameter is validated (`^[A-Za-z0-9]{2,20}$`) and `timeframe` is length-limited.
  * `apps/web/package.json`: minimum Next.js 14.2.25 (middleware authorization-bypass fix, CVE-2025-29927).
  * Audit found no eval/exec, no unsafe YAML or pickle loading, no shell commands built from input, and only parameterised SQL.
* **Privacy**: `knowledge/forward_journal.jsonl` (the owner's decisions, mood and notes) is never committed. Large re-creatable files (`reports/*.json`, `data/cache/`, logs) are ignored; small `reports/*.txt` results are committed so every ADR's evidence is visible.
* **Contributor structure**: new `README.md` (disclaimer, findings table, 5-minute quick start, repository map), `CONTRIBUTING.md` (where each kind of change goes, the 7 rules, PR checklist), `SECURITY.md`, `CODE_OF_CONDUCT.md`, MIT `LICENSE`, GitHub Actions CI (tests on Python 3.11 and 3.12 for every push and pull request), PR and issue templates (the research-idea template asks for fixed parameters and a kill rule up front). `docs/ARCHITECTURE.md` rewritten to the current code; the old texts are kept as `docs/ARCHITECTURE_M1.md` and `docs/MILESTONES.md`.
* **Check**: dry-run `git add` lists 156 files (1.1 MB), scanned for keys, tokens and e-mail addresses: none. Full suite: 229 passed.
* **Note**: written in the claude.ai chat while the VS Code session wrote ADR-038 (scan backfill) at the same time; numbered 039 to keep one number per decision.
