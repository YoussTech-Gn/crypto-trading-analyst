# Research & Monetization Proposal

**Date:** 2026-11-14  
**Scope:** Critical assessment of trading edge (free/public data, Binance Spot USDT long-only) and concrete income routes from existing repository assets.  
**Rule:** Every historical number below comes directly from `reports/` and `knowledge/`. Every expected trade count, timeline, and offer price is explicitly labeled as an **estimate** or **proposed price**, never as an observed result. External factual claims include source links retrieved during this session.

---

## 0. Epistemic Baseline: What We KNOW vs. What We Only HOPE

### What We KNOW (Observed in Repository Files)
1. **All 29 tested 4H long-only Binance Spot recipes failed.** In [`reports/MORNING_REPORT.txt`](../reports/MORNING_REPORT.txt) and [`reports/lab_main.txt`](../reports/lab_main.txt) (anchor `2026-11-14 08:00 UTC`, 3 × 730-day windows, `0.1%` fee per side + `0.05%` stop slippage, Bonferroni `z=2.92` for 29 trials, Liang-Zeger week-clustered SEs), **zero** recipes met the provisional goal (`avgR >= 0.20`, `PF >= 1.3`, `<= 1` negative window, `DD <= 20R`, `>= 100` trades, `ciLow > 0`).
2. **Winner's curse was directly demonstrated on the unseen `alt` basket.** The 3 pre-registered frozen candidates ([`knowledge/frozen_candidates.json`](../knowledge/frozen_candidates.json)) were:
   - `brk20_btc_trail`: on `main`, 366 trades, `avgR=+0.131`, `PF=1.26`, `ciLow=-0.163`, `neg_windows=0` (`+0.323` / `+0.008` / `+0.248`). On `alt` ([`reports/lab_alt.txt`](../reports/lab_alt.txt)), 245 trades, `avgR=-0.063`, `PF=0.88`, `ciLow=-0.332`, **negative in all 3 windows** (`-0.002` / `-0.050` / `-0.136`).
   - `brk55_trail`: on `main`, 456 trades, `avgR=+0.067`, `PF=1.13`, `ciLow=-0.122`. On `alt`, 320 trades, `avgR=-0.022`, `PF=0.96`, `ciLow=-0.275`, `neg_windows=2`.
   - `pullback_ema20_trail`: on `main`, 988 trades, `avgR=-0.015`, `PF=0.97`, `ciLow=-0.178`. On `alt`, 770 trades, `avgR=-0.119`, `PF=0.79`, `ciLow=-0.325`, `neg_windows=3`.
   - `PORTFOLIO(frozen)`: on `main`, 1,186 trades, `avgR=-0.000`, `PF=1.00`. On `alt`, **934 trades, `avgR=-0.079`, `PF=0.86`, `DD=93.35R`, `neg_windows=3`, `overall: FAIL`** ([`knowledge/alt_gate.json`](../knowledge/alt_gate.json)).
3. **Fees were NOT the primary reason trend breakouts failed.** On `fvg_only`, `avg_fee_r` was `+0.079R` against `avgR=-0.123R` (`lab_main.txt`). On `brk20_btc_trail` and `brk55_trail`, `avg_fee_r` was only `+0.031R` and `+0.029R` on `alt` (`lab_alt.txt`), yet `avgR` was `-0.063R` and `-0.022R`. Even at **zero fees**, `brk20_btc_trail` had negative gross expectancy (`-0.032R`) on unseen symbols. Moving to slower timeframes alone does not rescue a signal whose gross expectancy is ~0.
4. **Both historical datasets are spent for 4H rule discovery.** All history since `2020-05-01` across the 25 `main` symbols was used in development (`ADR-021`), and the 25 `alt` symbols were spent on the one-shot gate (`ADR-026`, `ADR-031`). Moreover, `data/cache` does not have uniform 6-year coverage across all 50 symbols: 6 `main` symbols (`SUIUSDT`, `ARBUSDT`, `APTUSDT`, `OPUSDT`, `TAOUSDT`, `ENAUSDT`) lacked history in `offset1460` (`lab_main.txt`), and `MKRUSDT` failed validation in `alt:offset0` (`MALFORMED_CANDLE_DATA,STALE_DATA`, `lab_alt.txt`).
5. **What is already built and verified in this codebase:** A deterministic, fail-closed engineering stack—Binance Spot public client, strict candle integrity validator (`FRESH` / `DELAYED` / `STALE` / `MISSING` / `MALFORMED`), PostgreSQL + SQLite dual-dialect schema/migrations, reproducible volume scanner (`scripts/run_scan.py`, FastAPI `/api/v1/scans/*`, Next.js `/scanner`), `NO_TRADE`-first signal contracts, conservative walk-forward backtester (with tie-breaking, fee/slippage modeling, post-mortems, `pattern_memory`), and a statistically guarded Strategy Lab.

