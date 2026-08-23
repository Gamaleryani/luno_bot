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
from datetime import datetime, timezone

import config as cfg
from core.profiles import PROFILES
from core.reports import compute_window_report
from core.allocations import load_allocation

STATE_DIR = "state"
LOG_DIR_ROOT = "logs"
OUT_FILE = "dashboard.html"

# "Next run" is computed live in the browser (see the <script> at the end of
# the page), not baked in here as static text - this file is only
# regenerated when a bot run happens, so a server-computed countdown would
# freeze at whatever it said at that moment and look broken to anyone
# viewing the page later (this is exactly what happened before this fix -
# see git history 2026-08-21).


def load_profile_data(name: str) -> dict:
    state_path = os.path.join(STATE_DIR, f"{name}.json")
    log_path = os.path.join(LOG_DIR_ROOT, name, "trade_log.csv")
    price_log_path = os.path.join(LOG_DIR_ROOT, name, "price_log.csv")

    state = {"balance": load_allocation(name, cfg.STARTING_BALANCE_MYR), "position": None}
    if os.path.exists(state_path):
        with open(state_path) as f:
            state = json.load(f)

    trades = []
    if os.path.exists(log_path):
        with open(log_path, newline="") as f:
            trades = list(csv.DictReader(f))

    prices = []
    if os.path.exists(price_log_path):
        with open(price_log_path, newline="") as f:
            prices = list(csv.DictReader(f))

    return {"state": state, "trades": trades, "prices": prices}


def last_seen_regime(prices, trades) -> str:
    """Prefers price_log (updated on EVERY run, including HOLDs) over
    trade_log (only updated when a trade actually happens) - a strategy
    that hasn't traded yet still knows the current regime, and showing
    'unknown' for it is misleading."""
    for p in reversed(prices):
        if p.get("regime") and p["regime"] != "-":
            return p["regime"]
    for t in reversed(trades):
        if t.get("regime") and t["regime"] != "-":
            return t["regime"]
    return "unknown"


REAL_TRADE_ACTIONS = {"BUY", "SELL"}


def count_real_trades(trades) -> int:
    """Excludes non-trade audit rows (e.g. RESET) from trade counts."""
    return sum(1 for t in trades if t.get("action") in REAL_TRADE_ACTIONS)


