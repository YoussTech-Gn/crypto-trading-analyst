"""Paper signals for the latest scan shortlist (public data only, no orders).

Usage:  python scripts/run_signals.py          (uses the latest stored scan; run scripts/run_scan.py first)
        python scripts/run_signals.py BTCUSDT SOLUSDT   (explicit symbols)
"""
from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.migrations.runner import apply_migrations
from database.session import create_connection
from packages.reporting import run_guarded
from packages.analysis import AnalysisEngine
from packages.backtest.memory import PatternMemory
from packages.config.settings import load_config
from packages.market_data.client import BinancePublicClient
from packages.market_data.validator import CandleValidator
from packages.scanner import ScannerRepository
from packages.signals import SignalGenerator, SignalRepository


def ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def main() -> int:
    cfg = load_config()
    conn = create_connection(cfg.database_url)
    try:
        apply_migrations(conn)
        symbols = [a.upper() for a in sys.argv[1:]]
        if not symbols:
            snap = ScannerRepository(conn).get_snapshot(None)
            if snap is None:
                print("No scan snapshot. Run: python scripts/run_scan.py")
                return 1
            symbols = [e.symbol for e in snap.shortlisted]
        now = datetime.now(timezone.utc)
        validator = CandleValidator(cfg.timeframes)
        engine = AnalysisEngine(cfg.analysis)
        gen = SignalGenerator(cfg.signals, cfg.strategy.minimum_reward_to_risk)
        repo = SignalRepository(conn)
        decisions = []
        with BinancePublicClient(cfg.exchange) as client:
            for sym in symbols:
                series, bad = {}, None
                for tf in ("1d", "4h"):
                    res = validator.validate(sym, tf, client.fetch_klines(sym, tf, limit=300 if tf == "1d" else 600))
                    if not res.analysis_allowed:
                        bad = f"{tf}:" + ",".join(sorted({i.code for i in res.issues})) if res.issues else tf
                        break
                    series[tf] = list(res.closed_candles)
                if bad:
                    last_open = int(now.timestamp() * 1000)
                    d = gen.no_data(sym, last_open - last_open % 14_400_000, bad)
                else:
                    d = gen.decide(engine.analyze(sym, series["1d"], series["4h"]).to_dict())
                repo.save(d, now)
                decisions.append(d)

        sigs = [d for d in decisions if d.decision == "SIGNAL"]
        print(f"analysed={len(decisions)}  SIGNAL={len(sigs)}  NO_TRADE={len(decisions) - len(sigs)}")
        memory = PatternMemory.load()
        for d in sigs:
            print(f"SIGNAL {d.symbol:<12} entry={d.entry:.6g} stop={d.stop:.6g} target={d.target:.6g} "
                  f"RR={d.risk_reward:.2f} valid_until={ts(d.valid_until_ms)} (paper only)")
            adv = memory.advise(dict(d.evidence.get("context", {})))
            print(f"   pattern-risk={adv['risk_level']}" + "".join(
                f"  [{a['flag']} {a['status']}: past avgR {a['avg_r_with']:+.2f} with vs {a['avg_r_without']:+.2f} without]"
                for a in adv["active"]))
        hist = Counter(r for d in decisions for r in d.reasons)
        print("Why NO_TRADE (count of symbols failing each check):")
        for reason, n in hist.most_common():
            print(f"  {n:>3}  {reason}")
        valid = [d for d in decisions if d.decision == "NO_TRADE" and not d.reasons[0].startswith("DATA_INVALID")]
        near = sorted(valid, key=lambda d: len(d.reasons))[:5]
        print("Closest to a signal (valid data only):")
        for d in near:
            print(f"  {d.symbol:<12} fails {len(d.reasons)}: {', '.join(d.reasons)}")
        bad = [d for d in decisions if d.reasons and d.reasons[0].startswith("DATA_INVALID")]
        if bad:
            print(f"Excluded for data (fail-closed, usually new listings): {', '.join(d.symbol for d in bad)}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(run_guarded("run_signals", main))
