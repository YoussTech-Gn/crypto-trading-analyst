# AI Crypto Trading Analyst

## Project Specification and AI Agent Operating Rules

**Document status:** Initial implementation specification\
**Version:** 1.0\
**Primary exchange:** Binance\
**Initial market:** Binance Spot, USDT trading pairs\
**Trading direction:** LONG only\
**Trading style:** Swing trading\
**Primary timeframes:** 1D (market direction) and 4H (setup and entry)\
**Execution:** Manual by the user\
**Initial operating modes:** Historical backtesting and paper trading\
**Real-money execution:** Out of scope

------------------------------------------------------------------------

## 1. Project purpose

Build a reliable, evidence-driven crypto market analysis system that
scans Binance markets, identifies potentially interesting
cryptocurrencies, evaluates them using explicit and testable rules, and
presents clear LONG trading signals.

The system is an **analysis and decision-support tool**. It does not
place real trades. The user independently reviews each signal and
decides whether to act on it.

The system must be willing to return **NO TRADE**. It must never
manufacture a signal simply to appear useful.

### 1.1 What the system should do

1.  Discover active and sufficiently liquid Binance USDT Spot markets.
2.  Rank eligible assets using recent market activity, including 24-hour
    quote volume.
3.  Analyze selected assets using historical and current market data.
4.  Apply deterministic technical and quantitative rules.
5.  Generate a LONG setup only when all required conditions are
    satisfied.
6.  Calculate an entry zone, invalidation level, stop-loss, targets, and
    risk/reward.
7.  Explain the evidence behind each signal in plain language.
8.  Save every scan, signal, strategy version, and simulated trade.
9.  Backtest the rules and evaluate them using realistic assumptions.
10. Paper-trade signals using live market data without placing orders.

### 1.2 What the system must not do

-   Do not place, modify, or cancel real exchange orders.
-   Do not request or store Binance withdrawal permissions.
-   Do not promise profits, accuracy, or a particular win rate.
-   Do not describe a model estimate as a certainty or guaranteed
    prediction.
-   Do not invent market data, indicator values, fills, or historical
    results.
-   Do not generate a signal when data is stale, incomplete,
    contradictory, or invalid.
-   Do not silently change strategy rules after seeing backtest
    outcomes.
-   Do not use future candle information when generating historical
    signals.
-   Do not treat popularity, a large price increase, or an AI
    explanation as proof of a good trade.

------------------------------------------------------------------------

## 2. Product form: build a website first

Build this as a **responsive web application**, not a native Android or
iOS app.

### Recommended stack

  -----------------------------------------------------------------------
  Layer                   Technology              Responsibility
  ----------------------- ----------------------- -----------------------
  Frontend                Next.js + TypeScript    Website, dashboard,
                                                  charts, signal views

  Backend API             Python + FastAPI        Market analysis,
                                                  signals, risk
                                                  calculations

  Data processing         Python, Pandas, NumPy   Candle processing and
                                                  calculations

  Database                PostgreSQL              Persistent market,
                                                  signal, and test
                                                  records

  Background jobs         A separate Python       Scanning, data updates,
                          worker                  paper-trade monitoring

  Charts                  TradingView Lightweight Candlestick and
                          Charts                  indicator visualization

  Exchange data           Binance public          Exchange metadata,
                          market-data API         tickers, candles

  Testing                 pytest                  Unit, integration, and
                                                  strategy tests
  -----------------------------------------------------------------------

Use a clear API boundary between Next.js and FastAPI. The frontend must
not contain strategy calculations or connect directly to private
exchange endpoints.

### Why a website is sufficient

The user can open the website from a desktop or mobile browser. A
responsive layout is enough for the first release. A Progressive Web App
(PWA) can be considered later if installability or notifications become
useful. A native mobile application is not required.

### Suggested high-level architecture

