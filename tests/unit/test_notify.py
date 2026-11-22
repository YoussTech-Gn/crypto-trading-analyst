from packages.notify.channels import load_env, ntfy, telegram
from packages.notify.planner import HEALTH_ALERT_MS, plan

H4 = 14_400_000
DAY = 86_400_000
T0 = 1_795_000_000_000 - (1_795_000_000_000 % DAY)  # a UTC midnight


def rec(i, open_ms, decision=None, status="PENDING"):
    return {"id": f"sweep_only:XUSDT:{open_ms}", "recipe": "sweep_only", "symbol": "XUSDT", "candle_open_ms": open_ms,
            "entry": 1.0, "stop": 0.9, "target": 1.2, "status": status, "owner": {"decision": decision}}


def test_a_new_signal_is_notified_once_with_the_decide_command():
    r = rec(1, T0)
    msgs, st = plan([r], {"initialized": True}, None, {}, T0 + H4 + 60_000, summary_hour_utc=25)
    assert [m[0] for m in msgs] == ["signal"] and "decide " + r["id"] in msgs[0][2] and "taken" in msgs[0][2]
    again, _ = plan([r], st, None, {}, T0 + H4 + 120_000, summary_hour_utc=25)
    assert again == []


def test_first_run_does_not_flood_old_signals():
    old = rec(1, T0)
    msgs, st = plan([old], {}, None, {}, T0 + 3 * DAY, summary_hour_utc=25)
    assert msgs == [] and old["id"] in st["notified_ids"]


def test_morning_summary_once_per_day_even_without_signals():
    view = {"btc_up": False, "up": [], "coins": 25, "signals": [], "close_calls": [{"coin": "XRP", "rule": "False break of a low"}]}
    msgs, st = plan([], {"initialized": True}, view, {"last_scan_ok_ms": T0 + 6 * 3_600_000}, T0 + 7 * 3_600_000 + 5)
    assert [m[0] for m in msgs] == ["summary"] and "DOWN" in msgs[0][2] and "XRP" in msgs[0][2]
    again, _ = plan([], st, view, {"last_scan_ok_ms": T0 + 6 * 3_600_000}, T0 + 9 * 3_600_000)
    assert again == []
    early, _ = plan([], {"initialized": True}, view, {}, T0 + 5 * 3_600_000)
    assert early == []


def test_health_alert_after_six_hours_without_a_good_scan_and_not_more_often():
    h = {"last_scan_ok_ms": T0}
    msgs, st = plan([], {"initialized": True}, None, h, T0 + HEALTH_ALERT_MS + 1, summary_hour_utc=25)
    assert [m[0] for m in msgs] == ["health"]
    again, _ = plan([], st, None, h, T0 + HEALTH_ALERT_MS + 3_600_000, summary_hour_utc=25)
    assert again == []


def test_channels_are_optional_and_env_file_is_read(tmp_path):
    (tmp_path / ".env").write_text("NTFY_TOPIC=abc123  # comment\nOTHER=1\n")
    assert load_env(tmp_path)["NTFY_TOPIC"] == "abc123"
    assert ntfy({}, "t", "b") == (False, "NTFY_TOPIC not set")
    assert telegram({}, "t", "b")[0] is False
