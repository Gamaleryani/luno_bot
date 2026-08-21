"""
Reads every profile's state + trade log and writes a single self-contained
HTML dashboard (dashboard.html) summarizing balances, open positions, and
trade history. Meant to be regenerated periodically and re-published (see
README "Dashboard" section) - it does not read live prices itself, only
what main.py has already logged.

Usage:
    python generate_dashboard.py
"""

import csv
import html
import json
import os
from datetime import datetime, timedelta, timezone

import config as cfg
from core.profiles import PROFILES

STATE_DIR = "state"
LOG_DIR_ROOT = "logs"
OUT_FILE = "dashboard.html"


def next_run_utc(schedule: dict, now: datetime = None) -> datetime:
    """Computes the next cron firing for a simple 'every N hours at minute M'
    schedule (matches the .github/workflows/*.yml cron expressions - keep
    interval_hours/minute_offset in core/profiles.py in sync with those)."""
    now = now or datetime.now(timezone.utc)
    interval = schedule["interval_hours"]
    minute = schedule["minute_offset"]
    candidate = now.replace(minute=minute, second=0, microsecond=0)
    # round current hour down to the nearest interval boundary, then step
    # forward in `interval`-hour jumps until we're at/after `now`
    candidate = candidate.replace(hour=(now.hour // interval) * interval)
    while candidate <= now:
        candidate += timedelta(hours=interval)
    return candidate


def format_countdown(target: datetime, now: datetime = None) -> str:
    now = now or datetime.now(timezone.utc)
    delta = target - now
    total_minutes = max(0, int(delta.total_seconds() // 60))
    hours, minutes = divmod(total_minutes, 60)
    if hours:
        return f"in {hours}h {minutes}m"
    return f"in {minutes}m"


def load_profile_data(name: str) -> dict:
    state_path = os.path.join(STATE_DIR, f"{name}.json")
    log_path = os.path.join(LOG_DIR_ROOT, name, "trade_log.csv")

    state = {"balance": cfg.STARTING_BALANCE_MYR, "position": None}
    if os.path.exists(state_path):
        with open(state_path) as f:
            state = json.load(f)

    trades = []
    if os.path.exists(log_path):
        with open(log_path, newline="") as f:
            trades = list(csv.DictReader(f))

    return {"state": state, "trades": trades}


def regime_of_last_trade(trades) -> str:
    for t in reversed(trades):
        if t.get("regime") and t["regime"] != "-":
            return t["regime"]
    return "unknown"


def render_card(name: str, data: dict) -> str:
    label = html.escape(PROFILES[name].get("label", name))
    balance = data["state"]["balance"]
    position = data["state"]["position"]
    pnl = balance - cfg.STARTING_BALANCE_MYR
    pnl_pct = (pnl / cfg.STARTING_BALANCE_MYR * 100) if cfg.STARTING_BALANCE_MYR else 0
    pnl_class = "pos" if pnl >= 0 else "neg"
    regime = regime_of_last_trade(data["trades"])

    if position:
        pos_chip = f'<span class="chip chip-active">position open</span>'
        pos_detail = (f"{position['size_units']:.8f} XBT @ {position['entry_price']:,.2f} "
                       f"&middot; {position['size_myr']:.2f} MYR")
    else:
        pos_chip = '<span class="chip chip-flat">flat</span>'
        pos_detail = "no open position"

    trade_rows = ""
    for t in reversed(data["trades"][-30:]):
        action = t.get("action", "")
        trade_rows += (
            "<tr>"
            f'<td class="mono muted">{html.escape(t.get("timestamp", ""))}</td>'
            f'<td><span class="chip chip-{"buy" if action == "BUY" else "sell"}">{html.escape(action)}</span></td>'
            f'<td class="mono num">{html.escape(t.get("price", ""))}</td>'
            f'<td class="mono num">{html.escape(t.get("balance", ""))}</td>'
            f'<td class="muted">{html.escape(t.get("regime", ""))}</td>'
            f'<td class="reason">{html.escape(t.get("reason", ""))}</td>'
            "</tr>\n"
        )
    if not trade_rows:
        trade_rows = '<tr><td colspan="6" class="empty">No trades logged yet - still watching the market.</td></tr>'

    schedule = PROFILES[name].get("schedule")
    next_run_html = ""
    if schedule:
        nxt = next_run_utc(schedule)
        next_run_html = (f'<span class="next-run">next check: '
                          f'<span class="mono">{format_countdown(nxt)}</span> '
                          f'({nxt.strftime("%H:%M")} UTC)</span>')

    return f"""
    <section class="card">
      <header class="card-head">
        <div>
          <h2>{label}</h2>
          <span class="regime-tag">last seen regime: {html.escape(regime)}</span>
          {next_run_html}
        </div>
        {pos_chip}
      </header>
      <div class="stat-grid">
        <div class="stat">
          <span class="stat-label">Balance</span>
          <span class="mono num stat-value">{balance:,.2f} <span class="unit">MYR</span></span>
        </div>
        <div class="stat">
          <span class="stat-label">Profit / loss</span>
          <span class="mono num stat-value {pnl_class}">{pnl:+,.2f} <span class="unit">({pnl_pct:+.2f}%)</span></span>
        </div>
        <div class="stat stat-wide">
          <span class="stat-label">Position</span>
          <span class="mono stat-value-sm">{pos_detail}</span>
        </div>
        <div class="stat">
          <span class="stat-label">Trades logged</span>
          <span class="mono num stat-value">{len(data['trades'])}</span>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Time</th><th>Action</th><th>Price</th><th>Balance</th><th>Regime</th><th>Reason</th></tr></thead>
          <tbody>{trade_rows}</tbody>
        </table>
      </div>
    </section>
    """


if __name__ == "__main__":
    profile_data = {name: load_profile_data(name) for name in PROFILES}
    total_balance = sum(d["state"]["balance"] for d in profile_data.values())
    total_start = cfg.STARTING_BALANCE_MYR * len(PROFILES)
    total_pnl = total_balance - total_start
    total_pnl_pct = (total_pnl / total_start * 100) if total_start else 0
    open_count = sum(1 for d in profile_data.values() if d["state"]["position"])
    total_trades = sum(len(d["trades"]) for d in profile_data.values())

    sections = "".join(render_card(name, profile_data[name]) for name in PROFILES)
    summary_class = "pos" if total_pnl >= 0 else "neg"

    html_doc = f"""<title>Luno Bot Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #eef1f6;
    --surface: #ffffff;
    --surface-2: #f4f6fb;
    --text: #171b26;
    --muted: #64708a;
    --border: rgba(23, 27, 38, 0.09);
    --accent: #a8722f;
    --accent-bg: rgba(168, 114, 47, 0.12);
    --pos: #197a52;
    --pos-bg: rgba(25, 122, 82, 0.12);
    --neg: #b8323b;
    --neg-bg: rgba(184, 50, 59, 0.11);
    --font-display: "IBM Plex Sans", -apple-system, Segoe UI, sans-serif;
    --font-mono: "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg: #090c12;
      --surface: #121722;
      --surface-2: #1a2030;
      --text: #e7eaf2;
      --muted: #8b93a8;
      --border: rgba(255, 255, 255, 0.08);
      --accent: #dba25e;
      --accent-bg: rgba(219, 162, 94, 0.14);
      --pos: #3ecf8e;
      --pos-bg: rgba(62, 207, 142, 0.13);
      --neg: #f0645c;
      --neg-bg: rgba(240, 100, 92, 0.13);
    }}
  }}
  :root[data-theme="dark"] {{
    --bg: #090c12;
    --surface: #121722;
    --surface-2: #1a2030;
    --text: #e7eaf2;
    --muted: #8b93a8;
    --border: rgba(255, 255, 255, 0.08);
    --accent: #dba25e;
    --accent-bg: rgba(219, 162, 94, 0.14);
    --pos: #3ecf8e;
    --pos-bg: rgba(62, 207, 142, 0.13);
    --neg: #f0645c;
    --neg-bg: rgba(240, 100, 92, 0.13);
  }}

  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-display);
    margin: 0;
    padding: 32px 24px 64px;
    -webkit-font-smoothing: antialiased;
  }}
  .mono {{ font-family: var(--font-mono); }}
  .num {{ font-variant-numeric: tabular-nums; }}
  .muted {{ color: var(--muted); }}

  .page {{ max-width: 980px; margin: 0 auto; display: flex; flex-direction: column; gap: 28px; }}

  .masthead {{ display: flex; flex-direction: column; gap: 4px; }}
  .eyebrow {{
    font-family: var(--font-mono); font-size: 0.72rem; letter-spacing: 0.09em; text-transform: uppercase;
    color: var(--accent); font-weight: 600;
  }}
  h1 {{ font-size: 1.65rem; margin: 2px 0 0; font-weight: 700; text-wrap: balance; }}
  .subtitle {{ color: var(--muted); font-size: 0.9rem; margin-top: 4px; }}

  .summary-bar {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
    padding: 18px 22px; display: flex; flex-wrap: wrap; gap: 24px; align-items: center;
  }}
  .summary-stat {{ display: flex; flex-direction: column; gap: 2px; min-width: 120px; }}
  .summary-stat .stat-label {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .summary-stat .stat-value {{ font-size: 1.2rem; font-weight: 600; }}
  .mode-badge {{
    font-family: var(--font-mono); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em;
    text-transform: uppercase; padding: 4px 10px; border-radius: 999px;
    background: var(--accent-bg); color: var(--accent); margin-left: auto;
  }}

  .card {{
    background: var(--surface); border: 1px solid var(--border); border-radius: 16px;
    padding: 22px 24px 8px;
  }}
  .card-head {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 18px; }}
  .card-head > div {{ display: flex; flex-direction: column; gap: 3px; }}
  .card-head h2 {{ margin: 0; font-size: 1.15rem; font-weight: 600; }}
  .regime-tag {{ font-size: 0.78rem; color: var(--muted); }}
  .next-run {{ font-size: 0.78rem; color: var(--accent); }}
  .next-run .mono {{ font-weight: 600; }}

  .chip {{
    font-family: var(--font-mono); font-size: 0.7rem; font-weight: 600; letter-spacing: 0.04em;
    text-transform: uppercase; padding: 3px 9px; border-radius: 999px; white-space: nowrap;
  }}
  .chip-active {{ background: var(--accent-bg); color: var(--accent); }}
  .chip-flat {{ background: var(--surface-2); color: var(--muted); }}
  .chip-buy {{ background: var(--pos-bg); color: var(--pos); }}
  .chip-sell {{ background: var(--neg-bg); color: var(--neg); }}

  .stat-grid {{
    display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px 20px;
    padding-bottom: 20px; border-bottom: 1px solid var(--border); margin-bottom: 4px;
  }}
  .stat {{ display: flex; flex-direction: column; gap: 3px; min-width: 0; }}
  .stat-wide {{ grid-column: span 2; }}
  .stat-label {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .stat-value {{ font-size: 1.15rem; font-weight: 600; }}
  .stat-value-sm {{ font-size: 0.85rem; font-weight: 500; overflow-wrap: break-word; }}
  .unit {{ font-size: 0.75rem; font-weight: 500; color: var(--muted); }}
  .pos {{ color: var(--pos); }}
  .neg {{ color: var(--neg); }}

  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.83rem; margin: 8px 0 16px; }}
  th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ color: var(--muted); font-weight: 500; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }}
  td.reason {{ color: var(--muted); max-width: 320px; }}
  .empty {{ color: var(--muted); text-align: center; padding: 22px; font-style: italic; }}

  @media (max-width: 640px) {{
    .stat-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .stat-wide {{ grid-column: span 2; }}
  }}
</style>
<div class="page">
  <div class="masthead">
    <span class="eyebrow">{html.escape(cfg.PAIR)} &middot; paper mode</span>
    <h1>Luno Bot Dashboard</h1>
    <span class="subtitle">Two strategies running in parallel, no real capital at risk. Regenerate after each bot run to refresh.</span>
  </div>

  <div class="summary-bar">
    <div class="summary-stat">
      <span class="stat-label">Combined balance</span>
      <span class="mono num stat-value">{total_balance:,.2f} MYR</span>
    </div>
    <div class="summary-stat">
      <span class="stat-label">Combined P/L</span>
      <span class="mono num stat-value {summary_class}">{total_pnl:+,.2f} MYR ({total_pnl_pct:+.2f}%)</span>
    </div>
    <div class="summary-stat">
      <span class="stat-label">Open positions</span>
      <span class="mono num stat-value">{open_count} / {len(PROFILES)}</span>
    </div>
    <div class="summary-stat">
      <span class="stat-label">Trades logged</span>
      <span class="mono num stat-value">{total_trades}</span>
    </div>
    <span class="mode-badge">{html.escape(cfg.MODE)}</span>
  </div>

  {sections}
</div>
"""
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"Wrote {OUT_FILE}")
