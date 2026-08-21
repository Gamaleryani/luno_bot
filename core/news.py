"""
Notification-only news awareness - NOT a trading signal. Pulls recent
Bitcoin headlines from Google News RSS (free, no signup, no API key - and
critically, not behind the Cloudflare bot-protection that blocks
datacenter/CI IPs like CryptoPanic's API does, which is why this isn't
CryptoPanic despite that being the original plan; see README) and flags
ones matching a hand-picked list of high-impact keywords. Never feeds into
strategy.evaluate() or any buy/sell decision.
"""

import hashlib
import json
import os
import xml.etree.ElementTree as ET

import requests

RSS_URL = "https://news.google.com/rss/search"
SEEN_FILE = "state/news_seen.json"
MAX_SEEN_IDS = 500

# Headlines must match at least one of these (case-insensitive) to count as
# "important" - a plain keyword list, not real sentiment analysis. Tune this
# list based on what turns out to be noise vs. signal in practice.
IMPORTANT_KEYWORDS = [
    "sec", "etf", "regulat", "ban", "hack", "exploit", "lawsuit", "sue",
    "seize", "crackdown", "legal tender", "central bank", "federal reserve",
    "fed rate", "interest rate", "election", "president", "sanction",
    "collapse", "crash", "plunge", "surge", "all-time high", "record high",
    "bankrupt", "insolvent", "halt", "outage", "delist",
]


def fetch_bitcoin_headlines() -> list:
    try:
        resp = requests.get(
            RSS_URL,
            params={"q": "bitcoin when:1d", "hl": "en-US", "gl": "US", "ceid": "US:en"},
            headers={"User-Agent": "Mozilla/5.0 (compatible; luno_bot/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            source = (item.findtext("source") or "unknown").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            items.append({"title": title, "link": link, "source": source, "pub_date": pub_date})
        return items
    except Exception as e:
        print(f"[news] failed to fetch headlines: {e}")
        return []


def is_important(title: str) -> bool:
    lower = title.lower()
    return any(kw in lower for kw in IMPORTANT_KEYWORDS)


def headline_id(item: dict) -> str:
    return hashlib.sha1(item["link"].encode("utf-8")).hexdigest()[:16]


def load_seen_ids(path: str = SEEN_FILE) -> set:
    if os.path.exists(path):
        with open(path) as f:
            return set(json.load(f))
    return set()


def save_seen_ids(ids: set, path: str = SEEN_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    trimmed = list(ids)[-MAX_SEEN_IDS:]
    with open(path, "w") as f:
        json.dump(trimmed, f)


def format_notification(item: dict) -> tuple:
    subject = f"[NEWS] {item['title']}"
    body = f"Source: {item['source']}\n{item['pub_date']}\n\n{item['link']}"
    return subject, body
