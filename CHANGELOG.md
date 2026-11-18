# Changelog

Dates are UTC. Each entry links the decision record that explains it. Contributors are credited by GitHub handle.

## Unreleased
### Added
- Trade-order shuffling Monte Carlo in every lab scorecard (drawdown distribution, 1000 scenarios). Idea from Jesse. (ADR-041)
- `scripts/bias_check.py`: look-ahead and warm-up checks for learning features and recipe decisions. Idea from Freqtrade's
  lookahead/recursive analysis. Found one small warm-up issue in `atr_pct_rank200` (first ~14 rows per symbol). (ADR-041)
- Tamper-evident forward journal: hash chain, sealed decisions, `forward_journal.py verify`. Idea from ai-hedge-fund. (ADR-041)
- `docs/HOW_WE_AVOID_FOOLING_OURSELVES.md`, `ROADMAP.md`, this changelog.

## 2026-11-15
### Added
- Public release: MIT license, contributor guide, security policy, CI on Python 3.11 and 3.12, governance. (ADR-039)
- Forward journal: backfill of missed 4H candles (ADR-038), `absent` decisions (ADR-037), live paper journal (ADR-036).

## 2026-11-14
### Research results
- 29 recipes, frozen top 3 on unseen coins: no edge after fees (ADR-031). Weekly rotation rejected (ADR-032).
  Learning engine on 640k candles: AUC 0.515, below costs (ADR-034).
