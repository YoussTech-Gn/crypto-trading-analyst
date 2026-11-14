import pytest

from packages.backtest.engine import Trade
from packages.strategies import Goal, score_recipe
from packages.strategies.freeze import alt_verdict, family_of, overall_verdict, select_frozen
from packages.strategies.portfolio import combine, overlap_report, trades_from_json


def card(trades=200, avg=0.05, ci=-0.1, pf=1.2, neg=()):
    return {"trades": trades, "avg_r": avg, "ci_lower_r": ci, "profit_factor": pf, "negative_windows": list(neg)}


def test_family_of():
    assert [family_of(n) for n in ("fvg_only", "combo_upper_btc", "brk20_trail", "pullback_ema20", "rsi_dip_30", "sweep_fvg", "bos_retest")] == \
           ["fvg", "fvg", "breakout", "pullback", "rsi", "smc", "smc"]


def test_freeze_ranks_by_clustered_bound_needs_trades_and_caps_a_family():
    cards = {"fvg_a": card(ci=0.30), "fvg_b": card(ci=0.20), "combo_c": card(ci=0.10), "brk20_trail": card(ci=0.05),
             "pullback_ema20": card(ci=0.01), "rsi_dip_30": card(trades=40, ci=0.9), "sweep_only": card(ci=None)}
    assert select_frozen(cards) == ["fvg_a", "fvg_b", "brk20_trail"]   # combo_c is a 3rd fvg; rsi has too few trades; None skipped


def test_freeze_with_nothing_eligible_is_empty():
    assert select_frozen({"a": card(trades=10)}) == []


def test_alt_verdicts():
    good = card(trades=150, avg=0.15, pf=1.3, neg=["w1"])
    assert alt_verdict(good, card(avg=0.02)) == "PASS"
    assert alt_verdict(good, card(avg=-0.02)) == "WEAK"                 # no edge on the main basket -> cannot pass
    assert alt_verdict(card(trades=150, avg=0.05, pf=1.1), None) == "WEAK"
    assert alt_verdict(card(trades=150, avg=-0.01), None) == "FAIL"
    assert alt_verdict(card(trades=80, avg=0.5), None) == "INCONCLUSIVE"
    assert alt_verdict(card(trades=150, avg=0.15, pf=1.3, neg=["a", "b"]), None) == "WEAK"
    assert overall_verdict({"x": "FAIL", "y": "WEAK"}) == "WEAK" and overall_verdict({}) == "NOT_RUN"


def tr(sym, fill, exit_, r=1.0, sig=None):
    return Trade(symbol=sym, signal_index=0, signal_time_ms=sig or fill - 1, entry=1, stop=0.9, target=1.2, planned_rr=2.0,
                 fill_index=0, fill_time_ms=fill, exit_index=1, exit_time_ms=exit_, exit_price=1.1, exit_reason="TARGET",
                 r_multiple=r, bars_held=3)


def test_portfolio_keeps_one_position_per_symbol_and_counts_a_shared_setup_once():
    per = {"a": {"w": [tr("X", 10, 20), tr("Y", 12, 30)]},
           "b": {"w": [tr("X", 10, 25, r=2.0), tr("X", 15, 40), tr("X", 21, 50)]}}
    out = combine(per, ["a", "b"])["w"]
    assert [(t.symbol, t.fill_time_ms) for t in out] == [("X", 10), ("Y", 12), ("X", 21)]
    assert out[0].r_multiple == 1.0          # tie goes to the recipe listed first
    assert combine(per, ["b", "a"])["w"][0].r_multiple == 2.0


def test_portfolio_scores_like_any_recipe_and_overlap_is_reported():
    per = {"a": {"w": [tr("X", 10, 20, sig=5), tr("Y", 12, 30, sig=6)]}, "b": {"w": [tr("X", 11, 25, sig=5)]}}
    card_ = score_recipe(combine(per, ["a", "b"]), Goal(), trials=3)
    assert card_["trades"] == 2
    ov = overlap_report(per, ["a", "b"])
    assert ov["setups_union"] == 2 and ov["setups_in_more_than_one"] == 1


def test_trades_roundtrip_from_json():
    from dataclasses import asdict
    t = tr("X", 10, 20)
    assert trades_from_json([{**asdict(t), "unknown_key": 1}]) == [t]
