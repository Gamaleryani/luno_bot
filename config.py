"""
Central config. Nothing here touches real money until MODE = "live"
and real API keys are set as environment variables:
  LUNO_API_KEY_ID
  LUNO_API_SECRET

MODE options:
  "backtest" -> run strategy over historical CSV data, no network calls
  "paper"    -> pull real live prices from Luno public API, simulate trades only
  "live"     -> pull real prices AND place real orders (requires API keys)
"""

import os

MODE = "paper"  # backtest -> paper -> live. Paper pulls real prices, simulates trades only.

PAIR = "XBTMYR"        # Bitcoin vs Malaysian Ringgit on Luno
CANDLE_DURATION = 300   # 5-minute candles (seconds) - Luno's smallest granularity

# --- Indicator settings ---
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

MA_FAST = 9
MA_SLOW = 21

BOLLINGER_PERIOD = 20
BOLLINGER_STD = 2

VOLUME_LOOKBACK = 20  # candles used to judge "high" vs "low" volume

# --- Regime detection ---
ADX_PERIOD = 14
ADX_TREND_THRESHOLD = 25  # above this = trending market, below = ranging

# --- Multi-indicator voting ---
MIN_AGREEING_SIGNALS = 3   # out of 4 indicators, minimum to trigger a trade

# --- Risk controls ---
STOP_LOSS_PCT = 0.03        # exit if position drops 3%
TAKE_PROFIT_PCT = 0.05      # exit if position gains 5%
MAX_POSITION_PCT = 0.5      # never risk more than 50% of balance on one trade
VOLATILITY_SIZE_FLOOR = 0.15  # min position size (as % of max) in high volatility
NEWS_SHOCK_PCT = 0.05       # pause trading if price moves this much in one candle

# --- Trading fees (backtest/paper realism only - live orders are charged by Luno directly) ---
# Luno's taker fee varies by pair and your account's 30-day volume tier
# (their standard/low-volume tier is commonly ~0.1%). Check your actual
# rate at luno.com/fees and update this before trusting backtest numbers.
TAKER_FEE_PCT = 0.001

# --- Notifications & approval gate ---
# A trade sized at or above this fraction of current balance is "big":
# it always gets an email notification, and in MODE="live" it additionally
# requires explicit approval (see core/approval.py, approve_trade.py)
# before it's ever executed - paper/backtest just notify, never block.
BIG_TRADE_ALERT_PCT = 0.30

# --- Starting capital (paper/backtest only) ---
STARTING_BALANCE_MYR = 50.0

# --- Credentials (only needed for MODE = "live") ---
LUNO_API_KEY_ID = os.environ.get("LUNO_API_KEY_ID", "")
LUNO_API_SECRET = os.environ.get("LUNO_API_SECRET", "")

LOG_DIR = "logs"