### What We Only HOPE (Unproven)
1. That an economically meaningful Spot long-only edge exists in free/public Binance data if we switch to daily cross-sectional momentum or add free derivatives crowding data (funding rates, open interest, perp-spot basis, taker-buy flow).
2. That you can reach your first paying client and consistent income faster by selling your **validation, tooling, and engineering skills** than by trading your own capital on an unproven edge.

---

## Two Independent Questions

### Question A: Can a trading edge exist with data I can get for free?
**Honest answer: Possibly in narrow, slower or derivatives-informed pockets, but the odds are against making meaningful income from it soon.**
- **Why 4H Spot long-only OHLCV failed:** Textbook 4H price-action patterns (sweeps, FVGs, BOS, EMA pullbacks, RSI dips, 20/55 breakouts) on liquid Spot pairs are among the most crowded signals in retail crypto. Any small gross predictability is compressed to ~0 or below Binance's standard VIP-0 Spot fee of `0.1%` per side (`0.075%` with BNB fee discount) ([Binance Fee Schedule](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH8JIomMPaFIKo6vSybcnQ6_ylocP-UzIoiRCUDsTP-jXOexqJ_ujYUPibvqoR4keB0zFSyDnF700M156UJ01Be5PjnQ9qjfT4RBzbDGgHMVrvcYllZ22F08B-botR58lv6C8hwVD7KsXnV)). Worse, long-only Spot carries near-100% crypto market beta during bear/chop windows, which inflates week-clustered variance (`se_clustered` up to ~1.45× `se_naive` in `ADR-025`).
- **Where free public data still allows legitimate hypotheses:** Binance exposes unauthenticated historical derivatives metrics (`fundingRate`, `metrics` with `sum_open_interest`, `premiumIndexKlines`) via REST and `data.binance.vision` ([Binance Vision Archive](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE13iFyahPB5NlLjqZZ1aykD73PekpZyfruupN1iMSv_N4s3QYCvs2fJa9cuzmYU1YtEtVxZ5UPm64pn3nm2vRAnQUWmdNv4z-0xsqlabLXQVo10neJM2HSDepL-eO8dO0zDk_VRWzqnQWXI5AObXQ0sWhe1Gk-uXZYdu42mSI=), [Binance Futures API Docs](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHVqstaRjdOhXY8KHahj5IE1et7bv61Q747UhmAQot8fqP3tVaR-NGb-I2YcDlKF2O45fC6tHBd1RKx9YyXkWLT122QyzGQec2BZBKd5yLFQE-3pL2OEeGaybT4Z3zFo2tN70EY258kAL0cph-hpd3T-w6w2EjaoroxN-Z6et3czKBlyUrNDUR8Xv0Oi0MxBr9MCvF9oDfQb-hn_LoCGit5lkmB1BjrdPyWHk5ITcg=)), and Spot klines include `taker_buy_base_volume` / `taker_buy_quote_volume` ([Binance Spot Klines Spec](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF3dqdWmuS4ZjHBi436EcAVDpNos3NllPxqtlHdRls4qj6NnpHZcYvxoYAeD_8zTHBE8fpXm5fqkl_1dkwb8k4ew9Wkvzsiriw7aiiLkBkilUl_08-9sAnAxswb4IeyOc70IvK_op-CqOHcRSSXmQSa4Cv3a8lFxJC8hi_eNI_J-HZJSTmmH3r9hFz8z4RoAg==)). Cross-sectional daily/weekly attention flows and leveraged positioning flushes are structurally different from 4H OHLCV patterns.
- **Capital reality check:** Even if a Spot long-only strategy achieves a real Sharpe ~1.0 (already rare net of costs), on small personal capital (e.g., `$2,000–$10,000`), expected dollar profit is small and lumpy across bear markets. Trading research is **not** a fast path to reliable income.

