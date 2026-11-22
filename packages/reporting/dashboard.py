"""Render the local dashboard (ADR-045): one self-contained HTML page, no server, no external files. Pure function."""

from __future__ import annotations

import html
from datetime import datetime, timezone

H4 = 14_400_000


def _utc(ms) -> str:
    return "never" if not ms else datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _e(x) -> str:
    return html.escape(str(x))


CSS = """
body{font-family:system-ui,Segoe UI,Arial,sans-serif;margin:0;background:#0f1419;color:#e6e6e6}
main{max-width:1100px;margin:auto;padding:16px}
h1{font-size:20px;margin:8px 0} h2{font-size:16px;margin:24px 0 8px;color:#9fb3c8;text-transform:uppercase;letter-spacing:.05em}
.card{background:#182029;border-radius:10px;padding:14px 16px;margin:8px 0}
.row{display:flex;flex-wrap:wrap;gap:12px} .row .card{flex:1;min-width:200px}
.big{font-size:22px;font-weight:600} .muted{color:#8a99a8;font-size:13px}
.ok{color:#4cd38a} .bad{color:#ff6b6b} .warn{color:#f5c04a}
table{width:100%;border-collapse:collapse;font-size:14px} th,td{padding:6px 8px;border-bottom:1px solid #26313c;text-align:left}
th{color:#9fb3c8;font-weight:500} td.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;background:#26313c}
.sig{background:#1f4d33;color:#7ff0b0} .one{background:#4d421f;color:#f5d67a}
code{background:#0b0f13;padding:2px 6px;border-radius:4px;font-size:12px;word-break:break-all}
"""


