# Morning guide (ADR-045)

## 1. See the system (no command needed)
Open `reports/dashboard.html` in a browser (double-click it). It refreshes every 5 minutes and shows:
health (last good scan), Bitcoin's daily trend, coins in an uptrend, signals waiting for your decision, the
per-coin table, the journal and its integrity. "NO DATA" in the health card means the internet or the computer was off.

## 2. Notifications
* **Windows**: automatic. A small window appears for every new signal, at 07:00 UTC with a summary, and after 6 hours without data.
* **Phone (optional, free)**: install the **ntfy** app, subscribe to a long random topic name, add one line to `.env`:
  `NTFY_TOPIC=your-long-random-name`. Test: `.venv\Scripts\python scripts\notify.py --test`.
* **Telegram (optional)**: add `TELEGRAM_BOT_TOKEN=...` and `TELEGRAM_CHAT_ID=...` to `.env` (never commit `.env`).

## 3. When a signal arrives
You have 4 hours after the candle close. Copy the command shown on the dashboard:
`python scripts/forward_journal.py decide <ID> taken --price <your price> --mood 3` or `... skipped --mood 3`.

## 4. If nothing updates
1. `Get-Content reports\journal_cycle.log -Tail 30`
2. `schtasks /Query /TN "CTA forward journal" /V /FO LIST | Select-String "Status|Last Run|Next Run"`
3. Run once by hand: `scripts\journal_cycle.cmd`, then reopen the dashboard.

## 5. Prompt for Claude Code (commit the night's work)
```
Read CLAUDE.md and docs/DECISIONS.md (ADR-044 and ADR-045). Then:
1. Run the full test suite in groups (tests/unit/test_backtest.py on its own, it is slow) and show me the counts.
2. Run scripts/journal_cycle.cmd once and show the last 30 log lines and reports/dashboard.html's health card.
3. Commit in two commits: first the ADR-044 journal lock work (scripts/forward_journal.py, tests/integration/test_journal_commands.py,
   MEETING_AGENT.md, its DECISIONS entries), then the ADR-045 work (notifications, dashboard, watchdog, fallback host,
   trader view, docs). Do not commit .env, reports/dashboard.html or anything in .gitignore. Push, and check that CI is green.
```
