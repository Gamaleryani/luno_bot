# Luno Multi-Indicator Trading Bot

## Structure
- `config.py` — shared defaults (mode, pair, thresholds, risk limits, fees, alert threshold)
- `core/profiles.py` — named strategy variants that override config.py defaults, so
  multiple strategies can run in parallel without stepping on each other
- `core/indicators.py` — RSI, moving averages, Bollinger Bands, volume, ADX
- `core/regime.py` — detects trending vs ranging market
- `core/strategy.py` — multi-indicator voting logic, regime-aware, news-shock filter,
  optional `ALLOWED_REGIMES` restriction
- `core/risk.py` — stop-loss, take-profit, volatility-based position sizing
- `core/luno_client.py` — Luno API wrapper (`get_candles` requires an authenticated
  key even for read-only history; paper/backtest never place real orders)
- `core/logger.py` — trade logging + performance summary generator
- `core/state.py` — persists balance/open-position between runs per profile
  (`state/<profile>.json`)
- `core/notifier.py` — sends email on every trade via SMTP (needs `EMAIL_*` env vars,
  no-ops safely if unset)
- `core/approval.py` — file-based approval gate for big **live** trades (see below)
- `backtest.py` — runs one config over historical CSV data, with fee/hold-duration accounting
- `strategy_compare.py` — runs many variants + a buy-and-hold benchmark side by side
- `data/fetch_history.py` — pulls real candle history from Luno into a CSV
- `data/generate_sample.py` — synthetic data generator (plumbing test only, not real prices)
- `main.py` — paper/live runner for one profile against real Luno prices
- `approve_trade.py` — approves a pending big live trade
- `generate_dashboard.py` — renders `dashboard.html` from current state + logs

## Status (2026-08-20)
Backtested extensively against real XBTMYR history (30d–2.7yr, multiple candle
durations, 15 variants, all compared against a buy-and-hold benchmark — not just
raw returns, since much of a "profit" over the last 2 years was just Bitcoin's own
rise). Two profiles came out as the only configs that consistently beat
buy-and-hold across multiple time windows, and are now running in **paper mode**:

- **`trend_4h`** — 4h candles, 5%/8% stop-loss/take-profit. Swing-trading style,
  ~4.7 day average hold. Beats buy-and-hold when the market trends.
- **`range_1h_defensive`** — 1h candles, ranging-regime-only, 2%/3% stop/take-profit.
  ~1-3 day average hold. The only config that stayed profitable through a falling
  market (1-year window where buy-and-hold lost -40.67%, this made +2.59%).

Neither is proven — 1-3 years of one asset's history is still a small sample — but
both are the strongest evidence-backed candidates found so far. Daily candles were
also tested (per a "shorter, few-day hold" request) and rejected: every daily-candle
variant underperformed simply holding, sometimes badly.

Re-run `strategy_compare.py` against fresh data periodically to sanity-check these
still hold up; don't assume yesterday's winner stays the winner forever.

## Running paper mode
```
export LUNO_API_KEY_ID=...       # read-only key is enough
export LUNO_API_SECRET=...
python main.py --profile trend_4h
python main.py --profile range_1h_defensive
```
Each run fetches recent real prices, makes one decision, simulates the trade if
any, persists balance/position to `state/<profile>.json`, and logs to
`logs/<profile>/trade_log.csv`. Nothing here loops automatically — run manually,
or wire to Windows Task Scheduler / cron for hands-off operation (see below).

## Email notifications
Every trade (either profile, paper or live) sends an email via `core/notifier.py`.
Requires these env vars — unset means it just prints a warning and continues,
never crashes the trading loop:
```
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=you@gmail.com
EMAIL_APP_PASSWORD=...   # Gmail: Google Account -> Security -> 2-Step Verification -> App Passwords
EMAIL_TO=you@gmail.com
```
A trade sized at or above `BIG_TRADE_ALERT_PCT` (default 30%) of balance gets
flagged `[BIG TRADE]` in the subject line.

## Approval gate for big live trades
Paper/backtest never risk real money, so they just notify. In `MODE="live"`,
a trade at or above `BIG_TRADE_ALERT_PCT` is **not executed automatically** —
the bot emails you the proposed trade and waits. Nothing happens until you run:
```
python approve_trade.py trend_4h
```
The approval only fires if the bot still wants to make almost exactly that trade
on its next run (price within 1%) — if the market moved on, the stale proposal is
dropped and a fresh one queued, never executed blindly. This only activates once
a profile's `MODE` is `"live"`; it's inert in paper/backtest.

## Dashboard
```
python generate_dashboard.py
```
Renders `dashboard.html` (combined balance/P&L across both profiles, per-profile
stats, trade history table) from whatever's currently in `state/` and `logs/`.
Published as a Claude Artifact — re-run this and re-publish to refresh it after
new bot runs.

## Next steps toward live
1. Keep both paper profiles running for a few weeks and compare *forward*
   performance against the backtest expectations — this is the real test.
2. Only after paper results look consistent: set a profile's `MODE = "live"`
   in `config.py` (or via `core/profiles.py` per-profile override), and switch
   to an API key with **trade permission** (still no withdrawal).
3. Start with small real capital. The approval gate above will hold for any
   trade over 30% of balance until you explicitly confirm it.

## Weekly review loop
`core/logger.summarize_performance()` gives a plain-English performance summary.
Bring `logs/<profile>/trade_log.csv` back to a Claude Code session periodically —
it can analyze what's working, which indicator combos fire before wins vs losses,
and suggest rule tweaks.

## Scheduling (for hands-off paper trading)
Nothing here runs on its own yet. To let it run unattended, set up a Windows
Task Scheduler entry (or cron on Linux/Mac) that runs, on an interval matching
each profile's candle duration (e.g. every hour for `range_1h_defensive`, every
4 hours for `trend_4h`):
```
"%LOCALAPPDATA%\PythonEmbed312\python.exe" main.py --profile trend_4h
```
with working directory set to this folder and the `LUNO_API_KEY_ID` /
`LUNO_API_SECRET` / `EMAIL_*` env vars available to the scheduled task (set them
as persistent user environment variables via `setx`, not inline in the task).
Not set up automatically here — ask if you want help configuring this.

## Local environment (this machine, set up 2026-08-19)
No system Python was present, and neither `winget` nor the official installer
worked in this environment, so a self-contained Python was set up instead:
- Python 3.12.7 embeddable distribution at
  `%LOCALAPPDATA%\PythonEmbed312\python.exe` (pip bootstrapped, project deps
  from `requirements.txt` installed).
- A `sitecustomize.py` was added under that install's `site-packages/` so
  scripts can import local modules (e.g. `config`) relative to the current
  working directory — the embeddable distro's `python312._pth` file
  otherwise blocks normal script-directory path resolution.
- Run scripts with: `& "$env:LOCALAPPDATA\PythonEmbed312\python.exe" main.py ...`
  from inside this folder.
