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

## Status (2026-08-25)
Backtested extensively against real historical data (30d–2.7yr, multiple candle
durations, 15 variants per pair, all compared against a buy-and-hold benchmark —
not just raw returns, since much of a "profit" can just be the asset's own price
rise/fall). Four profiles have survived this process and are running in
**paper mode**, across three different pairs — a strategy validated on one coin
is NOT assumed to transfer to another; each was backtested on its own pair's
real history before being added:

**XBTMYR (Bitcoin):**
- **`trend_4h`** — 4h candles, 5%/8% stop-loss/take-profit. Swing-trading style,
  ~4.7 day average hold. Beats buy-and-hold when the market trends.
- **`range_1h_defensive`** — 1h candles, ranging-regime-only, 2%/3% stop/take-profit.
  ~1-3 day average hold. The only config that stayed profitable through a falling
  market (1-year window where buy-and-hold lost -40.67%, this made +2.59%).

**ETHMYR (Ethereum):**
- **`eth_range_4h`** — 4h candles, ranging-regime-only, 2-of-4 signal agreement
  (config.py's default 3%/5% stop/take-profit, unchanged). Validated across both
  a 1-year and 2-year window where ETH itself was down -49% and -17%
  respectively — this was the only variant that stayed profitable in absolute
  terms in both, beating buy-and-hold by 50%+ and 26%+. Same "mean-reversion
  over trend-following" pattern as `range_1h_defensive` found independently
  for Bitcoin — worth noting if adding more pairs later.

**SOLMYR (Solana):**
- **`sol_range_1h`** — same structure as `range_1h_defensive` (1h candles,
  ranging-regime-only, 2%/3% stop/take-profit) - turned out to transfer.
  Positive in both a 180-day window (+6.23%, though SOL itself rallied
  +15.27% there so this trails buy-and-hold, as expected for a defensive
  strategy in a rally) and a 1-year window (+3.24%, beating buy-and-hold by
  +56.63% - SOL was down -53% there).

**LTCMYR was tested and rejected** (2026-08-25) — 4h and 1h candles, multiple
windows, 15 variants each: no configuration showed a consistent sign across
windows (whatever won in one window lost in another), the classic curve-fit
signature. Don't re-add it without a materially different approach.

None of these are proven — 1-3 years of one asset's history is still a small
sample — but they're the strongest evidence-backed candidates found so far.
Daily candles were also tested for BTC (per a "shorter, few-day hold" request)
and rejected: every daily-candle variant underperformed simply holding,
sometimes badly.

**Also tested and rejected as strategy types (2026-08-25)**:
- **DCA** (buy a fixed amount on a fixed schedule, no signals) — tested across
  BTC, ETH, and SOL, multiple windows each (7 tests total). Never once
  produced a positive absolute return, though it reliably beat lump-sum
  buy-and-hold by cushioning declines. Real property, wrong tool: it reduces
  risk, it doesn't generate profit. `dca_backtest.py` still exists if you
  want to re-check it, but nothing DCA-based is deployed.
- **Day trading** (forced exit within 12-24h via `core/risk.py`'s
  `MAX_HOLD_HOURS`, opt-in and unused by any live profile) — tested across
  BTC, ETH, SOL, multiple windows (16 tests total). Every single one came
  back negative. Combined with 5-minute candles failing earlier for the same
  reason, short holding periods appear to systematically lose to fees/noise
  with this indicator framework - the validated profiles' multi-day holds
  aren't incidental, they're load-bearing.
- **"Buy the dip" as a standalone strategy** wasn't separately tested because
  it's not actually new: `range_1h_defensive`, `eth_range_4h`, and
  `sol_range_1h` already ARE buy-the-dip strategies at their core (they buy
  when RSI/Bollinger Bands show oversold conditions during ranging markets).

**Fee accounting fixed 2026-08-24**: `main.py` (automated) and
`manual_command.py` (manual BUY/SELL) now both deduct `TAKER_FEE_PCT` on
every trade leg, matching what `backtest.py` always did. Before this fix,
every live/paper trade's logged balance was missing the ~0.1%-per-leg fee -
slightly optimistic. Not retroactively corrected in old log rows (that
would rewrite history); only trades from this date forward are accurate.

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
HOLD trend_4h
RESUME trend_4h
```
`BUY` on a profile that's already holding **adds to the position** instead
of refusing — the entry price becomes the size-weighted average of both
buys (so stop-loss/take-profit apply against that average, not the
original entry alone). `SELL` always closes the whole position at once,
however it was built up.

`HOLD` tells the **automated** bot to stop managing an open position
entirely — no stop-loss, no take-profit, no strategy SELL signal, every
run, until you `SELL` or `RESUME` it. This is a real safety trade-off, not
a convenience toggle: while it's on, there's no automatic loss protection
on that position. The dashboard shows a red banner on any profile with
HOLD active so it's never silently forgotten. `RESUME` turns it back off.

This is deliberately a GitHub Actions form, not a text box on the
dashboard itself — the dashboard is a public static page, and a control
that can execute real trades can't safely hold write credentials in
client-side JS that anyone visiting the site could read. The GitHub form
reuses your own login as the security boundary instead. A manual command
never goes through the approval queue above — typing an authenticated
command already **is** the approval.

Every outcome (QUERY's result, a successful or refused BUY/SELL, HOLD/RESUME
confirmation) is pushed to your phone via ntfy — no need to open the Actions
log to see what happened.

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

## Adding another trading pair
Don't just copy an existing profile's settings onto a new pair - a
strategy tuned for one coin's volatility isn't assumed to work for
another (see `eth_range_4h`'s docstring in `core/profiles.py` for why it
uses different settings than the BTC profiles). The process each time:
1. `python data/fetch_history.py --pair <PAIR> --days <N> --duration <secs> --out data/<name>.csv`
   for at least two different window lengths (e.g. 1yr and 2yr).
2. `python strategy_compare.py data/<name>.csv` on each window - look for a
   variant that beats the buy-and-hold benchmark consistently across
   windows with a real trade count (not a 2-trade fluke), same rigor as
   `strategy_compare.py`'s own output history in this repo's commits.
3. Add a new entry to `core/profiles.py`'s `PROFILES` dict with that
   variant's settings plus `"PAIR": "<PAIR>"`, and a `schedule` matching a
   new cron.
4. Add the profile to `allocations.json`, copy `.github/workflows/range_1h_defensive.yml`
   as a template for the new workflow (swap the profile name and cron),
   and add the profile name to `respond_approval.yml`'s choice list.
5. The dashboard, manual command interface, and approval gate all pick up
   any profile in `PROFILES` automatically - no other code changes needed.

## Weekly review loop
Two automated, scheduled checks (added 2026-08-25) run without you asking:

- **`weekly_report.py`** (`.github/workflows/weekly_report.yml`, every Monday
  08:00 UTC) — emails a plain-English digest of actual paper-trading results
  across every profile: balance, all-time %, and this week's closed-trade
  P&L. This reports what already happened - it doesn't re-run any backtest.
- **`revalidate.py`** (`.github/workflows/revalidate.yml`, the 1st and 15th
  of each month) — re-checks each profile's *own deployed configuration*
  against the last 90 days of fresh real data, comparing to a buy-and-hold
  benchmark, and sends an alert if it's now underperforming. This does
  **not** auto-disable or change anything - a defensive/mean-reversion
  profile trailing buy-and-hold during a rally is often expected behavior,
  not proof the edge broke; deciding what (if anything) to do about a flag
  is a human call, same philosophy as the approval gate.

You can still bring `logs/<profile>/trade_log.csv` back to a Claude Code
session manually anytime for a deeper look — `core/logger.summarize_performance()`
gives a plain-English summary, and a session can analyze which indicator
combos fire before wins vs losses and suggest rule tweaks.

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