``` text
                         BINANCE PUBLIC DATA
                                  |
                                  v
                         MARKET DATA SERVICE
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
              MARKET SCANNER              CANDLE STORAGE
                    |                           |
                    v                           v
             ASSET SHORTLIST             ANALYSIS ENGINE
                                                |
                 +------------------------------+------------------+
                 |              |               |                  |
                 v              v               v                  v
           MARKET STRUCTURE  LIQUIDITY         FVG             MOMENTUM
                 |              |               |                  |
                 +--------------+---------------+------------------+
                                                |
                                                v
                                      SIGNAL / RULE ENGINE
                                                |
                                                v
                                       RISK VALIDATION
                                                |
                                  +-------------+-------------+
                                  |                           |
                                  v                           v
                              NO TRADE                   VALID SIGNAL
                                                              |
                                                              v
                                                    SIGNAL DATABASE
                                                              |
                                                              v
                                                     FASTAPI BACKEND
                                                              |
                                                              v
                                                     NEXT.JS WEBSITE
                                                              |
                                                              v
                                                   USER REVIEWS SIGNAL

                         PAPER-TRADING ENGINE
                                  |
                                  v
                         PERFORMANCE EVALUATION
                                  |
                                  v
                         BACKTEST / REPORTING
```

------------------------------------------------------------------------

## 3. Trading scope and market universe

### 3.1 Initial trading scope

The first release uses:

-   Binance Spot.
-   USDT-quoted trading pairs.
-   LONG setups only.
-   1D candles for the higher-timeframe market filter.
-   4H candles for setup detection and entry planning.

Do not implement Futures, leverage, short selling, margin, or automatic
execution in the first release. Keep the architecture extensible, but do
not add these features without explicit approval.

### 3.2 Market scanner

The scanner should:

1.  Retrieve exchange trading-pair metadata.
2.  Include only eligible, active Spot symbols quoted in USDT.
3.  Exclude stablecoins, leveraged tokens, suspended markets, and
    unsuitable assets.
4.  Retrieve 24-hour ticker statistics.
5.  Rank candidates using measurable fields:
    -   24-hour quote volume;
    -   24-hour percentage change;
    -   relative volume, when sufficient historical data exists;
    -   spread and liquidity, where reliable data is available;
    -   volatility and data sufficiency.
6.  Produce a configurable shortlist. Start with up to 30 candidates.
7.  Store the timestamp and inputs used for every ranking.

A coin's 24-hour percentage gain must not be used as a standalone buy
signal. The scanner discovers assets to investigate; the strategy engine
decides whether a setup exists.

### 3.3 Exclusions and data-quality gates

Exclude or flag an asset when:

-   The pair is not eligible for the configured market.
-   Trading is halted or the symbol is not active.
-   Candle history is insufficient.
-   Required candles are missing or duplicated.
-   Data timestamps are inconsistent or stale.
-   Spread or liquidity fails configured limits.
-   The asset is a stablecoin or leveraged token.
-   The market has unusual conditions that make the strategy unreliable.

All exclusion rules must be configurable and documented.

------------------------------------------------------------------------

## 4. Timeframes and analysis responsibilities

### 4.1 Daily timeframe (1D): market context

Use the daily timeframe to evaluate:

-   Overall trend and market structure.
-   Recent swing highs and swing lows.
-   Major support and resistance areas.
-   Trend and momentum context.
-   Nearby higher-timeframe invalidation or resistance areas.

The daily analysis determines whether a LONG setup is permitted. It does
not by itself create an entry signal.

### 4.2 Four-hour timeframe (4H): setup and entry

Use the 4H timeframe to evaluate:

-   Liquidity sweeps.
-   Break of Structure (BOS) or other explicitly defined structure
    confirmation.
-   Fair Value Gap (FVG) formation and mitigation.
-   Entry-zone conditions.
-   Stop placement and target feasibility.
-   Whether the setup is still valid at the time it is displayed.

### 4.3 Candle rules

-   Use exchange timestamps and a consistent timezone internally (UTC).
-   Distinguish closed candles from the currently forming candle.
-   Do not confirm a candle-based signal using an unfinished candle
    unless the strategy explicitly defines an intrabar rule.
-   Every calculation must identify the candle timestamp it uses.
-   Historical and live analysis must use the same rule definitions.
-   Never use a future candle to decide what a past signal would have
    been.

------------------------------------------------------------------------

## 5. Strategy rules: explicit, deterministic, testable

The first strategy should be a **baseline research hypothesis**, not a
claim of profitability. Implement each rule as a separately testable
function. Keep thresholds in versioned configuration rather than
scattering unexplained constants through the code.

### 5.1 Daily trend filter

Define and test a reproducible bullish-trend rule. It may use confirmed
swing structure, moving-average context, or both.

The rule must specify:

-   How swing highs and lows are identified.
-   How many confirmed swings are required.
-   What qualifies as bullish structure.
-   What invalidates the bullish context.
-   Whether moving averages are used and their exact periods.
-   Whether the rule is evaluated on candle close.

