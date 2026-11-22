"""Journal command interleavings on disposable files (ADR-044)."""
import subprocess
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from packages.config.settings import load_config
from packages.journal.forward import H4, JOURNAL_START_OPEN_MS, chain_append, new_record, verify_chain
from packages.market_data.models import Candle
from scripts import forward_journal as cli


OPEN = JOURNAL_START_OPEN_MS
NOW = (OPEN + H4 + 60_000) / 1000
SYMBOL = "XUSDT"


def decision(candle_open):
    return SimpleNamespace(decision="SIGNAL", symbol=SYMBOL, setup_candle_open_time_ms=candle_open,
                           entry=100.0, stop=95.0, target=110.0, risk_reward=2.0, checks={}, evidence={})


def bar(t, low=99):
    return Candle(SYMBOL, "4h", t, t + H4 - 1, 100, 101, low, 100, 1000, 100000, 10)


@pytest.fixture
def journal(tmp_path, monkeypatch):
    cfg = load_config()
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "JOURNAL", tmp_path / "journal.jsonl")
    monkeypatch.setattr(cli, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(cli, "time", SimpleNamespace(time=lambda: NOW))
    monkeypatch.setattr(cli, "BinancePublicClient", lambda cfg: nullcontext())
    monkeypatch.setattr(cli, "BASKETS", {"main": SYMBOL})
    # Analysis and transport are fixtures. The scan, settlement, hashing and file operations are real.
    engine = Mock()
    engine.daily_assessment.return_value = (SimpleNamespace(bullish=True),)
    engine.analyze.side_effect = lambda sym, daily, setup: SimpleNamespace(
        to_dict=lambda: {"open": setup[-1].open_time_ms})
    monkeypatch.setattr(cli, "AnalysisEngine", lambda cfg: engine)
    recipe = SimpleNamespace(decide=lambda analysis: decision(analysis["open"]))
    monkeypatch.setattr(cli, "build_recipes", lambda *args: {"brk55_trail": recipe})
    candles = [bar(OPEN + i * H4) for i in range(1 - cfg.backtest.analysis_window_4h, 1)]
    monkeypatch.setattr(cli, "fetch", lambda client, validator, sym, tf, limit: candles)
    recs = []
    owner_signal = new_record("sweep_only", decision(OPEN), None, {}, {}, int(NOW * 1000), OPEN + H4)
    chain_append(recs, owner_signal)
    cli.save(recs)
    return cfg, candles, owner_signal["id"]


def decide_in_subprocess(signal_id, *, immediate_timeout=False):
    # Redirect the private store and clock, then use the normal CLI parser/dispatcher.
    bootstrap = """
import sys
from pathlib import Path
from types import SimpleNamespace
from scripts import forward_journal as cli
cli.JOURNAL = Path(sys.argv.pop(1))
now = float(sys.argv.pop(1))
cli.time = SimpleNamespace(time=lambda: now)
if sys.argv.pop(1) == "no-wait":
    connect = cli.sqlite3.connect
    cli.sqlite3.connect = lambda path, timeout: connect(path, timeout=0)
sys.exit(cli.main())
"""
    return subprocess.run([sys.executable, "-c", bootstrap, str(cli.JOURNAL), str(NOW),
                           "no-wait" if immediate_timeout else "wait", "decide", signal_id,
                           "skipped", "--note", "test choice"], check=not immediate_timeout,
                          capture_output=True, text=True, timeout=20)


@pytest.mark.parametrize("command", ["scan", "settle"])
def test_owner_decision_during_fetch_survives(journal, monkeypatch, command):
    cfg, candles, signal_id = journal
    if command == "settle":
        candles.append(bar(OPEN + H4, low=94))
    run_decision = True

    def fetch(client, validator, sym, tf, limit):
        nonlocal run_decision
        if run_decision:
            run_decision = False
            decide_in_subprocess(signal_id)
        return candles

    monkeypatch.setattr(cli, "fetch", fetch)
    run = cli.cmd_scan if command == "scan" else cli.cmd_settle
    assert run(cfg) == 0
    assert run(cfg) == 0  # reopen from disk and retry
    rows = cli.load()
    assert rows[0]["owner"]["decision"] == "skipped"
    assert rows[0]["owner"]["note"] == "test choice"
    assert verify_chain(rows)["ok"]
    if command == "scan":
        assert [r["id"] for r in rows] == [signal_id, f"brk55_trail:{SYMBOL}:{OPEN}"]
        assert cli.load_state()["last_open_ms"] == {SYMBOL: OPEN}
    else:
        assert len(rows) == 1 and rows[0]["status"] == "CLOSED"
        assert rows[0]["exit_reason"] == "STOP"


def test_scan_recovers_after_journal_saved_before_watermark(journal, monkeypatch):
    cfg, _, signal_id = journal
    with monkeypatch.context() as interrupted:
        interrupted.setattr(cli, "save_state", Mock(side_effect=OSError("interrupted before watermark")))
        with pytest.raises(OSError, match="before watermark"):
            cli.cmd_scan(cfg)
    assert cli.load_state()["last_open_ms"] == {}
    rows = cli.load()
    assert [r["id"] for r in rows] == [signal_id, f"brk55_trail:{SYMBOL}:{OPEN}"]
    assert cli.cmd_scan(cfg) == 0
    assert cli.load() == rows and verify_chain(rows)["ok"]
    assert cli.load_state() == {"last_open_ms": {SYMBOL: OPEN}, "gaps": []}


def test_scan_commit_excludes_other_writer_until_replace(journal, monkeypatch):
    cfg, _, signal_id = journal
    save = cli.save

    def contend_before_replace(rows):
        result = decide_in_subprocess(signal_id, immediate_timeout=True)
        assert result.returncode != 0 and "database is locked" in result.stderr
        save(rows)

    with monkeypatch.context() as during_commit:
        during_commit.setattr(cli, "save", contend_before_replace)
        assert cli.cmd_scan(cfg) == 0
    decide_in_subprocess(signal_id)
    rows = cli.load()
    assert len(rows) == 2 and rows[0]["owner"]["decision"] == "skipped"
    assert verify_chain(rows)["ok"]


def test_older_scan_finishing_last_preserves_newer_watermark(journal, monkeypatch):
    cfg, candles, signal_id = journal
    newer = candles + [bar(OPEN + H4)]
    # Both bars are closed for this test. The first worker receives an older validated snapshot.
    monkeypatch.setattr(cli, "time", SimpleNamespace(time=lambda: NOW + H4 / 1000))

    def fetch_older(client, validator, sym, tf, limit):
        if tf == "4h":
            with monkeypatch.context() as concurrent:
                concurrent.setattr(cli, "fetch", lambda *args: newer)
                assert cli.cmd_scan(cfg) == 0
        return candles

    monkeypatch.setattr(cli, "fetch", fetch_older)
    assert cli.cmd_scan(cfg) == 0
    rows = cli.load()
    assert [r["id"] for r in rows] == [signal_id, f"brk55_trail:{SYMBOL}:{OPEN}", f"brk55_trail:{SYMBOL}:{OPEN + H4}"]
    assert verify_chain(rows)["ok"]
    assert cli.load_state() == {"last_open_ms": {SYMBOL: OPEN + H4}, "gaps": []}