### Question B: Can I earn money from the tools and skills I built even if no edge exists?
**Honest answer: Yes—strictly higher EV and much faster to first dollar than trading.**
- Trading profitability is zero-sum/negative-sum after exchange fees; **tooling, data engineering, and strategy auditing are positive-sum services**.
- Most retail traders, TradingView strategy sellers, and crypto communities *already* spend money on custom scanners, Python backtest verification, alert dashboards, and risk tooling. Freelance rates for TradingView/Python backtesting and trading automation commonly span **$200–$600** for basic scripts, **$500–$1,500+** for Pine-to-Python backtesting conversions, and **$1,500–$5,000+** for end-to-end alert/backend systems ([Freelance Rate Benchmarks](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHCPXwu9IN-HoRraqsdDOwjRjdhue8d-dDF3bCO4n6D9DcGY1iZBynsLLHptm3CUmktp_Kbzflo_0xHm8pl3QpZ_fOP7cnk_YGonHRcWxt2aowFj8U_y7ErVofMipByRK6aF3UlR7Q3GXaOQwQ_tjTwOHpz3rr_tEVvaZPuvFJ7-VFL_O6EqoIyxu32ImzObWS8mx4d7Bqnr4NbGGvRIYvB8ZIx_bU0_6iG2po5qGdgko1ejRcQc7t090rDgNlS-8IKrNoPcNb0Anc=), [Arc.dev Rates](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHcYA69OLDGrPBwydEzFZq-keIVKloWhf5z_A4P2xnJKjRlsF5gJdwqIHJgzJ08OBbKvubGJpn_HRl72TqqjeDo5rlV42jW9jR8iwbrBRXFI8swgHsHQmRxrhBpPnvwCcQ8)).
- **Your unfair advantage:** Almost every freelance bot builder ships overfit backtests or silent look-ahead bugs to please clients. Your repo's statistical discipline (`NO_TRADE`, fail-closed validation, conservative tie-breaking, Bonferroni + week-clustered CIs, `ADR` audit trail) positions you immediately above average as a **truthful, engineering-grade builder**.

---

## Part 1: Trading Hypotheses (Max 4, Free/Public Data Only)

> Note: We present **3 orthogonal hypotheses** rather than padding a 4th weak OHLCV indicator variant (see "Most Likely Time-Wasters" below).

### Hypothesis 1: Daily Cross-Sectional Relative-Strength / Momentum Rotation with Weekly Rebalancing & BTC Cash Gate
*(Includes direct critique of the daily RS/momentum rotation idea)*

- **Mechanism & why others haven't completely removed it:** Academic literature documents a cross-sectional momentum factor in cryptocurrencies driven by investor attention cycles and slow capital diffusion across assets ([Liu, Tsyvinski, & Wu, *Journal of Finance*, 2022](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH3y8bmTRhdkQFF61ClzDCMobeLUwk5-Yqq_cEJd2oA5YI-BYs_PdOyjkTBXMqRUxSJu4dDF7N8CzYyUTELO75ivzxj74I4gMKJnGOS8zsLZFm-Sj66v8gmwFFExIcZbzeBtOBHbbeTEyF_bjtjQOi0-228OF74c0s=); [Drogen, Hoffstein, & Otte](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEK0ChBpr1jZcvGaJrXygpRAe5_Bsjv9uhg4tIgTNjJA0BIo25bSy5X8CFxzXCsLAgB35rTBvg3cZhgcLOXHrlajlxxyr3ZS00hYSM1t6HkzYzrGKtcQSzWnL8BRYRwbwWsIBXd9-Nv9oIBtYmMFFHh7_Kcd_xwIajOAgfbf2DeVcz2kviBey1PbnoAbICk4oLrWshpXQTPW7j0Wpuh_Ds=); [Dobrynskaya](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFQM0ZQo7OFlxA9gqsVUfFlFnfjl7bKn4MBsZMaagA99ZCnObApuX7Wq-YXt4lKt-vsnOqqS5ZlVFASP18huhdEHKbb8HQeaPVbTZx_GeBwWJYOmRSsJxFODez25m6qhwJ-jaciJaUuIrxnIFUVV1b2RbKnTToQBigS3IejYfuhhgnz_1kQsj8SYyNt1tERI5BblMyoGnmg2C0eO0qsnoGkaBBuUB5huT7WhZBG8iUXYPbB1j4=)). Weekly rebalancing cuts turnover compared to 4H trading, and Spot-only mandates cannot easily short-arb baskets of volatile mid-cap alts without borrow/funding risk.
- **My honest view on this idea (skeptical):**
  1. **Literature warning:** Han, Kang, & Ryu (*Journal of Financial and Quantitative Analysis*) found that once realistic frictions, transaction costs, and rebalance-day effects are modeled, cross-sectional crypto momentum degrades heavily and is vulnerable to **rebalance-day fragility** (e.g., Sunday vs. Monday shifts) ([Han, Kang, & Ryu](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFlV50_0zDcouPd5PzrVlm2HJxy1bcD0z9N3eW2Jy0RwKRtwBALa7sJIIhp4059mZwcStSh_1V181GDWZomPDUEI-mFlBh31mGgg2TLJjUtYZL_eklK5Afj4coeg3NGYIzkhTvj_GXrsq7hvsoKeJ8Xghe_jRJhiIfRqpXwW26G76ij0QxCUw==); [Aut.ac.nz summary](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHOufqryrbiVKrjuntM80Wk787o5_a8pumw3EXbRTFNCnuaGuYtbjRhWfeeqtLsqFwd3rIdC939fu4D7LfzAlYBp08pm3P2uneWnaCLnxY4AqhWOzCYKkeYbPFhLqRGGCqP4ve9lNGxFWyElbrgllCvLJSpRLz-jZcWvkbLDPuCfTBbJhdKgwKvS8io9T-ww_OYzk2sWZ8F84pbuQTP6OAPLChwRU-w7nixjsCTOh46aZNH4nlJdzInuzuA3ha4x-jsjg==)).
  2. **Severe survivorship bias in `data/cache`:** Our 50 cached symbols are coins that *survived and remained liquid on Binance in Nov 2026*. Coins that surged into the top momentum ranks in 2021 and later collapsed or got delisted (e.g., LUNA, FTT, delisted alts) are absent. **Any positive backtest on `data/cache` alone is an upper bound polluted by survivorship bias, not proof.**
  3. **Small sample of independent weeks:** 6 years = ~312 weeks (~150–190 active bull weeks). That is only ~6 independent annual cycles, so statistical confidence will be wide.
  4. **Worth ONE disciplined test** only because the daily candles are already cached (cheapest possible test), *provided* you benchmark against `BTC-EMA50` (not `0%` cash) so you don't mistake "being long during a BTC bull market" for rotation alpha.
