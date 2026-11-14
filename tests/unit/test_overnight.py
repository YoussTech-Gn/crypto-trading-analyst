import json
from dataclasses import asdict

import pytest

import scripts.overnight as ov
from tests.unit.test_freeze_portfolio import tr

AS_OF = 1_700_000_000_000


def mk_card(n, avg, ci, trades=150):
    return {"trades": trades, "avg_r": avg, "ci_lower_r": ci, "profit_factor": 1.2 if avg > 0 else 0.9, "max_drawdown_r": 5.0,
            "negative_windows": [], "meets_goal": False, "unmet": ["AVG_R: low"], "causes": ["WIN_RATE low"],
            "criteria_met": 2, "windows": {"w": {"trades": trades, "avg_r": avg}}}


def lab_json(names, avgs, as_of=AS_OF):
    rows = lambda i: [asdict(tr("X", 100 + i + 10 * k, 105 + i + 10 * k)) for k in range(3)]
    return {"meta": {"as_of_ms": as_of}, "trials": 29,
            "cards": {n: mk_card(n, a, a - 0.1) for n, a in zip(names, avgs)},
            "trades": {n: {"w": rows(i)} for i, n in enumerate(names)}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    rep, know = tmp_path / "reports", tmp_path / "knowledge"
    rep.mkdir(), know.mkdir()
    for k, v in {"REPORTS": rep, "KNOW": know, "STATUS": know / "s.json", "ANCHOR": know / "a.json",
                 "GATE": know / "gate.json", "FROZEN": know / "frozen.json"}.items():
        monkeypatch.setattr(ov, k, v)
    return rep, know


def test_freeze_then_alt_then_report_and_the_gate_is_one_shot(env, monkeypatch):
    rep, know = env
    names = ["fvg_a", "fvg_b", "brk20_trail", "pullback_ema20"]
    (rep / "lab_main.json").write_text(json.dumps(lab_json(names, [0.2, 0.1, 0.05, -0.1])))
    assert "frozen" in ov.stage_freeze(AS_OF)
    fz = json.loads((know / "frozen.json").read_text())
    assert fz["recipes"] == ["fvg_a", "fvg_b", "brk20_trail"] and fz["main_portfolio"]["trades"] > 0
    assert "kept" in ov.stage_freeze(AS_OF)                       # the freeze is not recomputed

    calls = []

    def fake_lab(args, logname):
        calls.append(args)
        (rep / "lab_alt.json").write_text(json.dumps(lab_json(fz["recipes"], [0.15, -0.05, 0.02], as_of=AS_OF)))
    monkeypatch.setattr(ov, "run_lab", fake_lab)
    ov.stage_alt(AS_OF, 1)
    gate = json.loads((know / "gate.json").read_text())
    assert set(gate["verdicts"].values()) <= {"PASS", "WEAK", "FAIL", "INCONCLUSIVE"} and gate["overall"] in set(gate["verdicts"].values()) | {gate["portfolio_verdict"]}
    assert calls[0][calls[0].index("--recipes") + 1] == "fvg_a,fvg_b,brk20_trail" and "--basket" in calls[0]
    assert "already used" in ov.stage_alt(AS_OF, 1) and len(calls) == 1   # ADR-026: never twice

    ov.stage_report(AS_OF)
    text = (rep / "MORNING_REPORT.txt").read_text()
    for needle in ("MAIN BASKET", "FROZEN", "ALT GATE", "closest to the goal", "best avg R per family"):
        assert needle in text


def test_freeze_refuses_a_lab_from_another_anchor(env):
    rep, _ = env
    (rep / "lab_main.json").write_text(json.dumps(lab_json(["fvg_a"], [0.1], as_of=1)))
    with pytest.raises(RuntimeError):
        ov.stage_freeze(AS_OF)


def test_a_failed_stage_writes_a_report_and_does_not_raise(env, monkeypatch):
    monkeypatch.setattr(ov, "write_failure_report", lambda script, exc, context="": env[0] / f"failure_{script}.txt")
    def boom():
        raise ValueError("boom")
    assert ov.guarded("x", boom) is False
    assert json.loads(ov.STATUS.read_text())["x"]["state"] == "FAILED"


def test_report_works_with_nothing_run(env):
    ov.stage_report(AS_OF)
    assert "no result for this anchor" in (env[0] / "MORNING_REPORT.txt").read_text()
