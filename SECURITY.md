# Security policy

## Design guarantees
* Public market data only: the Binance client calls public endpoints and accepts no API key or secret.
* No order execution exists in the code; configuration validation rejects `real_orders_enabled: true`.
* The local database and API bind to this computer only by default (`127.0.0.1`).

## Reporting a vulnerability
Please do **not** open a public issue for a security problem. Use GitHub's "Report a vulnerability" (Security tab, private
advisory) with steps to reproduce. You will get an answer within 7 days.

## Never commit
`.env` files, API keys of any exchange, database URLs with real passwords, `knowledge/forward_journal.jsonl` (personal trading
notes), or downloaded candle caches (`data/`). These paths are already in `.gitignore`.
