# AI Crypto Trading Analyst

> **Paper trading and research only. Not financial advice.** This software never places orders, never asks for an exchange API key,
> and reads public Binance market data only. Nothing here is a recommendation to buy or sell anything.

An open, test-first research lab for crypto trading rules (Binance Spot, USDT pairs, long only, 4H setup with daily context).
Its goal is not to sell a "winning bot" but to answer honestly: **does a rule have an edge after fees, on data it has never seen?**

## What the project found so far
| Experiment | Result | Decision |
|---|---|---|
| 29 rule-based strategies (fair value gaps, liquidity sweeps, breakouts, pullbacks, RSI...) on 25 coins, 3 windows | none has a statistically supported edge after fees | [ADR-031](docs/DECISIONS.md) |
| Frozen top 3 on 25 coins never used before | all failed | [ADR-031](docs/DECISIONS.md) |
| Weekly relative-strength rotation | passed its own rules, failed stricter robustness checks | [ADR-032](docs/DECISIONS.md) |
| Machine learning on 640k candles (walk-forward) | real but tiny signal (AUC 0.515), below trading costs | [ADR-034](docs/DECISIONS.md) |
| Live paper journal | running since 2026-11-14 | [ADR-036](docs/DECISIONS.md) |

Every decision, with its evidence, is in [docs/DECISIONS.md](docs/DECISIONS.md). Negative results are kept on purpose.
How we guard against look-ahead, overfitting, lucky trade orders and edited records:
**[docs/HOW_WE_AVOID_FOOLING_OURSELVES.md](docs/HOW_WE_AVOID_FOOLING_OURSELVES.md)**. What is next: [ROADMAP.md](ROADMAP.md).

## Quick start (5 minutes)
Requirements: Python 3.11+, Git. Node 18+ only for the web app.
```bash
git clone <this repository>
cd crypto-trading-analyst
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env                    # Windows: copy .env.example .env
python -m pytest tests -q               # everything should pass, no network needed
```
After the first `overnight.py` run (it fills the local candle cache), check for look-ahead and warm-up bias any time, offline:
```bash
python scripts/bias_check.py
python scripts/forward_journal.py verify   # the live journal was not edited
```
Then, with internet access:
```bash
python scripts/run_scan.py              # rank today's liquid USDT pairs
python scripts/forward_journal.py scan  # live paper signals on the last closed 4H candle
python scripts/overnight.py             # the full research pass (download, lab, freeze, unseen-coin gate, report)
```

## Repository map
```
apps/api/            FastAPI read-only API (health, symbols, scans, signals, candles)
apps/web/            Next.js front end (status and scanner pages)
packages/
  config/            settings and validation (real orders are impossible by design)
  market_data/       Binance public client, symbol discovery, candle validator (fail closed)
  indicators/        EMA, ATR, RSI, ...
  market_structure/  swings, break of structure
  liquidity/         liquidity levels and sweeps
  fvg/               fair value gaps
  analysis/          one engine that turns candles into an analysis snapshot
  signals/           paper signal decisions (SIGNAL or NO_TRADE, with reasons)
  scanner/           liquidity/volume scanner
  backtest/          walk-forward backtester, exit plans, candle cache, metrics
  strategies/        strategy recipes, scorecard, freeze rule, portfolio
  learning/          M7 dataset and walk-forward learners
  journal/           forward paper journal
  reporting/         failure reports
database/            SQL migrations and connections (PostgreSQL or SQLite)
scripts/             command-line entry points (one file per job)
tests/unit|integration
docs/                decisions (ADRs), architecture, data dictionary, collaboration log
config/default.yaml  every tunable number, validated at start-up
```
More detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Older milestone notes: [docs/MILESTONES.md](docs/MILESTONES.md).

## Standing on the shoulders of
We studied these open-source projects and re-implemented some of their ideas in our own code (no code was copied; licenses differ):

| Project | Idea we adopted | Where |
|---|---|---|
| [Freqtrade](https://github.com/freqtrade/freqtrade) | look-ahead and recursive (warm-up) analysis | `scripts/bias_check.py` |
| [Jesse](https://github.com/jesse-ai/jesse) | trade-order shuffling Monte Carlo | `packages/backtest/robustness.py` |
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | hash-chained paper ledger | `packages/journal/forward.py` |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents), [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) | analyst debate, every number grounded in tool output | planned, see [ROADMAP.md](ROADMAP.md) |

What is different here: every experiment is pre-registered, confidence intervals are clustered by week and corrected for the number
of strategies tried, and unseen coins are a one-shot gate.

## Contributing
New contributors are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md); issues labelled `good first issue` are a good entry point.
The one rule that matters most: **an experiment's parameters and its pass/fail rule are written down before it runs, and never changed after
seeing the result.**

## Governance and maintainers
This is an owner-led, community-driven project. Anyone can propose improvements through issues and pull requests; trusted maintainers are appointed explicitly and receive only the access needed for their responsibilities.

- Read [GOVERNANCE.md](GOVERNANCE.md) for roles, review expectations, decision-making, and maintainer appointments.
- See [MAINTAINERS.md](MAINTAINERS.md) for the current maintainer roster.
- New contributors do not need write access: fork the repository and open a pull request.

Security problems: see [SECURITY.md](SECURITY.md). License: [MIT](LICENSE).
