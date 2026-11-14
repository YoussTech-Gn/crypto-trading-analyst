import React from "react";

interface ScanEntry {
  symbol: string;
  status: string;
  category: string;
  rank: number | null;
  quote_volume: number | null;
  price_change_percent: number | null;
  spread_bps: number | null;
  exclusion_reasons: string[];
}

interface ScanResponse {
  snapshot_id: string;
  created_at_utc: string;
  scanner_version: string;
  counts: { evaluated: number; ranked: number; shortlisted: number; non_target_quote_skipped: number };
  note: string;
  categories: string[];
  entries: ScanEntry[];
}

const API_BASE = process.env.API_BASE_URL ?? "http://localhost:8000";

async function loadScan(category?: string): Promise<{ data?: ScanResponse; error?: string }> {
  try {
    const qs = category ? `?category=${encodeURIComponent(category)}` : "";
    const res = await fetch(`${API_BASE}/api/v1/scans/latest${qs}`, { cache: "no-store" });
    if (res.status === 404) return { error: "No scan stored yet. Run: python scripts/run_scan.py" };
    if (!res.ok) return { error: `API returned HTTP ${res.status}` };
    return { data: (await res.json()) as ScanResponse };
  } catch {
    return { error: "API unreachable. Start it with: uvicorn apps.api.main:app" };
  }
}

const cell: React.CSSProperties = { padding: "0.4rem 0.6rem", borderBottom: "1px solid #1e293b", textAlign: "left" };

function Table({ rows, excluded }: { rows: ScanEntry[]; excluded?: boolean }) {
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", color: "#e2e8f0", fontSize: "0.9rem" }}>
      <thead>
        <tr style={{ color: "#94a3b8" }}>
          <th style={cell}>{excluded ? "" : "#"}</th>
          <th style={cell}>Symbol</th>
          <th style={cell}>Category</th>
          <th style={cell}>24h quote volume</th>
          <th style={cell}>24h change (info only)</th>
          <th style={cell}>Spread (bps)</th>
          {excluded && <th style={cell}>Exclusion reasons</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((e) => (
          <tr key={e.symbol}>
            <td style={cell}>{e.rank ?? ""}</td>
            <td style={cell}>{e.symbol}</td>
            <td style={cell}>{e.category}</td>
            <td style={cell}>{e.quote_volume === null ? "n/a" : Math.round(e.quote_volume).toLocaleString("en-US")}</td>
            <td style={cell}>{e.price_change_percent === null ? "n/a" : `${e.price_change_percent.toFixed(2)}%`}</td>
            <td style={cell}>{e.spread_bps === null ? "n/a" : e.spread_bps.toFixed(2)}</td>
            {excluded && <td style={cell}>{e.exclusion_reasons.join(", ")}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default async function ScannerPage({
  searchParams,
}: {
  searchParams?: { category?: string };
}) {
  const category = searchParams?.category;
  const { data, error } = await loadScan(category);
  const shortlisted = data?.entries.filter((e) => e.status === "SHORTLISTED") ?? [];
  const excluded = data?.entries.filter((e) => e.status === "EXCLUDED") ?? [];
  return (
    <main style={{ maxWidth: "1100px", margin: "0 auto", padding: "2rem 1.5rem", color: "#e2e8f0" }}>
      <h1 style={{ color: "#f8fafc" }}>Market Scanner</h1>
      {error && <p style={{ color: "#fbbf24" }}>{error}</p>}
      {data && (
        <>
          <p style={{ color: "#94a3b8" }}>
            Snapshot {data.snapshot_id} · {data.created_at_utc} · {data.scanner_version}. {data.note}
          </p>
          <p>
            Category:{" "}
            <a href="/scanner" style={{ color: "#38bdf8" }}>ALL</a>
            {data.categories.map((c) => (
              <span key={c}> · <a href={`/scanner?category=${c}`} style={{ color: "#38bdf8" }}>{c}</a></span>
            ))}
          </p>
          <h2>Shortlist ({shortlisted.length})</h2>
          <Table rows={shortlisted} />
          <h2 style={{ marginTop: "2rem" }}>Excluded ({excluded.length})</h2>
          <Table rows={excluded} excluded />
        </>
      )}
    </main>
  );
}