Do not label a market bullish based on subjective chart interpretation
alone.

### 5.2 Market structure

Implement deterministic detection for:

-   Swing highs and swing lows.
-   Higher highs (HH) and higher lows (HL).
-   Lower highs (LH) and lower lows (LL).
-   Break of Structure (BOS).
-   Change of Character (CHoCH), if included.

Document the pivot/swing detection method, confirmation delay, and price
comparison rules. A swing point must not be treated as known before the
required confirming candles have closed.

### 5.3 Liquidity

Potential liquidity references may include:

-   Previous confirmed swing highs and lows.
-   Equal highs and equal lows within a configurable tolerance.
-   Previous daily highs and lows.
-   Other explicitly defined reference levels.

A liquidity sweep must have a precise definition, including the required
penetration and close/reclaim behavior. A touch of a level is not
automatically a sweep.

Store the reference level, detection time, sweep candle, and
confirmation status.

### 5.4 Fair Value Gap (FVG)

For a conventional three-candle bullish FVG, using three sequential
candles C1, C2, and C3:

`Low(C3) > High(C1)`

The gap interval is:

`[High(C1), Low(C3)]`

For every detected FVG, store:

-   Symbol and timeframe.
-   Formation timestamp.
-   Lower and upper boundaries.
-   Gap size and size relative to price or ATR.
-   Whether price has entered or mitigated the gap.
-   Whether the gap has been invalidated.
-   The exact rule used to classify its status.

Do not assume every FVG is tradable. Require the configured
market-context and confirmation conditions.

### 5.5 Momentum and volatility

Indicators such as RSI, ATR, moving averages, and relative volume may be
used as supporting filters.

For every indicator:

-   Specify the formula or trusted implementation.
-   Specify its parameters.
-   Test edge cases and missing data.
-   Record the input timeframe and candle timestamp.
-   Avoid adding indicators merely to make the system look
    sophisticated.

### 5.6 Baseline LONG setup

A candidate LONG setup may proceed only when all required gates pass:

1.  Daily market context satisfies the configured bullish rule.
2.  The 4H setup has a confirmed, rule-based trigger.
3.  The liquidity and/or FVG conditions required by the selected
    strategy version are present.
4.  The entry has not already been missed.
5.  A valid invalidation level and stop-loss can be calculated.
6.  At least the configured minimum reward-to-risk is available after
    reasonable cost assumptions.
7.  Data quality and liquidity checks pass.
8.  The signal is not a duplicate of an active or recently expired
    setup.

The exact combination of liquidity sweep, BOS, FVG retest, and
supporting filters must be a named, versioned strategy. Do not silently
change the required combination.

If any mandatory condition fails, return `NO_TRADE` and record the
failed conditions.

------------------------------------------------------------------------

## 6. Signal contract

Every signal must be saved as structured data before being rendered in
the user interface.

### 6.1 Required signal fields

``` json
{
  "signal_id": "unique-id",
  "strategy_version": "baseline-1.0",
  "symbol": "BTCUSDT",
  "market": "BINANCE_SPOT",
  "direction": "LONG",
  "status": "PENDING_ENTRY",
  "created_at": "UTC timestamp",
  "expires_at": "UTC timestamp",
  "timeframes": {
    "context": "1D",
    "setup": "4H"
  },
  "entry_zone": {
    "low": 0,
    "high": 0
  },
  "stop_loss": 0,
  "take_profit_targets": [],
  "estimated_reward_to_risk": 0,
  "setup_evidence": [],
  "invalidation_conditions": [],
  "risk_warnings": [],
  "data_snapshot_id": "snapshot-id"
}
```

Values above are a schema example, not trade prices or a real signal.

### 6.2 Signal statuses

Use explicit statuses:

-   `WATCHLIST`: candidate worth monitoring, not an actionable signal.
-   `PENDING_ENTRY`: setup confirmed; entry conditions have not yet been
    met.
-   `ACTIVE`: entry condition has been met under the paper-trading
    model.
-   `EXPIRED`: entry opportunity expired before activation.
-   `INVALIDATED`: setup conditions no longer hold.
-   `COMPLETED`: simulated trade reached its defined completion
    condition.
-   `NO_TRADE`: mandatory conditions failed.

