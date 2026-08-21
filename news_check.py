"""
Checks for new Bitcoin headlines matching the important-keyword list and
sends a push notification for anything not already seen. Notification-only
- never places or influences a trade.

Usage:
    python news_check.py
"""

import os

from core import news, notifier

if __name__ == "__main__":
    headlines = news.fetch_bitcoin_headlines()
    important = [h for h in headlines if news.is_important(h["title"])]
    seen = news.load_seen_ids()
    first_run = not os.path.exists(news.SEEN_FILE)
    new_items = [] if first_run else [h for h in important if news.headline_id(h) not in seen]

    if first_run:
        print(f"First run: marking {len(important)} current important item(s) as seen "
              f"without notifying (establishing a baseline).")
        for item in important:
            seen.add(news.headline_id(item))
    elif not new_items:
        print(f"No new important news ({len(headlines)} checked, "
              f"{len(important)} matched keywords, rest already seen or none found).")
    else:
        print(f"{len(new_items)} new important news item(s):")
        for item in new_items:
            subject, body = news.format_notification(item)
            print(f"  - {subject}")
            notifier.notify_push_only(subject, body)
            seen.add(news.headline_id(item))

    news.save_seen_ids(seen)