- **Parameters fixed in advance (no tuning):**
  - Universe: first test on `main` 25 symbols; only include a symbol on rebalance date `t` if it has `>= 60` closed daily candles prior to `t`.
  - Score: 28-day log return divided by 28-day daily realized volatility (`ret_28 / vol_28`, volatility-adjusted momentum).
  - Regime Gate: `BTCUSDT` daily close > `EMA(50)` at rebalance `00:00 UTC`. If false, hold `100%` USDT cash.
  - Portfolio: equal-weight top `K = 3` assets (`33.3%` each).
  - Rebalance cadence: every 7 days at `00:00 UTC` daily close; pay `0.10%` fee + `0.05%` slippage on actual traded weight delta (`turnover`).
- **Data needed (free/public only):** Already cached `data/cache/*_1d.json` for initial falsification; if it survives initial test, requires historical Binance delisted/all-pair listings from `data.binance.vision` to remove survivorship bias.
- **Exact test:** Build a separate weekly portfolio simulator (the current single-symbol `Backtester` cannot simulate cross-sectional ranking). Run across **all 7 rebalance weekdays** (`Mon..Sun`). Compare net CAGR, Sharpe, MaxDD, and weekly **excess return over a `BTC-EMA50` timing benchmark** (hold 100% BTC when `BTC > EMA50`, else USDT) using a 4-week block-bootstrap 95% CI, plus a 2× cost stress test (`0.20%` fee + `0.05%` slippage per side).
- **Expected trade count (estimate):** ~150–190 active weeks × ~1–2 position changes/week ≈ **180–350 rebalance trades** across ~312 weekly portfolio observations.
- **Kill criterion:** Kill immediately if ANY of: (1) 95% block-bootstrap lower bound of weekly excess return over `BTC-EMA50` `<= 0`, (2) net Sharpe `<= BTC-EMA50` benchmark Sharpe, (3) sign of excess return flips depending on weekday chosen (rebalance-day fragility), or (4) excess return turns negative under 2× cost stress test.
- **What could fool me:** Survivorship bias in the 50 cached coins; confusing BTC bull-market timing (`EMA50`) with altcoin selection alpha; one 2021 alt-season outlier carrying the entire 6-year mean; Sunday-vs-Monday liquidity luck.

---

### Hypothesis 2: Derivatives Deleveraging Flush + Negative Funding Rebound (Spot Long)

- **Mechanism & why others haven't removed it:** Crypto Spot prices are frequently pushed below fair value by forced liquidations and crowded perpetual futures shorting. When Open Interest drops sharply (longs wiped out / deleveraging completed) while perpetual funding flips negative (shorts paying longs), forced selling is exhausted and market makers face balance-sheet/margin limits during cascades, creating a temporary risk-premium rebound.
- **Parameters fixed in advance:**
  - Universe: symbols in `main` with USDS-M perpetual history.
  - Trigger (4H closed candle): (1) latest 8h funding rate `<= -0.0002` (`-0.02%`), (2) 24h Open Interest drop `<= -15%`, (3) current 4H candle is bullish (`close > open`) and closes above the prior 4H low.
  - Entry: next 4H open (`0.10%` fee + `0.15%` crash-slippage baseline).
  - Stop: trailing 24h flush low `- 0.5 * ATR(14)` (minimum stop distance `1.0 * ATR(14)`).
  - Exit: fixed `2.0R` target or time exit at close of 18th 4H bar (`72h`).