def render_card(name: str, data: dict) -> str:
    label = html.escape(PROFILES[name].get("label", name))
    balance = data["state"]["balance"]
    position = data["state"]["position"]
    allocation = load_allocation(name, cfg.STARTING_BALANCE_MYR)
    pnl = balance - allocation
    pnl_pct = (pnl / allocation * 100) if allocation else 0
    pnl_class = "pos" if pnl >= 0 else "neg"
    regime = last_seen_regime(data["prices"], data["trades"])
    real_trade_count = count_real_trades(data["trades"])

    if position:
        pos_chip = f'<span class="chip chip-active">position open</span>'
        pos_detail = (f"{position['size_units']:.8f} XBT @ {position['entry_price']:,.2f} "
                       f"&middot; {position['size_myr']:.2f} MYR")
    else:
        pos_chip = '<span class="chip chip-flat">flat</span>'
        pos_detail = "no open position"

    chip_class = {"BUY": "buy", "SELL": "sell"}
    trade_rows = ""
    for t in reversed(data["trades"][-30:]):
        action = t.get("action", "")
        trade_rows += (
            "<tr>"
            f'<td class="mono muted">{html.escape(t.get("timestamp", ""))}</td>'
            f'<td><span class="chip chip-{chip_class.get(action, "flat")}">{html.escape(action)}</span></td>'
            f'<td class="mono num">{html.escape(t.get("price") or "—")}</td>'
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
        next_run_html = (
            f'<span class="next-run" data-interval-hours="{schedule["interval_hours"]}" '
            f'data-minute-offset="{schedule["minute_offset"]}">'
            f'next check: <span class="mono next-run-text">calculating&hellip;</span></span>'
        )

    # --- report panel: today (24h) and this week (7d) ---
    today = compute_window_report(data["trades"], allocation, 24)
    week = compute_window_report(data["trades"], allocation, 24 * 7)

    def report_html(label_text, r):
        if r["trade_count"] == 0:
            return (f'<div class="report"><span class="report-label">{label_text}</span>'
                     f'<span class="report-body muted">No closed trades in this window.</span></div>')
        cls = "pos" if r["net_change"] >= 0 else "neg"
        return (
            f'<div class="report">'
            f'<span class="report-label">{label_text}</span>'
            f'<span class="report-body">'
            f'<span class="mono num {cls}">{r["net_change"]:+.2f} MYR</span> &middot; '
            f'{r["trade_count"]} closed ({r["wins"]}W / {r["losses"]}L)'
            f'</span></div>'
        )

    # --- price/trade chart data (embedded as JSON for Chart.js) ---
    price_points = [{"t": p["timestamp"], "y": float(p["price"])} for p in data["prices"] if p.get("price")]
    buy_points = [{"t": t["timestamp"], "y": float(t["price"])} for t in data["trades"] if t.get("action") == "BUY"]
    sell_points = [{"t": t["timestamp"], "y": float(t["price"])} for t in data["trades"] if t.get("action") == "SELL"]
    chart_html = ""
    if price_points:
        chart_id = f"chart-{name}"
        chart_data = json.dumps({"price": price_points, "buys": buy_points, "sells": sell_points})
        chart_html = (
            f'<div class="chart-wrap"><canvas id="{chart_id}" height="220"></canvas></div>'
            f'<script type="application/json" class="chart-data" data-chart-id="{chart_id}">'
            f'{chart_data}</script>'
        )
    else:
        chart_html = ('<div class="chart-wrap chart-empty">Price chart will appear once a few runs have '
                       'logged data (started 2026-08-21 - no history before that).</div>')

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
          <span class="mono muted" style="font-size:0.72rem;">allocated: {allocation:,.2f} MYR</span>
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
          <span class="mono num stat-value">{real_trade_count}</span>
        </div>
      </div>

      {chart_html}

      <div class="report-row">
        {report_html("Today", today)}
        {report_html("This week", week)}
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
    total_start = sum(load_allocation(name, cfg.STARTING_BALANCE_MYR) for name in PROFILES)
    total_pnl = total_balance - total_start
    total_pnl_pct = (total_pnl / total_start * 100) if total_start else 0
    open_count = sum(1 for d in profile_data.values() if d["state"]["position"])
    total_trades = sum(count_real_trades(d["trades"]) for d in profile_data.values())

    sections = "".join(render_card(name, profile_data[name]) for name in PROFILES)
    summary_class = "pos" if total_pnl >= 0 else "neg"

    html_doc = f"""<title>Luno Bot Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#090c12">
<link rel="manifest" href="manifest.json">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" href="icon-192.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>
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
  .link-row {{ display: flex; flex-wrap: wrap; gap: 8px 20px; align-self: flex-start; }}
  .manage-link {{
    font-size: 0.82rem; color: var(--accent); text-decoration: none;
    font-weight: 500; display: inline-flex; align-items: center; gap: 4px;
  }}
  .manage-link:hover {{ text-decoration: underline; }}
  .manage-link:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }}

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

  .chart-wrap {{ margin: 4px 0 18px; }}
  .chart-empty {{
    display: flex; align-items: center; justify-content: center; text-align: center;
    height: 100px; color: var(--muted); font-size: 0.82rem; font-style: italic;
    background: var(--surface-2); border-radius: 10px; padding: 12px;
  }}

  .report-row {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
    margin-bottom: 18px;
  }}
  .report {{
    background: var(--surface-2); border-radius: 10px; padding: 12px 14px;
    display: flex; flex-direction: column; gap: 4px;
  }}
  .report-label {{ font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.05em; }}
  .report-body {{ font-size: 0.88rem; }}

  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.83rem; margin: 8px 0 16px; }}
  th, td {{ text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{ color: var(--muted); font-weight: 500; font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }}
  td.reason {{ color: var(--muted); max-width: 320px; }}
  .empty {{ color: var(--muted); text-align: center; padding: 22px; font-style: italic; }}

  @media (max-width: 640px) {{
    .stat-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .stat-wide {{ grid-column: span 2; }}
    .report-row {{ grid-template-columns: 1fr; }}
  }}
</style>
<div class="page">
  <div class="masthead">
    <span class="eyebrow">{html.escape(cfg.PAIR)} &middot; paper mode</span>
    <h1>Luno Bot Dashboard</h1>
    <span class="subtitle">Two strategies running in parallel against real live prices, no real capital at risk.</span>
    <span class="subtitle mono">Data as of this page's last bot run: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</span>
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

  <div class="link-row">
    <a class="manage-link" href="https://github.com/Gamaleryani/luno_bot/edit/main/allocations.json" target="_blank" rel="noopener">
      Manage allocations &rarr;
    </a>
    <a class="manage-link" href="https://github.com/Gamaleryani/luno_bot/actions/workflows/manual_command.yml" target="_blank" rel="noopener">
      Manual command (query / buy / sell) &rarr;
    </a>
    <a class="manage-link" href="https://github.com/Gamaleryani/luno_bot/actions/workflows/respond_approval.yml" target="_blank" rel="noopener">
      Respond to a pending approval &rarr;
    </a>
  </div>

  {sections}
</div>
<script>
  if ("serviceWorker" in navigator) {{
    window.addEventListener("load", () => {{
      navigator.serviceWorker.register("sw.js").catch(() => {{}});
    }});
  }}

  // Live "next run" countdown - computed from the viewer's own clock, not
  // baked in at page-generation time, so it stays correct no matter how
  // long ago this static file was last regenerated.
  function nextRunUTC(intervalHours, minuteOffset, now) {{
    const candidate = new Date(now);
    candidate.setUTCMinutes(minuteOffset, 0, 0);
    candidate.setUTCHours(Math.floor(now.getUTCHours() / intervalHours) * intervalHours);
    while (candidate <= now) {{
      candidate.setUTCHours(candidate.getUTCHours() + intervalHours);
    }}
    return candidate;
  }}

  function updateCountdowns() {{
    const now = new Date();
    document.querySelectorAll(".next-run").forEach((el) => {{
      const interval = parseInt(el.dataset.intervalHours, 10);
      const minute = parseInt(el.dataset.minuteOffset, 10);
      const target = nextRunUTC(interval, minute, now);
      const totalMinutes = Math.max(0, Math.floor((target - now) / 60000));
      const hours = Math.floor(totalMinutes / 60);
      const minutes = totalMinutes % 60;
      const countdown = hours > 0 ? `in ${{hours}}h ${{minutes}}m` : `in ${{minutes}}m`;
      const hh = String(target.getUTCHours()).padStart(2, "0");
      const mm = String(target.getUTCMinutes()).padStart(2, "0");
      el.querySelector(".next-run-text").textContent = `${{countdown}} (${{hh}}:${{mm}} UTC)`;
    }});
  }}
  updateCountdowns();
  setInterval(updateCountdowns, 15000);

  // Price chart per profile: line = price over time (every bot run, since
  // 2026-08-21), green/red dots = actual buy/sell trades.
  document.querySelectorAll(".chart-data").forEach((el) => {{
    const data = JSON.parse(el.textContent);
    const canvas = document.getElementById(el.dataset.chartId);
    if (!canvas || typeof Chart === "undefined") return;
    const styles = getComputedStyle(document.documentElement);
    const accent = styles.getPropertyValue("--accent").trim();
    const pos = styles.getPropertyValue("--pos").trim();
    const neg = styles.getPropertyValue("--neg").trim();
    const muted = styles.getPropertyValue("--muted").trim();
    const border = styles.getPropertyValue("--border").trim();

    new Chart(canvas, {{
      type: "line",
      data: {{
        datasets: [
          {{
            label: "Price", data: data.price, parsing: {{xAxisKey: "t", yAxisKey: "y"}},
            borderColor: accent, backgroundColor: "transparent", borderWidth: 1.5,
            pointRadius: 0, tension: 0.15,
          }},
          {{
            label: "Buy", data: data.buys, parsing: {{xAxisKey: "t", yAxisKey: "y"}},
            type: "scatter", backgroundColor: pos, borderColor: pos,
            pointRadius: 5, pointStyle: "triangle",
          }},
          {{
            label: "Sell", data: data.sells, parsing: {{xAxisKey: "t", yAxisKey: "y"}},
            type: "scatter", backgroundColor: neg, borderColor: neg,
            pointRadius: 5, pointStyle: "rectRot",
          }},
        ],
      }},
      options: {{
        responsive: true, maintainAspectRatio: false,
        interaction: {{mode: "nearest", axis: "x", intersect: false}},
        scales: {{
          x: {{type: "time", ticks: {{color: muted, maxTicksLimit: 6}}, grid: {{color: border}}}},
          y: {{ticks: {{color: muted}}, grid: {{color: border}}}},
        }},
        plugins: {{
          legend: {{labels: {{color: muted, boxWidth: 12, font: {{size: 11}}}}}},
        }},
      }},
    }});
  }});
</script>
"""
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html_doc)
    print(f"Wrote {OUT_FILE}")
