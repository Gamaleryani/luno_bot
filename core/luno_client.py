"""
Thin wrapper around Luno's public/authenticated API.

- /ticker is public in all modes, no keys needed.
- /candles now REQUIRES an authenticated API key on Luno's side (confirmed
  2026-08-19 - the old public candles endpoint returns 404, and the current
  one at /api/exchange/1/candles returns 401 without credentials). A
  read-only key (no trade/withdraw permission) is enough - set
  LUNO_API_KEY_ID / LUNO_API_SECRET even to just pull history for backtesting.
- Order placement is GATED: it only actually calls Luno's order endpoint
  when cfg.MODE == "live" AND both API key env vars are set. In "paper"
  mode it simulates the fill locally and never touches the real account.
"""

import time
import requests

BASE_URL = "https://api.luno.com/api/1"
EXCHANGE_BASE_URL = "https://api.luno.com/api/exchange/1"


class LunoClient:
    def __init__(self, cfg):
        self.cfg = cfg

    def get_ticker(self, pair: str) -> dict:
        r = requests.get(f"{BASE_URL}/ticker", params={"pair": pair}, timeout=10)
        r.raise_for_status()
        return r.json()

    def get_candles(self, pair: str, duration: int, since_ms: int) -> list:
        if not (self.cfg.LUNO_API_KEY_ID and self.cfg.LUNO_API_SECRET):
            raise RuntimeError(
                "get_candles requires LUNO_API_KEY_ID / LUNO_API_SECRET to be set "
                "(Luno's candles endpoint requires an authenticated key, even a "
                "read-only one with no trade/withdraw permission)."
            )
        r = requests.get(
            f"{EXCHANGE_BASE_URL}/candles",
            params={"pair": pair, "since": since_ms, "duration": duration},
            auth=(self.cfg.LUNO_API_KEY_ID, self.cfg.LUNO_API_SECRET),
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get("candles", [])

    def place_order(self, pair: str, side: str, volume: float, price: float) -> dict:
        """
        side: 'BID' (buy) or 'ASK' (sell)
        Returns a dict describing what happened - real order details in
        live mode, or a simulated fill record in paper mode.
        """
        if self.cfg.MODE != "live":
            return {
                "simulated": True,
                "side": side,
                "pair": pair,
                "volume": volume,
                "price": price,
                "timestamp": time.time(),
                "note": "paper mode - no real order placed",
            }

        if not (self.cfg.LUNO_API_KEY_ID and self.cfg.LUNO_API_SECRET):
            raise RuntimeError(
                "MODE is 'live' but LUNO_API_KEY_ID / LUNO_API_SECRET are not set. "
                "Refusing to place a real order without credentials."
            )

        resp = requests.post(
            f"{BASE_URL}/postorder",
            auth=(self.cfg.LUNO_API_KEY_ID, self.cfg.LUNO_API_SECRET),
            data={
                "pair": pair,
                "type": side,
                "volume": volume,
                "price": price,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
