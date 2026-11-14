from packages.backtest.memory import PatternMemory


def lesson(flag, nw, aw, nwo, awo):
    return {"flag": flag, "all": {"n_with": nw, "avg_r_with": aw, "n_without": nwo, "avg_r_without": awo}}


def mem_with(windows):
    m = PatternMemory()
    for w, ls in windows.items():
        m.record_run(w, "first_meeting_rr", ls, {"NORMAL_STOP": 5}, 30, -0.1)
    return m


def test_status_progression_insufficient_watch_hazard():
    bad = lesson("TINY_FVG", 20, -0.5, 20, 0.1)
    assert mem_with({"w1": [bad]}).assess()["TINY_FVG"]["status"] == "INSUFFICIENT"
    assert mem_with({"w1": [bad], "w2": [bad]}).assess()["TINY_FVG"]["status"] == "WATCH"
    assert mem_with({"w1": [bad], "w2": [bad], "w3": [bad]}).assess()["TINY_FVG"]["status"] == "RECURRING_HAZARD"


def test_one_contradicting_window_makes_it_mixed():
    bad, good = lesson("TINY_FVG", 20, -0.5, 20, 0.1), lesson("TINY_FVG", 20, 0.4, 20, 0.0)
    assert mem_with({"w1": [bad], "w2": [bad], "w3": [good]}).assess()["TINY_FVG"]["status"] == "MIXED"


def test_small_samples_are_ignored():
    tiny = lesson("TINY_FVG", 3, -2.0, 30, 0.2)
    assert mem_with({"w1": [tiny], "w2": [tiny]}).assess()["TINY_FVG"]["status"] == "INSUFFICIENT"


def test_same_window_rerun_replaces_not_adds():
    bad = lesson("TINY_FVG", 20, -0.5, 20, 0.1)
    m = mem_with({"w1": [bad]})
    m.record_run("w1", "first_meeting_rr", [bad], {}, 30, -0.1)
    assert m.assess()["TINY_FVG"]["windows_used"] == 1


def test_advise_flags_new_signal_and_is_clean_otherwise():
    bad = lesson("TINY_FVG", 20, -0.5, 20, 0.1)
    m = mem_with({"w1": [bad], "w2": [bad]})
    risky = m.advise({"fvg_size_atr": 0.1, "risk_atr": 2.0})
    assert risky["risk_level"] == "LOW" and risky["active"][0]["flag"] == "TINY_FVG"
    assert m.advise({"fvg_size_atr": 0.6, "risk_atr": 2.0})["risk_level"] == "CLEAN"


def test_persistence_roundtrip(tmp_path):
    bad = lesson("TINY_FVG", 20, -0.5, 20, 0.1)
    m = mem_with({"w1": [bad]})
    path = tmp_path / "pm.json"
    m.save(path)
    assert PatternMemory.load(path).assess() == m.assess()
