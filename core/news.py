"""
Notification-only news awareness - NOT a trading signal. Pulls crypto news
flagged as "important" by CryptoPanic's community voting (not our own
sentiment guess), filtered to BTC, and pushes a notification for anything
new. Never feeds into strategy.evaluate() or any buy/sell decision - see
README for why (can't honestly backtest political/news events, free data
is rate-limited, and crypto reacts to news faster than our polling cadence
anyway).

Requires CRYPTOPANIC_API_TOKEN (free signup at
https://cryptopanic.com/developers/api/). Without it, prints a warning and
does nothing - same pattern as core/notifier.py.
"""

import os

import requests

API_URL = "https://cryptopanic.com/api/v2/posts/"
SEEN_FILE = "state/news_seen.json"
MAX_SEEN_IDS = 500  # cap so the seen-list file doesn't grow forever


def fetch_important_posts(currency: str = "BTC") -> list:
    token = os.environ.get("CRYPTOPANIC_API_TOKEN")
    if not token:
        print("[news] CRYPTOPANIC_API_TOKEN not set - skipping news check.")
        return []
    try:
        resp = requests.get(
            API_URL,
            params={"auth_token": token, "currencies": currency,
                    "filter": "important", "kind": "news"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        print(f"[news] failed to fetch: {e}")
        return []


def load_seen_ids(path: str = SEEN_FILE) -> set:
    import json
    if os.path.exists(path):
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_seen_ids(ids: set, path: str = SEEN_FILE):
    import json
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # keep only the most recent MAX_SEEN_IDS (ids are roughly increasing)
    trimmed = sorted(ids, reverse=True)[:MAX_SEEN_IDS]
    with open(path, "w") as f:
        json.dump(trimmed, f)


def format_notification(post: dict) -> tuple:
    title = post.get("title", "(no title)")
    source = (post.get("source") or {}).get("title", "unknown source")
    url = post.get("url") or post.get("original_url") or ""
    votes = post.get("votes") or {}
    subject = f"[NEWS] {title}"
    body = f"Source: {source}\nImportant votes: {votes.get('important', '?')}\n\n{url}"
    return subject, body
