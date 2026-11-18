# Contributing

Thank you for helping. This project values **honest measurement over attractive results**: a well-tested "this does not work"
is a welcome contribution.

## 1. Set up
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
python -m pytest tests -q                            # must pass before and after your change
```
Tests need no network and no database server (SQLite in memory).

## 2. Where does my change go?
| You want to... | Put it in | Add tests in |
|---|---|---|
| fetch or validate market data | `packages/market_data/` | `tests/unit/test_binance_*.py`, `test_candle_validator.py` |
| add an indicator | `packages/indicators/` | `tests/unit/test_analysis.py` |
| add a pattern detector (structure, liquidity, gaps) | `packages/market_structure/`, `liquidity/`, `fvg/` | `tests/unit/test_analysis.py` |
| add a strategy recipe | `packages/strategies/families.py` (+ `registry.py`) | `tests/unit/test_strategies.py` |
| change how trades are simulated | `packages/backtest/engine.py` | `tests/unit/test_backtest*.py`, `test_exit_plan.py` |
| add a learning feature | `packages/learning/dataset.py` | `tests/unit/test_learning.py` |
| add an API endpoint | `apps/api/main.py` | `tests/integration/test_api_endpoints.py` |
| add a command | `scripts/<verb>_<noun>.py` (thin: parse arguments, call `packages/`) | test the package function, not the script |
Business logic never lives in `scripts/` or `apps/`; they only call `packages/`.

## 3. Rules every pull request follows
1. **Paper only.** No order placement, no private API keys, no code path that could trade. `real_orders_enabled` must stay false.
2. **No look-ahead.** A feature or signal at candle t may use only candles that were closed at t. Add a test that proves it.
3. **Fail closed.** Bad or missing data means `NO_TRADE` or a skipped symbol, never a guess.
4. **Pre-register experiments.** Before running a new experiment, add an ADR to `docs/DECISIONS.md` with its fixed parameters and kill rule.
   Never change them after seeing the result. Negative results are recorded, not deleted.
5. **Numbers live in `config/default.yaml`** or as named constants marked PROVISIONAL, never as unexplained literals.
6. **English only** in code, comments, docs and commit messages.
7. Keep functions small and pure where possible; I/O at the edges (scripts, API, repositories).

## 4. Pull request checklist
- [ ] `python -m pytest tests -q` passes
- [ ] new behaviour has tests (including at least one failure case)
- [ ] a new feature or recipe passes `python scripts/bias_check.py` (no look-ahead)
- [ ] no secrets, keys or personal data in the diff
- [ ] an ADR is added if a decision or an experiment is involved
- [ ] the PR description says what changed and why, with evidence for any performance claim

## 5. Good first issues
Docs and tests are perfect first contributions: improving a docstring, adding an edge-case test, or making an error message clearer.
