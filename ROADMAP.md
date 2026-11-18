# Roadmap

Ordered by value. Every research item needs a pre-registered ADR before it runs. Items marked **good first issue** need no
trading knowledge.

## Now
- Collect 100 closed live paper signals per tracked recipe; verdict per ADR-036 (no code needed, only time).
- Weekly: commit `reports/forward_review.txt` so the journal's chain head is anchored in Git history (ADR-041).

## Next (contributions welcome)
- Web page for the forward journal: each signal with its reasons for and against, and Taken / Skipped buttons (`apps/web`).
- Fix the warm-up of `atr_pct_rank200` found by `bias_check` (rank only real ATR values). **good first issue**
- Run `bias_check` in CI on a small committed sample of candles. **good first issue**
- Candle-perturbation Monte Carlo (re-run a recipe on slightly modified candles), the second Jesse method.

## Research (each needs an ADR first)
- A survivorship-free coin universe (include delisted coins) to re-test weekly rotation (ADR-032).
- Feature group FG2 for the learning engine: taker-buy share, funding rate, open interest; judged by its gain over FG1 (ADR-034).
- An "analyst committee" (bull, bear, risk judge) that explains signals, where every number must come from the engine's own
  output (ideas from TradingAgents and Vibe-Trading). It explains; it never decides or sizes risk.

## Later
- An MCP server so AI assistants can run backtests and read the scorecard (idea from Jesse and Vibe-Trading).
- A frozen benchmark dataset and leaderboard: "beat the baseline on unseen coins".

## Never
- Placing orders or holding exchange API keys with trading or withdrawal rights.
