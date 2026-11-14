# Architecture

## Data flow
```
Binance public REST ──> market_data (client, validator: closed candles only, fail closed)
        │                     │
        │                     └──> backtest/cache.py (data/cache, offline replay)
        v
analysis/engine.py  ── indicators, market_structure, liquidity, fvg ──> one analysis snapshot (dict)
        │
        ├──> signals/ (default generator)          ─┐
        ├──> strategies/ (29 recipes, registry)     ├──> SignalDecision: SIGNAL or NO_TRADE + reasons
        │                                          ─┘
        ├──> backtest/engine.py  walk-forward replay, simulate_order (fills, stop wins ties, fees, exit plans)
        │        └──> strategies/scorecard.py, freeze.py, portfolio.py  (scores, pre-registered freeze, combination)
        ├──> learning/  one row per candle, walk-forward learners, metrics
        └──> journal/forward.py  live paper signals, settled by the SAME simulate_order as the backtest
```

## Layers and the one rule between them
| Layer | Folders | May do I/O? |
|---|---|---|
| Domain logic (pure, tested) | `packages/*` except repositories and clients | no |
| Adapters | `packages/market_data/client.py`, `*/repository.py`, `database/`, `backtest/cache.py` | yes |
| Entry points | `scripts/*.py`, `apps/api`, `apps/web` | yes, and only call `packages/` |
Logic is never duplicated between a script and a package: live journal settlement and the backtest call the same function.

## Safety boundaries (enforced in code, covered by tests)
1. Public data only; the client has no key or secret fields.
2. `ExecutionConfig.real_orders_enabled` must be false or start-up fails.
3. Closed candles only; the validator separates the forming candle and fails closed on gaps, duplicates, stale or malformed data.
4. Every experiment is pre-registered in `docs/DECISIONS.md`; the `alt` symbol gate is one-shot (`knowledge/alt_gate.json`).

## State on disk
| Path | What | Public? |
|---|---|---|
| `config/default.yaml` | every tunable number | yes |
| `knowledge/*.json` | trial ledger, frozen candidates, alt gate, pattern memory | yes |
| `knowledge/forward_journal.jsonl` | the owner's live decisions | no (ignored) |
| `reports/*.txt` | human-readable results | yes |
| `reports/*.json`, `data/cache/` | large, re-creatable | no (ignored) |

Milestone-1 detail (validator states, original API boundary): [ARCHITECTURE_M1.md](ARCHITECTURE_M1.md).