Do not present `WATCHLIST` or `PENDING_ENTRY` as if an entry has already
occurred.

### 6.3 Signal explanation

For each signal, show:

-   Why the asset was selected by the scanner.
-   Daily trend evidence.
-   4H setup evidence.
-   Entry-zone logic.
-   Stop-loss logic.
-   Target logic.
-   Estimated reward-to-risk.
-   Conditions that invalidate the setup.
-   Data timestamp and strategy version.
-   Important limitations or conflicting evidence.

An AI explanation layer may translate these facts into readable
language. It must not create, alter, or embellish the underlying
numbers.

------------------------------------------------------------------------

## 7. Risk and position calculations

The first release is Spot and paper-trading only. Risk calculations are
informational and must not imply that a trade is safe.

Implement configurable controls:

-   Maximum simulated account risk per trade.
-   Maximum number of simultaneous simulated positions.
-   Minimum reward-to-risk.
-   Maximum permitted spread.
-   Minimum quote volume.
-   Maximum signal age.
-   Maximum permitted distance between current price and entry zone.

Position size should be calculated from the user's configured simulated
equity, allowed risk amount, and entry-to-stop distance. Account for
trading fees and a configurable slippage assumption.

Do not hardcode a promise that a stop-loss will execute at its exact
price. Gaps, fast markets, and liquidity conditions can produce worse
fills.

A signal must be rejected if its stop, target, entry, or risk
calculations are invalid or internally inconsistent.

------------------------------------------------------------------------

## 8. Backtesting and performance validation

Backtesting is a core requirement, not a later cosmetic feature.

### 8.1 Required protections

-   No look-ahead bias.
-   No future candle data in past decisions.
-   No use of unconfirmed swing points before confirmation.
-   No retrospective signal creation based on later price movement.
-   Explicit handling of candles where stop-loss and take-profit are
    both touched and their order is unknowable from OHLCV data.
-   Include trading fees and configurable slippage.
-   Model entry-zone fills realistically; a candle touching a zone does
    not guarantee a fill.
-   Keep strategy development data separate from out-of-sample
    evaluation data.

### 8.2 Required metrics

Report at minimum:

-   Number of trades.
-   Win rate.
-   Gross and net profit/loss.
-   Profit factor.
-   Expectancy per trade.
-   Average winner and average loser.
-   Maximum drawdown.
-   Average holding time.
-   Fees and estimated slippage.
-   Results by symbol.
-   Results by market regime.
-   Results by year or test period.

Do not judge a strategy by win rate alone.

### 8.3 Testing stages

1.  Unit tests for every calculation and rule.
2.  Historical backtests on a defined development period.
3.  Out-of-sample tests on unseen periods.
4.  Walk-forward evaluation where appropriate.
5.  Live-data paper trading.
6.  Review of discrepancies between expected and simulated fills.

Every backtest report must include the date range, symbols, candle
intervals, strategy version, configuration, cost assumptions, and data
source.

### 8.4 Improvement policy

The system may suggest strategy improvements, but it must not
automatically rewrite production rules.

For every proposed change:

1.  Explain the problem being addressed.
2.  Identify the exact rule being changed.
3.  Create a new strategy version.
4.  Run the same baseline tests.
5.  Compare in-sample and out-of-sample results.
6.  Report trade-offs and possible overfitting.
7.  Require human approval before adopting the change.

Preserve previous strategy versions and their results.

------------------------------------------------------------------------

## 9. AI agent operating rules

These rules apply to any coding agent working on this project, including
Codex or Claude Code.

### Rule 1 --- Read before acting

Read this entire specification before planning, editing, or creating
files. Inspect the existing repository before proposing a new structure.

### Rule 2 --- Do not assume

If a requirement is unclear or conflicts with existing code, explain the
ambiguity and ask for clarification when it affects architecture,
trading logic, data integrity, or scope. Do not invent a trading rule.

### Rule 3 --- Plan before implementation

Before each phase:

1.  State the objective.
2.  Inspect relevant files.
3.  List the files to create or modify.
4.  Describe the implementation approach.
5.  Identify risks and dependencies.
6.  Define tests and acceptance criteria.

Wait for approval before making a large or irreversible architectural
change.

### Rule 4 --- Work in small, verifiable phases

Implement one milestone at a time. Do not generate the entire
application in one large operation. Finish each milestone with tests, a
concise summary, and any known limitations.

