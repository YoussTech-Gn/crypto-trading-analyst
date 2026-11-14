import React from "react";

export interface HealthResponse {
  status: string;
  timestamp_utc: string;
  milestone: string;
  exchange: {
    name: string;
    market: string;
    quote_asset: string;
  };
  timeframes: {
    context: string;
    setup: string;
    use_closed_candles: boolean;
    min_closed_candles_1d: number;
    min_closed_candles_4h: number;
    max_close_delay_seconds: number;
  };
  safety: {
    real_orders_enabled: boolean;
    paper_trading_enabled: boolean;
    direction: string;
  };
}

export default function HomePage() {
  return (
    <main
      style={{ maxWidth: "960px", margin: "0 auto", padding: "2.5rem 1.5rem" }}>
      <header
        style={{ borderBottom: "1px solid #1e293b", paddingBottom: "1.25rem" }}>
        <div
          style={{
            display: "inline-block",
            fontSize: "0.75rem",
            fontWeight: 600,
            letterSpacing: "0.06em",
            textTransform: "uppercase",
            color: "#38bdf8",
            backgroundColor: "#0f172a",
            border: "1px solid #1e293b",
            borderRadius: "4px",
            padding: "0.25rem 0.6rem",
            marginBottom: "0.75rem",
          }}>
          Milestone 1: Repository &amp; Data Foundation
        </div>
        <h1
          style={{
            margin: "0 0 0.5rem 0",
            fontSize: "1.85rem",
            color: "#f8fafc",
          }}>
          AI Crypto Trading Analyst
        </h1>
        <p style={{ margin: 0, color: "#94a3b8", lineHeight: 1.5 }}>
          Binance Spot (USDT) LONG-only swing analysis foundation. All strategy
          calculations and data integrity checks run deterministically in the
          FastAPI backend. Real order execution is permanently disabled.
        </p>
      </header>

      <section
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: "1rem",
          marginTop: "1.5rem",
        }}>
        <div
          style={{
            backgroundColor: "#111827",
            border: "1px solid #1f2937",
            borderRadius: "8px",
            padding: "1.25rem",
          }}>
          <h2 style={{ marginTop: 0, fontSize: "1rem", color: "#f1f5f9" }}>
            Market Scope &amp; Safety
          </h2>
          <ul
            style={{
              margin: 0,
              paddingLeft: "1.2rem",
              color: "#cbd5e1",
              lineHeight: 1.7,
            }}>
            <li>Exchange: Binance Spot (Public API only)</li>
            <li>Quote Asset: USDT</li>
            <li>Direction: LONG Only (Swing)</li>
            <li>Real Orders Enabled: false (Hard-locked)</li>
          </ul>
        </div>

        <div
          style={{
            backgroundColor: "#111827",
            border: "1px solid #1f2937",
            borderRadius: "8px",
            padding: "1.25rem",
          }}>
          <h2 style={{ marginTop: 0, fontSize: "1rem", color: "#f1f5f9" }}>
            Data Integrity Gates
          </h2>
          <ul
            style={{
              margin: 0,
              paddingLeft: "1.2rem",
              color: "#cbd5e1",
              lineHeight: 1.7,
            }}>
            <li>1D Context Min History: 200 closed candles</li>
            <li>4H Setup Min History: 500 closed candles</li>
            <li>Max Close Delay: 300s (5 minutes)</li>
            <li>Fail-Closed on Stale / Missing / Delayed Bars</li>
          </ul>
        </div>
      </section>
    </main>
  );
}