def render(view: dict | None, view_stale: bool, records: list[dict], health: dict, review_lines: list[str],
           chain: dict, now_ms: int) -> str:
    last_ok = health.get("last_scan_ok_ms")
    age_h = (now_ms - last_ok) / 3_600_000 if last_ok else None
    health_cls = "ok" if age_h is not None and age_h < 2 else ("warn" if age_h is not None and age_h < 6 else "bad")
    waiting = [r for r in records if (r.get("owner") or {}).get("decision") is None and now_ms <= r["candle_open_ms"] + 2 * H4]
    P = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
         f"<meta http-equiv='refresh' content='300'><title>Crypto analyst dashboard</title><style>{CSS}</style></head><body><main>",
         f"<h1>Crypto analyst - paper dashboard</h1><div class='muted'>Updated {_e(_utc(now_ms))} - refreshes every 5 minutes. "
         "Paper research only, not financial advice; nothing here places orders.</div>"]
    # status cards
    sig_now = len(view["signals"]) if view else 0
    P.append("<div class='row'>")
    P.append(f"<div class='card'><div class='muted'>System health</div><div class='big {health_cls}'>"
             f"{'OK' if health_cls == 'ok' else ('LATE' if health_cls == 'warn' else 'NO DATA')}</div>"
             f"<div class='muted'>last good scan {_e(_utc(last_ok))}<br>failed runs in 24h: {_e(health.get('failures_24h', 0))}"
             f"<br>data host: {_e(health.get('host', 'api.binance.com'))}</div></div>")
    if view:
        P.append(f"<div class='card'><div class='muted'>Bitcoin daily trend</div><div class='big {'ok' if view['btc_up'] else 'bad'}'>"
                 f"{'UP' if view['btc_up'] else 'DOWN'}</div><div class='muted'>{_e(view['btc_trend'])}</div></div>")
        P.append(f"<div class='card'><div class='muted'>Coins in a daily uptrend</div><div class='big'>{len(view['up'])} / {view['coins']}</div>"
                 f"<div class='muted'>{_e(', '.join(view['up']) or 'none')}</div></div>")
    P.append(f"<div class='card'><div class='muted'>Signals now / waiting for you</div><div class='big'>{sig_now} / {len(waiting)}</div>"
             f"<div class='muted'>journal: {len(records)} signals recorded</div></div></div>")
    # waiting decisions
    if waiting:
        P.append("<h2>Waiting for your decision (4 hours after the candle close)</h2>")
        for r in waiting:
            P.append(f"<div class='card'><span class='pill sig'>SIGNAL</span> <b>{_e(r['symbol'])}</b> {_e(r['recipe'])} - entry "
                     f"{r['entry']:.6g}, stop {r['stop']:.6g}, target {r['target']:.6g}<div class='muted'>For: "
                     f"{_e('; '.join(r.get('reasons_for', [])))}<br>Against: {_e('; '.join(r.get('reasons_against', [])))}</div>"
                     f"<code>python scripts/forward_journal.py decide {_e(r['id'])} taken --price P --mood 3</code><br>"
                     f"<code>python scripts/forward_journal.py decide {_e(r['id'])} skipped --mood 3</code></div>")
    # market
    P.append("<h2>Market now</h2>")
    if not view:
        P.append("<div class='card bad'>Market data unavailable (no internet or Binance unreachable). Nothing is guessed.</div>")
    else:
        if view_stale:
            P.append("<div class='card warn'>Showing the last saved market view - the live fetch failed this hour.</div>")
        P.append(f"<div class='muted'>Last closed 4H candle: {_e(_utc(view['last_close_ms']))}</div>")
        if view["close_calls"]:
            P.append("<div class='card'><b>One condition away from a signal</b><ul>"
                     + "".join(f"<li>{_e(c['coin'])} - {_e(c['rule'])}: only {_e(c['missing'])}</li>" for c in view["close_calls"])
                     + "</ul><div class='muted'>A count of conditions, not a probability.</div></div>")
        P.append("<div class='card'><table><tr><th>Coin</th><th class='num'>Price</th><th>Daily trend</th>"
                 + "".join(f"<th>{_e(h)}</th>" for h in view["rule_heads"]) + "</tr>")
        for row in view["rows"]:
            cells = "".join(f"<td><span class='pill {'sig' if c == 'SIGNAL' else ('one' if c.startswith('1 ') else '')}'>{_e(c)}</span></td>"
                            for c in row["cells"])
            P.append(f"<tr><td><b>{_e(row['coin'])}</b></td><td class='num'>{row['price']:.6g}</td>"
                     f"<td class='{'ok' if row['trend'].startswith('UP') else 'bad'}'>{_e(row['trend'])}</td>{cells}</tr>")
        P.append("</table><div class='muted'>Each rule signals only when ALL its conditions are true at a 4H close. "
                 "BREAKOUT55 = close above the 55-candle high; BREAKOUT20+BTC = close above the 20-candle high while Bitcoin trends up; "
                 "FALSE-BREAK = a wick below a low that closes back above it.</div></div>")
    # journal
    P.append("<h2>Journal</h2><div class='card'>")
    if records:
        P.append("<table><tr><th>Candle</th><th>Coin</th><th>Rule</th><th>Status</th><th class='num'>R</th><th>Your decision</th></tr>")
        for r in sorted(records, key=lambda x: -x["candle_open_ms"])[:30]:
            res = r.get("result_r")
            P.append(f"<tr><td>{_e(r.get('candle', ''))}</td><td>{_e(r['symbol'])}</td><td>{_e(r['recipe'])}</td><td>{_e(r['status'])}</td>"
                     f"<td class='num {'ok' if (res or 0) > 0 else ('bad' if res is not None else '')}'>{'' if res is None else f'{res:+.2f}'}</td>"
                     f"<td>{_e((r.get('owner') or {}).get('decision') or '-')}</td></tr>")
        P.append("</table>")
    else:
        P.append("No signal recorded yet. The rules wait for a daily uptrend; this is expected in a falling market.")
    P.append(f"<div class='muted'>Integrity: {'OK' if chain.get('ok') else 'BROKEN'} - {chain.get('chained', 0)} chained signals"
             f" - head {_e(str(chain.get('head', ''))[:16])}</div></div>")
    if review_lines:
        P.append("<h2>Review</h2><div class='card'><pre style='white-space:pre-wrap;margin:0'>" + _e("\n".join(review_lines)) + "</pre></div>")
    P.append("</main></body></html>")
    return "\n".join(P)