### Rule 5 --- Mathematical correctness first

All market calculations and strategy rules must be deterministic,
documented, and tested. Never delegate price calculations, signal
status, or risk calculations to an LLM.

### Rule 6 --- AI must not fabricate evidence

The explanation model may only use data supplied by the application. If
required evidence is missing, it must say so. It must not invent prices,
probabilities, market events, or performance statistics.

### Rule 7 --- Preserve safety boundaries

Do not implement real-money trading, order execution, leverage,
withdrawals, or private account actions. Do not request exchange
secrets. Use public market data and simulated balances only.

### Rule 8 --- Protect data integrity

Validate API responses, timestamps, candle ordering, duplicate records,
missing candles, and numeric values. Handle rate limits, retries,
timeouts, and exchange outages safely. Never silently treat failed data
retrieval as valid market data.

### Rule 9 --- Test every meaningful change

Add or update tests for calculations, strategy rules, API behavior, and
edge cases. Run relevant tests before declaring a task complete. Never
claim a test passed unless it was actually run and passed.

### Rule 10 --- Keep documentation current

Update relevant documentation when architecture, configuration, data
schemas, API contracts, or strategy rules change. Record important
decisions and explain why they were made.

### Rule 11 --- No hidden strategy changes

Never change thresholds, indicators, entry conditions, stop logic,
target logic, or risk settings without documenting the change and
assigning a new strategy version.

### Rule 12 --- Report honestly

At the end of each task, report: - What changed. - Files created or
modified. - Tests run and their actual results. - Remaining issues. -
Assumptions made. - The next recommended milestone.

Do not claim the system is profitable because it compiles, passes unit
tests, or produces attractive signals.

------------------------------------------------------------------------

## 10. Suggested repository structure

Start with a simple monorepo. Adjust only when there is a demonstrated
need.

``` text
crypto-trading-analyst/
|
|-- README.md
|-- PROJECT_SPEC.md
|-- .env.example
|-- .gitignore
|
|-- apps/
|   |-- web/                     # Next.js frontend
|   |
|   |-- api/                     # FastAPI application
|   |
|   |-- worker/                  # Scheduled scans and paper trading
|
|-- packages/
|   |-- market_data/             # Binance public data client
|   |-- scanner/                 # Asset discovery and ranking
|   |-- indicators/              # Deterministic calculations
|   |-- market_structure/         # Swings, BOS, CHoCH
|   |-- liquidity/               # Liquidity levels and sweeps
|   |-- fvg/                     # Fair Value Gap detection
|   |-- strategy/                # Versioned strategy rules
|   |-- risk/                    # Risk and position calculations
|   |-- backtesting/             # Historical simulation
|   |-- paper_trading/           # Simulated trade lifecycle
|
|-- database/
|   |-- migrations/
|   |-- schema/
|
|-- tests/
|   |-- unit/
|   |-- integration/
|   |-- strategy/
|   |-- backtesting/
|
|-- docs/
|   |-- ARCHITECTURE.md
|   |-- STRATEGY_RULES.md
|   |-- DATA_DICTIONARY.md
|   |-- API.md
|   |-- TESTING.md
|   |-- DECISIONS.md
|
|-- scripts/
|-- docker-compose.yml
```

Do not create empty modules for every directory on day one. Introduce
components as their phase begins.

------------------------------------------------------------------------

## 11. Initial development milestones and acceptance criteria

### Milestone 1 --- Repository and data foundation

Deliver: - Monorepo setup. - Python environment and Next.js
application. - Configuration and environment-variable handling. -
Binance public market-data client. - Exchange-symbol discovery. -
Historical candle retrieval and validation. - Database migrations and
initial schema.

Acceptance: - Can retrieve eligible symbols and historical 1D/4H
candles. - Handles missing, duplicate, stale, and malformed data. - Has
automated tests for the data client and validation. - Does not require
private Binance API credentials.

### Milestone 2 --- Market scanner

Deliver: - Eligible-pair filtering. - 24-hour market ranking. -
Configurable shortlist. - Stored scan snapshots. - Basic scanner page.

Acceptance: - Ranking is reproducible from a saved market snapshot. -
Exclusions are visible and explainable. - A large 24-hour gain does not
automatically create a LONG signal.

### Milestone 3 --- Analysis engine

Deliver: - Confirmed swing detection. - Daily trend filter. - 4H
market-structure analysis. - Liquidity references and sweep detection. -
FVG detection and mitigation tracking. - Indicator calculations.

