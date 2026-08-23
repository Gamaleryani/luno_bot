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
a trade at or above `BIG_TRADE_ALERT_PCT` is queued and you're notified
(email + push) — then one of three things happens:
1. You respond via the **"Respond to a pending approval"** link on the
   dashboard (a GitHub Actions form, works from your phone) — approve to
   execute now, or reject to cancel it outright.
2. You do nothing for `APPROVAL_TIMEOUT_SECONDS` (5 min by default) — it
   executes automatically anyway, as long as the trade still checks out
   (price hasn't moved past tolerance). This is a **deliberate fail-open**
   design (chosen so a missed notification doesn't mean a missed
   opportunity) — see `core/approval.py` for the full reasoning. Adjust the
   timeout in `config.py` if 5 minutes feels too short.
3. The market moves past tolerance before either happens — the stale
   proposal is dropped, never executed blindly.

This only activates once a profile's `MODE` is `"live"`; it's inert in
paper/backtest (paper trades just notify, never queue or block).

## Manual command interface
Query market state or issue a manual BUY/SELL for a profile, checked
against the same risk rules as the automated bot (position sizing caps,
balance checks) and logged like any other trade (tagged `MANUAL:` in the
reason column). Use the **"Manual command"** link on the dashboard — a
GitHub Actions form, works from your phone, no terminal needed:
```
QUERY trend_4h
BUY trend_4h 20
SELL range_1h_defensive
```
This is deliberately a GitHub Actions form, not a text box on the
dashboard itself — the dashboard is a public static page, and a control
that can execute real trades can't safely hold write credentials in
client-side JS that anyone visiting the site could read. The GitHub form
reuses your own login as the security boundary instead. A manual command
never goes through the approval queue above — typing an authenticated
command already **is** the approval.

## News awareness (notification-only, NOT a trading strategy)
```
python news_check.py
```
Checks Google News RSS for Bitcoin headlines every 30 minutes
(`.github/workflows/news_check.yml`), flags anything matching a hand-picked
list of high-impact keywords (`core/news.IMPORTANT_KEYWORDS` — regulation,
ETF, hacks, lawsuits, central bank/Fed moves, elections, crashes/surges,
etc.), and sends a **push notification only** (no email — this runs every
30 min and would flood an inbox) for anything new. First run establishes a
silent baseline instead of dumping the whole backlog as notifications.
**This never feeds into strategy.evaluate() or any buy/sell decision.**

Originally tried CryptoPanic (purpose-built crypto news with community
"important" voting) instead of keyword-matching Google News, but its API is
behind Cloudflare bot-protection that blocks datacenter/CI IPs outright —
confirmed both from this dev sandbox and from an actual GitHub Actions
runner, valid token and all, both got HTTP 403. Google News RSS has no such
block and needs no signup at all, at the cost of needing our own keyword
filter instead of a community-vote signal. `IMPORTANT_KEYWORDS` is a first
pass — tune it if it's too noisy or misses things.

Known limitation: the same story from multiple outlets (e.g. Reuters +
Yahoo Finance both covering one event) isn't deduplicated — each unique
article URL gets its own notification.

Why not a real trading strategy at all: researched this properly
(2026-08-21) before building anything — there isn't enough historical
political/regulatory event data to honestly backtest against (unlike the
price-only strategies, which had years of clean candle data), and crypto
typically reacts to news within minutes, faster than an hourly/4-hourly bot
can act on anyway. This gives the awareness/context benefit without
pretending we can systematize something we can't validate.

**Setup**: nothing needed beyond `NTFY_TOPIC` (already set) — no API key,
no signup. It's live already.

## Dashboard
```
python generate_dashboard.py
```
Renders `dashboard.html` (combined balance/P&L across both profiles, per-profile
stats, trade history table) from whatever's currently in `state/` and `logs/`.

**Live at https://gamaleryani.github.io/luno_bot/** — auto-deployed by GitHub
Actions after every bot run (see below), viewable from any device including
your phone, no manual refresh needed.

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

## Scheduling — runs in the cloud, not on this PC (set up 2026-08-21)
The bot runs on **GitHub Actions**, not this machine, so it keeps running (and
emailing, and updating the dashboard) even when this PC is off:
- Repo: **https://github.com/Gamaleryani/luno_bot** (public — see note below on why)
- `.github/workflows/trend_4h.yml` — runs every 4 hours
- `.github/workflows/range_1h_defensive.yml` — runs hourly
- Both call `.github/workflows/deploy_dashboard.yml` as a final step, which
  publishes `dashboard.html` to GitHub Pages
- Credentials (`LUNO_API_KEY_ID`, `LUNO_API_SECRET`, `EMAIL_*`) live as
  encrypted repo secrets (Settings → Secrets and variables → Actions) — never
  in the code
- Trigger a run manually any time: `gh workflow run trend_4h.yml` (or via the
  Actions tab on github.com), or check status with `gh run list`

**Why the repo is public**: GitHub Pages (needed for the phone-accessible
dashboard URL) isn't available for private repos on the free plan. Only code
and simulated paper-trading logs are public — no credentials, no real money.

**Local Windows Task Scheduler entries were removed** (they briefly existed
2026-08-21 as a first pass, called `LunoBot_trend_4h` /
`LunoBot_range_1h_defensive`) — running both local and cloud versions would
create two divergent trading histories with separate state files. The cloud
version is the only one running now. `run_profile.ps1` is kept in the repo for
reference / as a fallback if you ever want to run locally again instead.

To go live eventually, update the `MODE` in `core/profiles.py` and the repo
secrets to a trade-permission key the same way — no separate deployment step
needed, the workflow already reads from `config.py`/`core/profiles.py`.

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
