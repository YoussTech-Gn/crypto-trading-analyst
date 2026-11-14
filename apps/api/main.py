"""FastAPI application for Milestone 1: Repository & Data Foundation.

Exposes read-only health, configuration summary, symbol universe, and candle validation
inspection endpoints. Strictly enforces startup configuration validation and safety boundaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from database.migrations.runner import apply_migrations
from database.session import DatabaseConnection, create_connection
from packages.config.settings import AppConfig, load_config
from packages.market_data.repository import MarketDataRepository
from packages.scanner.models import ScanSnapshot
from packages.scanner.repository import ScannerRepository
from packages.signals.repository import SignalRepository


def create_app(
    config: AppConfig | None = None,
    db_conn: DatabaseConnection | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    validated_config = config or load_config()

    app = FastAPI(
        title="AI Crypto Trading Analyst API",
        version="0.1.0",
        description=(
            "Milestone 1: Repository and Data Foundation. "
            "Read-only Binance Spot USDT market data foundation (no real order execution)."
        ),
    )
    app.state.config = validated_config
    app.state.db_conn = db_conn

    @app.get("/api/v1/health")
    def get_health() -> Any:
        cfg: AppConfig = app.state.config
        try:
            conn: DatabaseConnection | None = app.state.db_conn
            if conn is None:
                conn = create_connection(cfg.database_url)
                apply_migrations(conn)
                app.state.db_conn = conn
            probe = conn.fetchone_dict("SELECT 1 AS ok")
            if not probe or probe.get("ok") != 1:
                raise RuntimeError("database probe returned an unexpected result")
        except Exception as exc:  # fail closed: report unhealthy instead of a false "ok"
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "database": "error",
                    "detail": type(exc).__name__,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                },
            )
        return {
            "status": "ok",
            "database": "ok",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "milestone": "Milestone 1 - Repository and Data Foundation",
            "exchange": {
                "name": cfg.exchange.name,
                "market": cfg.exchange.market,
                "quote_asset": cfg.exchange.quote_asset,
            },
            "timeframes": {
                "context": cfg.timeframes.context,
                "setup": cfg.timeframes.setup,
                "use_closed_candles": cfg.timeframes.use_closed_candles,
                "min_closed_candles_1d": cfg.timeframes.min_closed_candles_1d,
                "min_closed_candles_4h": cfg.timeframes.min_closed_candles_4h,
                "max_close_delay_seconds": cfg.timeframes.max_close_delay_seconds,
            },
            "safety": {
                "real_orders_enabled": cfg.execution.real_orders_enabled,
                "paper_trading_enabled": cfg.execution.paper_trading_enabled,
                "direction": cfg.strategy.direction,
            },
        }

    @app.get("/api/v1/config")
    def get_config_summary() -> dict[str, Any]:
        cfg: AppConfig = app.state.config
        return {
            "exchange": cfg.exchange.model_dump(),
            "universe": cfg.universe.model_dump(),
            "timeframes": cfg.timeframes.model_dump(),
            "strategy": cfg.strategy.model_dump(),
            "risk": cfg.risk.model_dump(),
            "execution": cfg.execution.model_dump(),
        }

    @app.get("/api/v1/symbols")
    def list_discovered_symbols(
        eligible_only: bool = Query(default=True, description="Return only eligible symbols"),
    ) -> dict[str, Any]:
        conn: DatabaseConnection | None = app.state.db_conn
        if conn is None:
            conn = create_connection(app.state.config.database_url)
            apply_migrations(conn)
            app.state.db_conn = conn

        repo = MarketDataRepository(conn)
        symbols = repo.list_symbols(eligible_only=eligible_only)
        return {
            "count": len(symbols),
            "eligible_only": eligible_only,
            "symbols": [
                {
                    "symbol": s.symbol,
                    "base_asset": s.base_asset,
                    "quote_asset": s.quote_asset,
                    "exchange_status": s.exchange_status,
                    "is_spot_trading_allowed": s.is_spot_trading_allowed,
                    "is_eligible": s.is_eligible,
                    "exclusion_reasons": list(s.exclusion_reasons),
                    "evaluated_at_utc": s.evaluated_at_utc.isoformat(),
                }
                for s in symbols
            ],
        }

    def _serialize_snapshot(
        snap: ScanSnapshot, status: str | None, category: str | None = None
    ) -> dict[str, Any]:
        wanted = category.strip().upper() if category else None
        entries = [
            e for e in snap.entries
            if (status is None or e.status == status) and (wanted is None or e.category == wanted)
        ]
        return {
            "snapshot_id": snap.snapshot_id,
            "created_at_utc": snap.created_at_utc.isoformat(),
            "scanner_version": snap.scanner_version,
            "params": snap.params,
            "categories": sorted({e.category for e in snap.entries}),
            "counts": {
                "evaluated": len(snap.entries),
                "ranked": sum(1 for e in snap.entries if e.rank is not None),
                "shortlisted": len(snap.shortlisted),
                "non_target_quote_skipped": snap.non_target_quote_skipped,
            },
            "note": "Scanner output lists assets to investigate. It is not a trading signal.",
            "entries": [
                {
                    "symbol": e.symbol,
                    "status": e.status,
                    "category": e.category,
                    "rank": e.rank,
                    "quote_volume": e.quote_volume,
                    "price_change_percent": e.price_change_percent,
                    "spread_bps": e.spread_bps,
                    "exclusion_reasons": list(e.exclusion_reasons),
                }
                for e in entries
            ],
        }

    def _scan_repo() -> ScannerRepository:
        conn: DatabaseConnection | None = app.state.db_conn
        if conn is None:
            conn = create_connection(app.state.config.database_url)
            apply_migrations(conn)
            app.state.db_conn = conn
        return ScannerRepository(conn)

    @app.get("/api/v1/scans/latest")
    def get_latest_scan(
        status: str | None = Query(default=None, pattern="^(SHORTLISTED|RANKED_NOT_SHORTLISTED|EXCLUDED)$"),
        category: str | None = Query(default=None, max_length=32),
    ) -> dict[str, Any]:
        snap = _scan_repo().get_snapshot(None)
        if snap is None:
            raise HTTPException(status_code=404, detail="No scan snapshots stored yet.")
        return _serialize_snapshot(snap, status, category)

    @app.get("/api/v1/scans/{snapshot_id}")
    def get_scan(
        snapshot_id: str,
        status: str | None = Query(default=None, pattern="^(SHORTLISTED|RANKED_NOT_SHORTLISTED|EXCLUDED)$"),
        category: str | None = Query(default=None, max_length=32),
    ) -> dict[str, Any]:
        snap = _scan_repo().get_snapshot(snapshot_id)
        if snap is None:
            raise HTTPException(status_code=404, detail="Scan snapshot not found.")
        return _serialize_snapshot(snap, status, category)

    @app.get("/api/v1/signals")
    def get_signals(
        decision: str | None = Query(default=None, pattern="^(SIGNAL|NO_TRADE)$"),
        symbol: str | None = Query(default=None, max_length=32),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> dict[str, Any]:
        conn: DatabaseConnection | None = app.state.db_conn
        if conn is None:
            conn = create_connection(app.state.config.database_url)
            apply_migrations(conn)
            app.state.db_conn = conn
        rows = SignalRepository(conn).list_recent(decision, symbol, limit)
        return {
            "note": "Paper-only decisions. Not financial advice. No orders are placed.",
            "count": len(rows),
            "decisions": rows,
        }

    @app.get("/api/v1/candles/{symbol}/{timeframe}")
    def get_stored_candles(
        symbol: str = Path(..., pattern="^[A-Za-z0-9]{2,20}$"),
        timeframe: str = Path(..., max_length=4),
        limit: int = Query(default=200, ge=1, le=2000),
    ) -> dict[str, Any]:
        tf = timeframe.strip().lower()
        if tf not in ("1d", "4h"):
            raise HTTPException(
                status_code=400,
                detail="Unsupported timeframe. Expected '1d' or '4h'.",
            )
        conn: DatabaseConnection | None = app.state.db_conn
        if conn is None:
            conn = create_connection(app.state.config.database_url)
            apply_migrations(conn)
            app.state.db_conn = conn

        repo = MarketDataRepository(conn)
        candles = repo.get_candles(symbol=symbol, timeframe=tf, limit=limit)
        latest_validation = repo.get_latest_validation_run(symbol=symbol, timeframe=tf)

        return {
            "symbol": symbol.strip().upper(),
            "timeframe": tf,
            "count": len(candles),
            "latest_validation": latest_validation,
            "candles": [
                {
                    "open_time_ms": c.open_time_ms,
                    "close_time_ms": c.close_time_ms,
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "quote_volume": c.quote_volume,
                    "trade_count": c.trade_count,
                }
                for c in candles
            ],
        }

    return app