- **Data needed (free/public only):** Unauthenticated USDS-M Futures historical `fundingRate` and `metrics` (`sum_open_interest`) from `data.binance.vision` ([Binance Vision Archive](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQE13iFyahPB5NlLjqZZ1aykD73PekpZyfruupN1iMSv_N4s3QYCvs2fJa9cuzmYU1YtEtVxZ5UPm64pn3nm2vRAnQUWmdNv4z-0xsqlabLXQVo10neJM2HSDepL-eO8dO0zDk_VRWzqnQWXI5AObXQ0sWhe1Gk-uXZYdu42mSI=)), joined by timestamp to cached 4H Spot candles. *(Note: REST `/futures/data/openInterestHist` only retains ~30 days, so `data.binance.vision` daily `metrics` is required ([Binance Futures API Docs](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGusSPBOcWNug1Xbu4yhX8c4LzOHAYPr3icmizwD5_AQr1QxSJwlf7qLE7q8W5IrWGYXwDadyOfFcA_GOGYa6_9ZaQJq4lnVd577RLn8nOsnjEsBZdclTCtcKEib7qfrnbOS2kt9U3QJUxeGbhY1p4vy7XRCKleJN8-_AMsinQx6MZbt7167NEeSNZHL8qCuzJwxiuNelNDOj_SqJVB6kAazhbjTsmDn5iT2xFP6A==)).)*
- **Exact test:** Walk-forward backtest on `main` (over the covered derivatives history window), week-clustered SEs (`Liang-Zeger`), plus slippage sensitivity at `0.05%`, `0.15%`, and `0.25%`.
- **Expected trade count (estimate):** **~50–120 trades** across 25 symbols (liquidation flushes are discrete macro/microstructure events).
- **Kill criterion:** `< 20` distinct weekly clusters (proving trades are just 3–5 market crash days counted 15 times each), OR week-clustered 95% CI lower bound `<= 0`, OR `avgR < +0.15` at `0.15%` slippage.
- **What could fool me:** Extreme cross-sectional clustering (20 coins flushing on the exact same BTC crash day = 1 independent bet); optimistic fill prices during violent liquidation wicks; limited historical depth of `data.binance.vision` `metrics`.

---

### Hypothesis 3: Spot-Led Accumulation Divergence (Spot Taker-Buy Flow vs. Perp Basis)

- **Mechanism & why others haven't removed it:** Purely perp-driven rallies (perp trading at steep positive premium/funding above spot) frequently unwind via long squeezes, whereas spot-led accumulation (aggressive market buyers on Spot while perp basis stays flat or discounted) reflects unleveraged demand that is slower to reverse. Standard OHLCV backtesters ignore taker-buy flow and perp-spot basis.
- **Parameters fixed in advance:**
  - Universe: `main` symbols with USDS-M perpetuals.
  - Trigger (1D closed candle): (1) 5-day rolling Spot `taker_buy_quote_volume / quote_volume > 0.54`, (2) 5-day mean perp-spot close basis `(perp_close - spot_close) / spot_close <= 0.0`, (3) Spot close `> 20-day high` AND `BTCUSDT 1D close > EMA(50)`.
  - Entry: next 1D open (`0.10%` fee + `0.05%` slippage).
  - Stop: `entry - 2.0 * ATR(14)`.
  - Exit: trail `1.0R` behind highest close once `+1.0R` is reached (max hold `30` days).
- **Data needed (free/public only):** Re-fetch Spot 1D klines retaining fields `9–10` (`taker_buy_base_volume`, `taker_buy_quote_volume`, currently omitted from `Candle` in `packages/market_data/models.py`) ([Binance Spot Klines Spec](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQF3dqdWmuS4ZjHBi436EcAVDpNos3NllPxqtlHdRls4qj6NnpHZcYvxoYAeD_8zTHBE8fpXm5fqkl_1dkwb8k4ew9Wkvzsiriw7aiiLkBkilUl_08-9sAnAxswb4IeyOc70IvK_op-CqOHcRSSXmQSa4Cv3a8lFxJC8hi_eNI_J-HZJSTmmH3r9hFz8z4RoAg==)) + USDS-M `premiumIndexKlines` from `data.binance.vision` / public Binance Futures API.
- **Exact test:** Walk-forward on `main` with week-clustered SEs; directly compare incremental `avgR` against a control without the taker-buy/basis gates (`20D breakout + BTC EMA50`) to verify the flow data actually adds signal.
- **Expected trade count (estimate):** **~60–130 trades** over 5–6 years.
- **Kill criterion:** Week-clustered 95% CI lower bound `<= 0`, OR `avgR < +0.15`, OR fails to outperform the plain `20D breakout + BTC EMA50` control by a statistically meaningful margin.
- **What could fool me:** Binance zero-fee Spot promotions (such as past BTC zero-fee promos) ([Binance Fee Schedule](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH8JIomMPaFIKo6vSybcnQ6_ylocP-UzIoiRCUDsTP-jXOexqJ_ujYUPibvqoR4keB0zFSyDnF700M156UJ01Be5PjnQ9qjfT4RBzbDGgHMVrvcYllZ22F08B-botR58lv6C8hwVD7KsXnV)) artificially distorting taker-buy volume ratios; shared BTC bull beta.