Acceptance: - Each calculation has unit tests and documented
definitions. - Results can be reproduced from the same candle data. - No
future data is used.

### Milestone 4 --- Strategy and signal engine

Deliver: - Versioned baseline LONG strategy. - Mandatory-condition
evaluation. - Entry, invalidation, stop and target calculations. -
Signal lifecycle and duplicate prevention. - Structured signal records.

Acceptance: - Every signal can be traced to its data and strategy
version. - Failed conditions produce `NO_TRADE` with reasons. - No
signal is shown as filled before the entry condition occurs.

### Milestone 5 --- Backtesting

Deliver: - Historical simulation. - Fees and slippage assumptions. -
Realistic entry and exit handling. - Performance reports. -
Out-of-sample evaluation.

Acceptance: - Tests cover look-ahead bias and ambiguous candle
outcomes. - Reports include assumptions and strategy version. - Results
can be reproduced.

### Milestone 6 --- Dashboard and paper trading

Deliver: - Market shortlist. - Asset analysis page. - Signal list and
signal details. - Candlestick charts. - Paper-trade tracking. -
Performance dashboard. - Clear stale-data and system-health indicators.

Acceptance: - User can inspect why a signal exists. - User can see
whether it is pending, active, invalidated, expired, or completed. - No
real orders can be submitted.

------------------------------------------------------------------------

## 12. Initial configuration

Keep operational and strategy settings in validated configuration files
or database records. Do not bury them in code.

Example configuration (values are placeholders until tested):

``` yaml
exchange:
  name: binance
  market: spot
  quote_asset: USDT

universe:
  max_candidates: 30
  min_quote_volume_24h: configurable
  excluded_assets: []

timeframes:
  context: 1d
  setup: 4h
  use_closed_candles: true

strategy:
  active_version: baseline-1.0
  direction: long_only
  minimum_reward_to_risk: configurable

risk:
  mode: paper
  simulated_equity: configurable
  risk_per_trade_percent: configurable
  max_open_positions: configurable

execution:
  real_orders_enabled: false
  paper_trading_enabled: true
```

The application must validate configuration at startup and fail clearly
when required settings are invalid.

------------------------------------------------------------------------

## 13. Security and operations

-   Keep secrets out of source control.
-   Provide `.env.example` with names and safe placeholders only.
-   Use no private exchange credentials in the initial release.
-   Validate all API inputs.
-   Apply sensible request timeouts and retry policies.
-   Respect Binance API rate limits.
-   Log errors without leaking secrets.
-   Add database backups before storing important long-term results.
-   Display data freshness and service health in the dashboard.
-   Make the system fail closed: uncertain or invalid data must not
    produce an actionable signal.

------------------------------------------------------------------------

## 14. First task for Codex or Claude Code

When this specification is added to the repository as `PROJECT_SPEC.md`,
give the coding agent the following instruction:

> Read `PROJECT_SPEC.md` completely and treat it as the primary project
> requirements document.
>
> Do not build the whole application immediately.
>
> First inspect the repository and report: 1. Existing files and current
> architecture. 2. Any existing implementation that should be preserved.
> 3. Conflicts, ambiguities, or missing decisions in the specification.
> 4. A proposed implementation plan for Milestone 1 only. 5. The files
> you intend to create or modify. 6. Tests and acceptance criteria for
> Milestone 1.
>
> Do not implement trading signals or strategy rules during this first
> task. Do not add real order execution or request exchange secrets.
>
> Wait for approval before making changes.

------------------------------------------------------------------------

## 15. Definition of done

The first usable release is complete when the application can:

1.  Scan eligible Binance USDT Spot markets.
2.  Rank active candidates using stored, timestamped market data.
3.  Analyze 1D context and 4H setups using documented deterministic
    rules.
4.  Produce explainable LONG signals or explicit `NO_TRADE` outcomes.
5.  Calculate and display entry zones, stop-loss, targets, and
    risk/reward.
6.  Backtest the exact versioned rules without look-ahead bias.
7.  Paper-trade and track signal outcomes.
8.  Show reproducible performance after costs.
9.  Explain every signal using evidence from the application.
10. Operate without placing real trades.

**The goal is not to generate the largest number of signals. The goal is
to discover whether a clearly defined strategy has a measurable,
repeatable edge.**
