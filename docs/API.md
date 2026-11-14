# API Reference (Milestone 1)

All Milestone 1 endpoints are read-only and expose system health, validated configuration, discovered symbols, and stored closed candles.

## `GET /api/v1/health`
Returns service status, active milestone, exchange scope, timeframe validation parameters, and safety flags (`real_orders_enabled: false`).

## `GET /api/v1/config`
Returns the active, validated `AppConfig` structure loaded from `config/default.yaml` and environment overrides.

## `GET /api/v1/symbols?eligible_only=true`
Returns discovered symbols persisted in the `symbols` table along with `is_eligible` and `exclusion_reasons`.

## `GET /api/v1/candles/{symbol}/{timeframe}?limit=200`
Returns chronologically ordered closed candles (`1d` or `4h`) for `{symbol}` along with the most recent `data_validation_runs` audit record.

## Scanner (Milestone 2)
* `GET /api/v1/scans/latest[?status=SHORTLISTED|RANKED_NOT_SHORTLISTED|EXCLUDED]` - latest stored scan snapshot (404 if none).
* `GET /api/v1/scans/{snapshot_id}[?status=...]` - a specific snapshot (404 if unknown).
Response: `snapshot_id`, `created_at_utc`, `scanner_version`, `params`, `counts`, `note`, `entries[]` (`symbol`, `status`, `rank`, `quote_volume`, `price_change_percent`, `spread_bps`, `exclusion_reasons`). Output is a list of assets to investigate, never a trading signal.
`GET /api/v1/health` now also returns `database: "ok"` and HTTP 503 when the database check fails.

## GET /api/v1/signals
Query: `decision` (SIGNAL or NO_TRADE), `symbol`, `limit` (1-500). Returns stored paper decisions with reasons, checks and evidence. Not financial advice.