---

## Part 2: Income Routes from Existing Assets (Ranked by Time to First Payment)

What you already own is **not** a money-printing strategy—it is a **battle-tested, anti-overfit quant research & market-data engineering stack** (`market_data`, `scanner`, `signals`, `backtest`, `postmortem`, `pattern_memory`, `strategies`, FastAPI, Next.js). Here are 5 routes ranked by realistic speed to first cash:

### Rank 1: Strategy Audit & Backtest Validation Service *(Fastest — Est. 1–3 weeks to first payment)*
- **Mechanism:** Thousands of traders buy/build Pine Script or Python strategies that look great in naive backtests due to look-ahead bias, repainting, intrabar fill assumptions, missing fees, or multiple-testing overfitting. Freelance developers normally say "yes" to everything; you can sell **objective, deterministic verification** using the exact audit engine you already built (`packages/backtest`, `postmortem.py`, `scorecard.py`).
- **Who pays:** Independent systematic/discretionary traders, TradingView strategy sellers wanting independent Python validation, Telegram/Discord signal operators testing rules before risking capital.
- **Proposed price range (grounded against market benchmarks):**
  - **$150–$350** fixed-price **"Backtest Reality-Check Audit"** (encode client rules, run walk-forward with fees/slippage/conservative tie-breaking + week-clustered CI + post-mortem report).
  - **$500–$1,200+** for full Pine Script / strategy spec to standalone Python validator + custom metrics (consistent with observed **$500–$1,500+** freelance Pine-to-Python backtesting benchmarks) ([Upwork/Freelance Benchmarks](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHCPXwu9IN-HoRraqsdDOwjRjdhue8d-dDF3bCO4n6D9DcGY1iZBynsLLHptm3CUmktp_Kbzflo_0xHm8pl3QpZ_fOP7cnk_YGonHRcWxt2aowFj8U_y7ErVofMipByRK6aF3UlR7Q3GXaOQwQ_tjTwOHpz3rr_tEVvaZPuvFJ7-VFL_O6EqoIyxu32ImzObWS8mx4d7Bqnr4NbGGvRIYvB8ZIx_bU0_6iG2po5qGdgko1ejRcQc7t090rDgNlS-8IKrNoPcNb0Anc=)).
- **Cheapest test & First action this week:** Publish one concrete case study based on *this repository* (`"I tested 29 crypto strategies with conservative fills, Bonferroni penalties, and an unseen 25-coin gate—and killed all 29 before risking $1"`), showing real snippets from `MORNING_REPORT.txt` and `lab_alt.txt`. Send 20 targeted Upwork proposals / X & Reddit `r/algotrading` offers for a **$199 fixed-scope Strategy Audit** with 72h turnaround.
- **Kill criterion:** 30 targeted proposals/outreach DMs over 14 days yield `0` discovery conversations or `0` paid audits after one pitch iteration.
- **Main risk / What could fool me:** Traders often want validation of their ego, not the truth. **Positioning fix:** Do not pitch *"I'll prove your strategy fails"*; pitch *"Find hidden repainting, fee drag, and execution leaks before your live account pays for them."* Also beware messy/ambiguous client specs—require explicit rule sign-off before coding.

### Rank 2: Custom Crypto Scanners, Alert Bots & Client Dashboards *(Est. 2–5 weeks to first payment)*
- **Mechanism:** Active traders and trading communities pay reliably for custom market screeners, Telegram/Discord alerts, and clean web dashboards (`apps/api`, `apps/web`, `packages/scanner`, `packages/market_data`). Utility software gets paid whether markets go up, down, or sideways.
- **Who pays:** Active crypto traders, paid Discord/Telegram communities, boutique family/prop traders needing automated multi-pair monitoring (volume anomalies, spread/liquidity gates, custom alerts).
- **Proposed price range:** **$400–$1,500** per fixed-scope scanner/alert/dashboard build (aligning with **$200–$600** custom indicator/script and **$1,500–$5,000** end-to-end alert/backend system ranges) ([Upwork/Freelance Benchmarks](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQHCPXwu9IN-HoRraqsdDOwjRjdhue8d-dDF3bCO4n6D9DcGY1iZBynsLLHptm3CUmktp_Kbzflo_0xHm8pl3QpZ_fOP7cnk_YGonHRcWxt2aowFj8U_y7ErVofMipByRK6aF3UlR7Q3GXaOQwQ_tjTwOHpz3rr_tEVvaZPuvFJ7-VFL_O6EqoIyxu32ImzObWS8mx4d7Bqnr4NbGGvRIYvB8ZIx_bU0_6iG2po5qGdgko1ejRcQc7t090rDgNlS-8IKrNoPcNb0Anc=)), plus **$100–$300/mo** maintenance if hosted.
- **Cheapest test & First action this week:** Record a 60-second screen-capture demo of the existing Next.js `/scanner` + FastAPI endpoints + fail-closed data validation. Bid on 10 active freelance jobs for Python/FastAPI/Next.js crypto dashboards or Telegram scanners using that demo video as proof.
- **Kill criterion:** `0` client replies after 20 customized proposals with the live demo link.
- **Main risk / What could fool me:** Clients demanding auto-trading execution with their private API keys (high security/legal liability). Stay strictly read-only / alert-only / local-deployment unless contractually scoped.

