# How we avoid fooling ourselves

Most trading backtests look better than reality. This page lists every trap we know, the guard in this repository, and where
the guard lives in the code. If you find a trap that is not on this list, that is one of the most valuable issues you can open.

| Trap | What goes wrong | Our guard | Where |
|---|---|---|---|
| Look-ahead | a signal or feature uses a candle that had not closed yet | closed candles only; automatic check that every learning feature is identical when the future is cut off | `packages/market_data/validator.py`, `packages/backtest/bias.py`, `scripts/bias_check.py`, `tests/unit/test_bias.py` |
| Warm-up (recursive indicators) | an EMA/ATR/RSI value depends on how much history came before it | the same check with 200/500/1000 startup candles, and recipe decisions compared on 600 vs 900 candle windows | `packages/backtest/bias.py` |
| Bad data | gaps, duplicates, stale or truncated candles | the validator fails closed: the symbol is skipped, never guessed | `packages/market_data/validator.py` |
| Optimistic fills | assuming a limit order fills, or that the target is hit before the stop in the same candle | limit fills only when price trades through; when one candle touches both, the stop wins | `packages/backtest/engine.py` (`simulate_order`) |
| Ignoring costs | profits that disappear after fees | 0.1% fee per side and 0.05% slippage on stops, reported in R (`avg_fee_r`) | `config/default.yaml`, `packages/backtest/engine.py` |
| Overfitting to the past | tuning until the backtest looks good | three separate 2-year windows; walk-forward for learning; parameters marked PROVISIONAL and never tuned on results | `scripts/run_lab.py`, `packages/learning/model.py` |
| Many tries, one lucky winner | testing 29 ideas and keeping the best by chance | the confidence bar rises with every recipe ever tried (Bonferroni over `knowledge/lab_trials.json`) | `packages/strategies/scorecard.py` |
| Trades that move together | 20 coins falling on one day counted as 20 independent results | confidence intervals clustered by calendar week | `packages/backtest/metrics.py` |
| A lucky order of trades | a drawdown that only looks small because losses were spread out | trade-order shuffling Monte Carlo (1000 scenarios), reported as a lower bound | `packages/backtest/robustness.py` |
| Peeking at the holdout | using "unseen" data to choose, then calling it a test | the alt basket gate runs once, after a pre-registered freeze, and refuses to run again | `packages/strategies/freeze.py`, `knowledge/alt_gate.json` |
| Moving the goalposts | changing the pass rule after seeing the result | every experiment is written as an ADR before it runs | `docs/DECISIONS.md` |
| Rewriting the live record | quietly editing past signals or decisions | the forward journal is hash-chained; decisions are sealed 4 hours after the candle; `forward_journal.py verify` | `packages/journal/forward.py` |
| Selective memory | logging only the trades you liked | every signal is recorded, including skipped ones and ones that arrived while you were away (`absent`) | `packages/journal/forward.py` |
| Survivorship | testing only coins that still exist today | known and NOT fixed yet: the cache holds coins listed in Nov 2026; results are upper bounds (ADR-032) | open issue |

Our negative results (no recipe with an edge, ML AUC 0.515) are published on purpose: a method that can say "no" is the only
method whose "yes" means anything.
