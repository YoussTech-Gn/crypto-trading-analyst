# Backtest guide
Run: `python scripts/run_backtest.py` (default 25 liquid symbols, 730 days). Output: `reports/backtest_latest.txt` and `.json`.
Options: `--days 1000`, `--symbols BTCUSDT,ETHUSDT`, `--workers 4`.
Read the VERDICT line first. Fewer than 30 trades means INSUFFICIENT_SAMPLE. Then read the win-rate confidence interval, break-even win rate, per-symbol table and the count of unfilled signals that would have reached the target.

## Post-mortem and failure reports
The backtest report ends with a post-mortem: expected vs unexpected losses, lucky wins, entry-time flags and lessons (CONFIRMED_OUT_OF_SAMPLE, NOT_CONFIRMED, INSUFFICIENT_DATA). Full per-trade details are in `reports/backtest_latest.json`.
Any script that fails writes `reports/failure_<script>.txt` explaining what failed and whether it was expected.

## Funnel and experiment mode
The report prints a FUNNEL: for every check, how many analysed steps evaluated it and how many passed. It shows which gate limits the number of trades.
`python scripts/run_backtest.py --experiment-no-daily-gate` disables only the daily-trend filter (the report says EXPERIMENT) and splits trades by the daily regime at entry. It measures whether the filter adds value. It is not the strategy and writes `reports/backtest_experiment_no_daily_gate.txt`.