### Rank 3: Signal-Journal & Pre-Trade Risk-Check Tool *(Est. 4–8 weeks to first payment)*
- **Mechanism:** Discretionary and prop-firm traders lose accounts due to undisciplined sizing, trading during poor regimes/low volume, or repeating the same errors—not lack of indicators. Your `NO_TRADE` gate evaluator, risk calculator, `postmortem.py`, and `pattern_memory.py` already model *rule compliance and mistake memory*.
- **Who pays:** Active crypto/prop-challenge traders who want an objective pre-trade checklist ("should this trade be `NO_TRADE`?") + automated post-mortem tagging of recurring mistakes (`TIGHT_STOP`, `LOW_VOLUME`, `UNEXPECTED` slippage).
- **Proposed price range:** **$19–$39/month** SaaS or **$49–$99** one-time local/self-hosted license.
- **Cheapest test & First action this week:** **Do NOT build multi-tenant auth, Stripe, or a polished SaaS yet.** Offer a manual "Concierge Risk & Journal Audit" (using your local scripts on CSV exports of a trader's last 50 trades) to 10 active traders at **$29–$49** one-off. Only build the SaaS if `>= 3` strangers pay.
- **Kill criterion:** `< 3` paid concierge trials out of 30 targeted trader conversations over 3 weeks.
- **Main risk / What could fool me:** Classic "build-in-silence" trap—spending 6 weeks building Next.js auth/billing for a tool traders say is "cool" but won't pay for because free Notion/Excel templates exist.

### Rank 4: Quant Validation Starter Kit / Open-Core Repo *(Est. 6–12 weeks to first payment)*
- **Mechanism:** Self-taught developers and aspiring quants waste months writing buggy backtesters with look-ahead bias. Packaging your clean monorepo infrastructure (validator + walk-forward engine + Postgres/SQLite + Next.js shell, explicitly branded as an **engineering & validation framework with no trading edge claimed**) monetizes your code directly as a product.
- **Who pays:** Python developers, CS learners, indie algo builders.
- **Proposed price range:** **$49–$129** one-time template/pro-modules license.
- **Cheapest test & First action this week:** Publish a clean technical post + architecture diagram linking to a waitlist/pre-order page before spending time packaging or stripping project-specific files.
- **Kill criterion:** `< 5` pre-orders or `< 25` qualified waitlist signups after publishing 2 technical deep-dives.
- **Main risk / What could fool me:** Tough competition against free open-source frameworks (`freqtrade`, `vectorbt`, `backtrader`); works only if your anti-overfitting statistical rigor (`ADR` workflow, clustered SEs, `alt_gate`) is the clear differentiator.

### Rank 5: Binance Square Content ("Write to Earn") *(Slowest / Lowest Reliable Cash — Est. 3–6+ months)*
- **Mechanism:** Binance Square's "Write to Earn" automatically enrolls KYC-verified creators and pays a **~20% basic commission** on net trading fees generated when readers click embedded coin cashtags/widgets (`$BTC`, `$ETH`) and trade, plus weekly engagement bonus pool shares ([Binance Square Write to Earn](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFoPuoL3ihetGu25HcUZqQXlB7MiOKoc4SuRVuRNtCA5ZEo-vik8bMbUCIfzsz8K2OmYsXaNlh48BVADdAQPTXhOOeqYmJ-bRlBWCTWz8tLrs7qHfBZ9e5oHLeBbFXmEwyHZvSHHoomeCEgB9A=), [Binance Square Program Details](https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQFzqII0rWHkrztIcGiX4ocW_Z8_HE51H9h3YaEpffGqr4VrkrD_UKx65CyMUgkCs94tLyuwFF1E38-0AowyuBN5fb5gqO7eAJgj-3Xzt9wmKHj0USEKZ508aMdgmIE0d5Z2gJ5vtz0AL7AZwv_IZouBBciMZV64hm0Nz09yXnt6igcerlRIS-H39HFI08A=)).
- **Who pays:** Binance (fee rebates + engagement reward pool).
- **Proposed/expected range (estimate):** Typically **$0–$30/month** early on unless you build high-volume cashtag click-throughs.
- **Cheapest test & First action this week:** Cross-post your backtest teardowns 1–2×/week strictly as a zero-expectation top-of-funnel bio link—**never** as an income strategy.
- **Kill criterion:** Spending `> 2 hours/week` on Square with zero inbound freelance leads or trivial payouts after 4 weeks.
- **Main risk / What could fool me:** **Incentive mismatch.** Write-to-Earn rewards getting readers to click `$COIN` and trade impulsively; your brand value to paying engineering/audit clients comes from telling the truth (`NO_TRADE`, statistical skepticism). Chasing clicks can ruin your positioning.

---

## Ideas Most Likely to Waste Your Time

1. **Tweaking 4H Spot long-only recipes further:** Already falsified across 29 recipes (`main` + spent `alt` gate). Changing EMA `20` to `21` or RSI `30` to `28` is pure overfitting.
2. **Building a full multi-tenant SaaS UI before pre-selling:** Never build login/billing/onboarding for the journal/risk tool before 3 strangers pay for a manual run.
3. **Treating Binance Square "Write to Earn" as an income plan:** High effort, tiny early payouts, and perverse clickbait incentives.
4. **Running 50 more pure-OHLCV variations on the same 50 cached symbols:** Every extra trial pushes the Bonferroni bar higher (`z` is already `2.92`) on a survivorship-biased cache.

---

## Part 3: Single Recommendation & Handoff to Claude

### My Single Recommendation: **80% Client Revenue (Route #1 + #2) / 20% Time-Boxed Lab (H1 Only)**
Stop trying to squeeze income out of an unproven Binance Spot trading edge. Starting this week, spend **80% of your time** turning your existing audit & scanner stack into **Route #1 (Strategy Audit & Backtest Validation)** and **Route #2 (Custom Scanners/Dashboards)** so you get your **first paying client in 2–4 weeks**.

Spend at most **20% of your time** letting Claude run **Hypothesis 1 (Daily RS/Momentum Rotation vs. `BTC-EMA50`)** as a single, pre-registered, zero-download experiment on the cached `1D` candles—with a strict kill switch. If H1 fails its kill criterion, **close pure-OHLCV Spot trading research completely** and only revisit derivatives data (H2/H3) *after* client revenue is paying your bills.

### Exact Brief to Bring Back to Claude (Lab Runner)
> 1. **Do NOT reopen the 4H Spot long-only lab** (`ADR-031` stays closed; do not modify `packages/strategies/recipes.py` or `knowledge/alt_gate.json`).
> 2. **Log `ADR-032` first** and build a standalone, offline weekly portfolio simulator (`scripts/run_rotation_study.py`) reading only `data/cache/*_1d.json` (no downloads, no trades).
> 3. **Pre-register exact Hypothesis 1 parameters:** `main` 25 symbols (listing-aware per date: `>= 60` prior closed 1D bars), score = `28d_log_ret / 28d_daily_vol`, regime gate = `BTCUSDT 1D close > EMA(50)` (else `100%` USDT cash), equal-weight top `K=3`, weekly rebalance, `0.10%` fee + `0.05%` slippage on actual weight turnover.
> 4. **Mandatory diagnostics before any optimism:**
>    - Test **all 7 rebalance weekdays** (`Mon..Sun`) to expose rebalance-day fragility.
>    - Benchmark against **`BTC-EMA50`** (not `0%`), reporting 4-week block-bootstrap 95% CI on weekly excess return, plus a **2× cost stress test** (`0.20%` fee/side).
>    - Explicitly mark any positive result as **PROVISIONAL / SURVIVORSHIP-BIASED** because `data/cache` lacks delisted coins.
> 5. **Kill rule:** If `BTC-EMA50` benchmark beats H1 on Sharpe, OR 95% block-bootstrap lower bound of excess return `<= 0`, OR sign flips across weekdays, OR 2× fees kills excess return -> log `ADR-032` as `Rejected` and end pure-OHLCV Spot research.

---

## 3 Questions I Need You to Answer

1. **Time, Urgency & Capital Reality:** How many hours per week can you commit over the next 30 days, how urgent is your first `$500–$1,000` of income, and how much capital would you actually trade if a Spot strategy worked? *(This decides whether `20%` lab time is even worth spending right now vs. `100%` client work.)*
2. **Sales Channel & English Comfort:** Which outreach channel can you execute *this week* (Upwork/Fiverr proposals, X/Twitter + Reddit `r/algotrading` teardowns, or direct outreach to trading communities), and are you ready to record a 60-second English walkthrough video of your backtester/scanner?
3. **Lab Boundary Commitment:** Do you agree to keep the 4H line closed, run **only H1** as a single pre-registered pass with the kill switch above, and pause all trading-strategy R&D if H1 fails until after your first paying client?
