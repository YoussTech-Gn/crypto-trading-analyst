from packages.backtest import Backtester
from packages.config.settings import load_config
from packages.market_data.models import Candle

H4 = 14_400_000


def mk(i, tf="4h", step=H4):
    o = 1_600_000_000_000 // step * step + i * step
    p = 100.0 + (i % 7)
    return Candle("TESTUSDT", tf, o, o + step - 1, p, p + 1, p - 1, p, 10.0, 1000.0, 5)


def test_steps_near_tainted_candle_are_skipped_and_counted():
    cfg = load_config()
    setup = [mk(i) for i in range(560)]
    daily = [mk(i - 230, "1d", 86_400_000) for i in range(330)]  # starts 230 days before the 4h series
    clean = Backtester(cfg.analysis, cfg.signals, 2.0, cfg.backtest, min_setup=500).run("TESTUSDT", daily, setup)
    tainted = Backtester(cfg.analysis, cfg.signals, 2.0, cfg.backtest, min_setup=500,
                         tainted_open_times=[setup[520].open_time_ms]).run("TESTUSDT", daily, setup)
    assert clean.steps_skipped_data_defect == 0
    assert tainted.steps_skipped_data_defect > 0
    assert tainted.analysed_steps < clean.analysed_steps or clean.analysed_steps == 0
