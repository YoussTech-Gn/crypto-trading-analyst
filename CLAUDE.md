# CLAUDE.md - read this first (Claude Code loads it automatically)

## The project
AI Crypto Trading Analyst: Binance Spot USDT, LONG only, 1D context / 4H setup, public data only, PAPER ONLY (never send an order,
never ask for an API key with trading or withdrawal rights). Full spec: `PROJECT_SPEC.md`.
The code is the analyst; the owner (Youssef) decides and executes by hand. LLMs explain signals; they never predict prices or size risk.

## Rules that are never broken
1. Every decision goes into `docs/DECISIONS.md` as an ADR (date, evidence, files). Read its index and the last ADRs before working.
2. Pre-register before running: parameters and the kill rule are written in an ADR BEFORE an experiment runs; never change them after
   seeing a result. Extra checks added after a result may only make the test stricter.
3. A backtest result needs >= 30 trades to be read at all; every failure produces a report (`reports/failure_*.txt`).
4. No Arabic in any project file (code, docs, reports). Talk to the owner in Arabic.
5. The `alt` basket gate is spent (ADR-026, ADR-031, `knowledge/alt_gate.json`); do not rerun it.
6. Run the tests before saying something works: `.venv\Scripts\python -m pytest tests -q` on Windows (`python -m pytest tests -q` inside an active venv)

## Where things stand (2026-11-14)
* Strategy lab: 29 recipes, none with an edge after fees (ADR-031). Daily rotation H1 rejected (ADR-032).
* Learning engine M7-FG1 (OHLCV, walk-forward): AUC 0.513/0.515, below trading costs, rejected (ADR-034).
* NOW: live paper measurement (ADR-036) with `brk55_trail`, `brk20_btc_trail`, `sweep_only` (the owner's false-break-of-a-low rule):
  `python scripts/forward_journal.py scan | settle | list | decide ID taken|skipped|absent --price --mood --note | review`.
  Decisions only within 4h of the candle close; after that the signal becomes `absent` automatically and is frozen (ADR-037).
  `scan` backfills every missed closed 4H candle (max 7 days, never before 2026-11-14 12:00 UTC); older misses are gaps (ADR-038).
  Journal: `knowledge/forward_journal.jsonl`. Verdicts only at 100 and 200 closed signals per recipe.
  Scan state: `knowledge/forward_scan_state.json`.
* Collaboration with Gemini: `docs/COLLAB.md` (append-only threads T-1..T-3, open questions in T-2 and T-3);
  `python scripts/collab_loop.py` alternates Gemini and Claude CLIs (ADR-035).

## Open items
* First commit and public push (ADR-039 prepared everything; the owner pushes).
* Kill rule for the forward journal: DONE. The owner accepted ADR-036's rule unchanged for all 3 recipes on 2026-11-15; it is frozen.
* Possible next research (needs an ADR first): FG2 features (taker-buy share, funding, open interest) judged by gain over FG1;
  a survivorship-free universe for rotation.
* Automate `scan` + `settle` every 4 hours (Windows Task Scheduler) - not done yet.

## Open-source layout
See README.md (map), CONTRIBUTING.md (rules for contributors), SECURITY.md, docs/ARCHITECTURE.md. CI runs the tests on every push (.github/workflows/ci.yml).

## How to talk to the owner
Arabic, direct, no flattery. Concrete example first, then the explanation, then the simple version, then the engineering secret,
and end with one challenge question. Give him one concrete next action, not a menu.
