import os
import math
import json
import time
import logging
import base64

from dotenv import load_dotenv
load_dotenv()

LOG_FILE = os.environ.get("TRADING_APP_LOG_FILE", "trading_app.log")
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("trading_app")

LAST_SCHWAB_ERROR = "No Schwab error yet."

def set_schwab_error(message, level="error"):
    global LAST_SCHWAB_ERROR
    LAST_SCHWAB_ERROR = message
    if level == "warning":
        logger.warning("Schwab status: %s", message)
    elif level == "info":
        logger.info("Schwab status: %s", message)
    else:
        logger.error("Schwab status: %s", message)

try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    yf = None
    YFINANCE_OK = False

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

try:
    import certifi
except ImportError:
    certifi = None

DATA_SOURCE = os.environ.get("DATA_SOURCE", "yahoo")

DEFAULT_APP_KEY = "YOUR_APP_KEY_HERE"
APP_KEY = os.environ.get("SCHWAB_APP_KEY", DEFAULT_APP_KEY)
APP_SECRET = os.environ.get("SCHWAB_APP_SECRET", "")
REDIRECT_URI = os.environ.get("SCHWAB_REDIRECT_URI", "https://127.0.0.1")
TOKEN_FILE = os.environ.get("SCHWAB_TOKEN_FILE", "schwab_tokens.json")

PORTFOLIO = {
    "GOOGL": {"shares": 100, "call_strike": 315, "color": "#4285F4"},
    "AAPL":  {"shares": 100, "call_strike": 268, "color": "#A8B4BE"},
    "MSFT":  {"shares": 100, "call_strike": 383, "color": "#00A4EF"},
    "CCL":   {"shares": 100, "call_strike": 29,  "color": "#E31837"},
    "SOFI":  {"shares": 100, "call_strike": 9,   "color": "#00C896"},
}

EARNINGS_DATES = {}
MONTHLY_GOAL = 6000
ACCOUNT_SIZE = 230000

MOMENTUM_REBALANCE = os.environ.get("MOMENTUM_REBALANCE", "weekly").lower()
MOMENTUM_TARGET_RETURN = 0.40
MOMENTUM_UNIVERSE_SIZE = int(os.environ.get("MOMENTUM_UNIVERSE_SIZE", "15"))
MOMENTUM_CACHE_FILE = os.environ.get("MOMENTUM_CACHE_FILE", "spmo_momentum_cache.json")

BG          = "#0a0a12"
BG2         = "#12121e"
BG3         = "#1a1a2e"
CARD        = "#141420"
BORDER      = "#2a2a3e"
ACCENT      = "#7c6fff"
ACCENT2     = "#00c896"
CYAN        = "#4dd0e1"
GREEN       = "#00e676"
RED         = "#ff4444"
YELLOW      = "#ffd740"
TEXT        = "#e8e4ff"
TEXT2       = "#888899"
TEXT3       = "#444455"
WHITE       = "#ffffff"

SPMO_MOMENTUM_UNIVERSE = [
    "NVDA", "AVGO", "MU", "JNJ", "GOOGL",
    "GOOG", "LRCX", "XOM", "CAT", "AMD",
    "INTC", "AMAT", "RTX", "GE", "CSCO",
    "GEV", "GS", "KLAC", "SNDK", "APH",
    "NEM", "KO", "PM", "WDC", "PLTR",
]

SCAN_UNIVERSE = SPMO_MOMENTUM_UNIVERSE
ETF_SYMBOLS = {"SPY", "QQQ", "SPMO"}

MOCK_PRICES = {"GOOGL":{"price":303.12,"change":1.43,"pct":0.47},"AAPL":{"price":260.45,"change":0.87,"pct":0.34},"MSFT":{"price":371.70,"change":-1.20,"pct":-0.32},"CCL":{"price":27.85,"change":-0.18,"pct":-0.64},"SOFI":{"price":8.42,"change":-0.31,"pct":-3.55},"SPY":{"price":645.09,"change":-11.73,"pct":-1.79},"QQQ":{"price":611.07,"change":0.88,"pct":0.14}}
MOCK_RSI = {"GOOGL":54,"AAPL":49,"MSFT":47,"CCL":42,"SOFI":33,"SPY":52,"QQQ":51}
MOCK_MA50 = {"GOOGL":295.4,"AAPL":255.1,"MSFT":368.5,"CCL":26.9,"SOFI":9.8,"SPY":628.4,"QQQ":597.3}
MOCK_MA200= {"GOOGL":278.6,"AAPL":242.8,"MSFT":410.2,"CCL":24.3,"SOFI":11.4,"SPY":601.2,"QQQ":572.8}
