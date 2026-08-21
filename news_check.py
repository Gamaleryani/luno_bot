"""
Checks for new important BTC news and sends a notification for anything
not already seen. Notification-only - never places or influences a trade.

Usage:
    python news_check.py
"""

from core import news, notifier

if __name__ == "__main__":
    posts = news.fetch_important_posts("BTC")
    seen = news.load_seen_ids()
    new_posts = [p for p in posts if str(p.get("id")) not in seen]

    if not new_posts:
        print(f"No new important news ({len(posts)} checked, all already seen or none found).")
    else:
        print(f"{len(new_posts)} new important news item(s):")
        for post in new_posts:
            subject, body = news.format_notification(post)
            print(f"  - {subject}")
            notifier.notify(subject, body)
            seen.add(str(post.get("id")))

    news.save_seen_ids(seen)
