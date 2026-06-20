"""
═══════════════════════════════════════════════════════════
  GEORGE'S TRADING DASHBOARD  —  Desktop App
  Built with Python + tkinter + matplotlib
═══════════════════════════════════════════════════════════

  INSTALL (run once in terminal):
  pip install requests matplotlib pandas numpy pillow yfinance

  RUN:
  python trading_app.py
"""

import tkinter as tk
from tkinter import ttk, font as tkfont, messagebox, simpledialog
import threading
import time
import math
import json
import os
import base64
import logging
import requests
import webbrowser
from datetime import datetime, date, timedelta
from collections import deque
from urllib.parse import urlparse, parse_qs, urlencode
import xml.etree.ElementTree as ET
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
    YFINANCE_OK = False

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

try:
    import certifi
except ImportError:
    certifi = None

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import matplotlib.patches as mpatches
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import matplotlib.gridspec as gridspec
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False

# ─────────────────────────────────────────
#  DATA SOURCE — SWITCH HERE WHEN READY
# ─────────────────────────────────────────
# "yahoo"  = Live data right now, no setup needed
# "schwab" = Live brokerage data (add keys when API approved)
DATA_SOURCE  = os.environ.get("DATA_SOURCE", "yahoo")

# Schwab credentials — add when your API is approved
DEFAULT_APP_KEY = "YOUR_APP_KEY_HERE"
APP_KEY      = os.environ.get("SCHWAB_APP_KEY", DEFAULT_APP_KEY)
APP_SECRET   = os.environ.get("SCHWAB_APP_SECRET", "")
REDIRECT_URI = os.environ.get("SCHWAB_REDIRECT_URI", "https://127.0.0.1")
TOKEN_FILE   = os.environ.get("SCHWAB_TOKEN_FILE", "schwab_tokens.json")

# ─────────────────────────────────────────
#  YOUR PORTFOLIO
#  earnings date is now pulled from Yahoo automatically
# ─────────────────────────────────────────
PORTFOLIO = {
    "GOOGL": {"shares": 100, "call_strike": 315, "color": "#4285F4"},
    "AAPL":  {"shares": 100, "call_strike": 268, "color": "#A8B4BE"},
    "MSFT":  {"shares": 100, "call_strike": 383, "color": "#00A4EF"},
    "CCL":   {"shares": 100, "call_strike": 29,  "color": "#E31837"},
    "SOFI":  {"shares": 100, "call_strike": 9,   "color": "#00C896"},
}

# Live earnings dates — populated automatically at startup
EARNINGS_DATES = {}

MONTHLY_GOAL = 6000
ACCOUNT_SIZE = 230000

# SPMO-inspired strategy controls. Actual SPMO rebalances semiannually; this app
# can refresh the momentum universe faster for active income scanning.
MOMENTUM_REBALANCE = os.environ.get("MOMENTUM_REBALANCE", "weekly").lower()  # daily or weekly
MOMENTUM_TARGET_RETURN = 0.40
MOMENTUM_UNIVERSE_SIZE = int(os.environ.get("MOMENTUM_UNIVERSE_SIZE", "15"))
MOMENTUM_CACHE_FILE = os.environ.get("MOMENTUM_CACHE_FILE", "spmo_momentum_cache.json")

# ─────────────────────────────────────────
#  COLORS / THEME
# ─────────────────────────────────────────
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

# ─────────────────────────────────────────
#  YAHOO FINANCE DATA
# ─────────────────────────────────────────
def create_yahoo_session():
    """Build a Yahoo-friendly session when curl_cffi is available."""
    if curl_requests is None:
        return None

    session = curl_requests.Session(impersonate="chrome")
    disable_ssl = os.environ.get("YFINANCE_DISABLE_SSL", "1").lower() in {"1", "true", "yes", "on"}
    if disable_ssl:
        session.verify = False
        return session

    ca_bundle = (
        os.environ.get("YFINANCE_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
        or (certifi.where() if certifi else None)
    )
    if ca_bundle:
        session.verify = ca_bundle
    return session

def get_requests_verify_setting():
    """Return CA bundle path for requests, or True to use system defaults."""
    if os.environ.get("SCHWAB_SSL_NO_VERIFY", "").strip().lower() in {"1", "true", "yes"}:
        set_schwab_error("WARNING: Schwab SSL verification is disabled.", level="warning")
        return False
    ca_bundle = (
        os.environ.get("SCHWAB_CA_BUNDLE")
        or os.environ.get("SSL_CERT_FILE")
        or os.environ.get("REQUESTS_CA_BUNDLE")
        or (certifi.where() if certifi else None)
    )
    return ca_bundle or True

def fetch_quotes_yahoo(symbols):
    """Fetch live quotes from Yahoo Finance — no API key needed"""
    if not YFINANCE_OK:
        return None
        return "â€”"
    try:
        result = {}
        tickers = yf.Tickers(" ".join(symbols), session=create_yahoo_session())
        for symbol in symbols:
            try:
                ticker = tickers.tickers[symbol]
                info = ticker.fast_info
                curr_price = (
                    info.get("lastPrice")
                    or info.get("regularMarketPrice")
                    or info.get("currentPrice")
                    or 0
                )
                prev_close = (
                    info.get("previousClose")
                    or info.get("regularMarketPreviousClose")
                    or 0
                )
                volume = (
                    info.get("lastVolume")
                    or info.get("regularMarketVolume")
                    or info.get("volume")
                    or 0
                )
                if not curr_price or not prev_close:
                    hist = ticker.history(period="2d", interval="1d")
                    if len(hist) >= 2:
                        prev_close = prev_close or hist["Close"].iloc[-2]
                        curr_price = curr_price or hist["Close"].iloc[-1]
                    elif len(hist) == 1:
                        curr_price = curr_price or hist["Close"].iloc[-1]
                        prev_close = prev_close or curr_price
                    else:
                        prev_close = prev_close or curr_price
                change     = curr_price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0
                result[symbol] = {
                    "price":  round(curr_price, 2),
                    "change": round(change, 2),
                    "pct":    round(change_pct, 2),
                    "volume": int(volume or 0),
                }
            except Exception:
                pass
        return result if result else None
    except Exception as e:
        print(f"Yahoo quote error: {e}")
        return None

def fetch_quotes_yahoo(symbols):
    """Fetch live quotes from Yahoo Finance â€” no API key needed"""
    if not YFINANCE_OK:
        return None
    try:
        result = {}
        tickers = yf.Tickers(" ".join(symbols), session=create_yahoo_session())
        for symbol in symbols:
            try:
                ticker = tickers.tickers[symbol]
                info = ticker.fast_info
                curr_price = (
                    info.get("lastPrice")
                    or info.get("regularMarketPrice")
                    or info.get("currentPrice")
                    or 0
                )
                prev_close = (
                    info.get("previousClose")
                    or info.get("regularMarketPreviousClose")
                    or 0
                )
                volume = (
                    info.get("lastVolume")
                    or info.get("regularMarketVolume")
                    or info.get("volume")
                    or 0
                )
                if not curr_price or not prev_close:
                    hist = ticker.history(period="2d", interval="1d")
                    if len(hist) >= 2:
                        prev_close = prev_close or hist["Close"].iloc[-2]
                        curr_price = curr_price or hist["Close"].iloc[-1]
                    elif len(hist) == 1:
                        curr_price = curr_price or hist["Close"].iloc[-1]
                        prev_close = prev_close or curr_price
                    else:
                        prev_close = prev_close or curr_price
                change = curr_price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0
                result[symbol] = {
                    "price": round(curr_price, 2),
                    "change": round(change, 2),
                    "pct": round(change_pct, 2),
                    "volume": int(volume or 0),
                }
            except Exception:
                pass
        return result if result else None
    except Exception as e:
        print(f"Yahoo quote error: {e}")
        return None

def fetch_history_yahoo(symbol):
    """Fetch 1 year price history from Yahoo Finance"""
    if not YFINANCE_OK:
        return []
    try:
        ticker = yf.Ticker(symbol, session=create_yahoo_session())
        hist   = ticker.history(period="1y", interval="1d")
        return [round(p, 2) for p in hist["Close"].tolist()]
    except Exception as e:
        print(f"Yahoo history error for {symbol}: {e}")
        return []

def fetch_history_series_yahoo(symbol, period="2y"):
    """Fetch dated price history from Yahoo Finance."""
    if not YFINANCE_OK:
        return []
    try:
        ticker = yf.Ticker(symbol, session=create_yahoo_session())
        hist = ticker.history(period=period, interval="1d")
        series = []
        for idx, row in hist.iterrows():
            dt = idx.to_pydatetime().date() if hasattr(idx, "to_pydatetime") else idx.date()
            close = row.get("Close")
            if close is not None:
                series.append({"date": dt, "close": round(float(close), 2)})
        return series
    except Exception as e:
        print(f"Yahoo history series error for {symbol}: {e}")
        return []

def fetch_earnings_timeline_yahoo(symbol, limit=12):
    """Fetch historical and upcoming earnings dates from Yahoo when available."""
    if not YFINANCE_OK or symbol in ETF_SYMBOLS:
        return {"historical": [], "upcoming": None}
    dates = []
    try:
        ticker = yf.Ticker(symbol, session=create_yahoo_session())
        try:
            df = ticker.get_earnings_dates(limit=limit)
            if df is not None and len(df):
                for idx in df.index.tolist():
                    ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
                    if hasattr(ts, "date"):
                        dates.append(ts.date())
        except Exception:
            pass

        try:
            cal = ticker.calendar
            if cal is not None and not cal.empty:
                if hasattr(cal, "index") and "Earnings Date" in cal.index:
                    cal_dates = cal.loc["Earnings Date"]
                elif hasattr(cal, "columns") and "Earnings Date" in cal.columns:
                    cal_dates = cal["Earnings Date"]
                else:
                    cal_dates = None

                if cal_dates is not None:
                    if hasattr(cal_dates, "__iter__") and not isinstance(cal_dates, str):
                        for item in cal_dates:
                            if hasattr(item, "date"):
                                dates.append(item.date())
                    elif hasattr(cal_dates, "date"):
                        dates.append(cal_dates.date())
        except Exception:
            pass
    except Exception:
        return {"historical": [], "upcoming": None}

    unique_dates = sorted({d for d in dates if d})
    today = datetime.now().date()
    historical = [d for d in unique_dates if d <= today]
    upcoming = next((d for d in unique_dates if d > today), None)
    return {"historical": historical[-8:], "upcoming": upcoming}

def parse_short_earnings_date(earn_str):
    if not earn_str or earn_str == "â€”" or earn_str == "-":
        return None
    try:
        parsed = datetime.strptime(f"{earn_str} {datetime.now().year}", "%b %d %Y").date()
        if parsed < datetime.now().date() - timedelta(days=180):
            parsed = parsed.replace(year=parsed.year + 1)
        return parsed
    except Exception:
        return None

def fetch_earnings_date(symbol):
    """
    Pull next earnings date from Yahoo Finance.
    Returns formatted string like 'Apr 29' or '—' if unavailable.
    """
    if not YFINANCE_OK:
        return "—"
    if symbol in ETF_SYMBOLS:
        return "—"
    try:
        t    = yf.Ticker(symbol, session=create_yahoo_session())
        info = t.info

        # Try earnings_date field first (most reliable)
        ed = info.get("earningsDate") or info.get("earningsTimestamp")
        if ed:
            from datetime import datetime
            if isinstance(ed, (int, float)):
                dt = datetime.fromtimestamp(ed)
            elif isinstance(ed, list) and ed:
                dt = datetime.fromtimestamp(ed[0]) if isinstance(ed[0], (int, float)) else ed[0]
            else:
                dt = ed
            if hasattr(dt, "strftime"):
                # Only show if in the future
                if dt.date() >= datetime.now().date():
                    return dt.strftime("%b %-d") if hasattr(dt, "date") else str(dt)

        # Fallback: check calendar
        cal = t.calendar
        if cal is not None and not cal.empty:
            if "Earnings Date" in cal.index:
                dates = cal.loc["Earnings Date"]
                if hasattr(dates, "__iter__"):
                    for d in dates:
                        if hasattr(d, "date") and d.date() >= datetime.now().date():
                            return d.strftime("%b %-d")
                elif hasattr(dates, "date") and dates.date() >= datetime.now().date():
                    return dates.strftime("%b %-d")

        return "—"
    except Exception:
        return "—"

def fetch_all_earnings(symbols):
    """Fetch earnings dates for all symbols and store in EARNINGS_DATES."""
    global EARNINGS_DATES
    for symbol in symbols:
        try:
            EARNINGS_DATES[symbol] = fetch_earnings_date(symbol)
        except Exception:
            EARNINGS_DATES[symbol] = "—"

def get_earnings(symbol):
    """Get earnings date for a symbol, falling back to '—'."""
    return EARNINGS_DATES.get(symbol, "—")

# ─────────────────────────────────────────
#  SCHWAB AUTH (used when DATA_SOURCE = "schwab")
# ─────────────────────────────────────────
def load_tokens():
    logger.info("load_tokens: checking %s", TOKEN_FILE)
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE) as f:
                tokens = json.load(f)
            logger.info("load_tokens: token file loaded successfully")
            set_schwab_error("Schwab token file loaded.", level="info")
            return tokens
        except Exception:
            logger.exception("load_tokens: failed to read token file")
            set_schwab_error("Failed to read Schwab token file.", level="error")
            return None
    logger.warning("load_tokens: token file not found")
    set_schwab_error("No Schwab token file found yet. Complete login in Setup.", level="warning")
    return None

def save_tokens(tokens):
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f)
        logger.info("save_tokens: token file saved to %s", TOKEN_FILE)
        set_schwab_error("Schwab tokens saved successfully.", level="info")
    except Exception:
        logger.exception("save_tokens: failed to save token file")
        set_schwab_error("Failed to save Schwab token file.", level="error")

def refresh_token(refresh_tok):
    logger.info("refresh_token: attempting refresh")
    creds = base64.b64encode(f"{APP_KEY}:{APP_SECRET}".encode()).decode()
    verify = get_requests_verify_setting()
    try:
        r = requests.post("https://api.schwabapi.com/v1/oauth/token",
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": refresh_tok},
            timeout=20, verify=verify)
    except requests.exceptions.SSLError as e:
        logger.exception("refresh_token: ssl error")
        set_schwab_error(f"Schwab SSL error during token refresh: {e}", level="error")
        return None
    except Exception:
        logger.exception("refresh_token: network error")
        set_schwab_error("Schwab token refresh failed due to network error.", level="error")
        return None
    if r.status_code == 200:
        t = r.json(); t["obtained_at"] = time.time()
        logger.info("refresh_token: refresh succeeded")
        set_schwab_error("Schwab token refreshed successfully.", level="info")
        save_tokens(t); return t
    logger.error("refresh_token: failed with status %s body=%s", r.status_code, r.text[:500])
    set_schwab_error(f"Schwab token refresh failed ({r.status_code}).", level="error")
    return None

def build_schwab_authorize_url():
    params = {
        "client_id": APP_KEY,
        "redirect_uri": REDIRECT_URI,
    }
    return f"https://api.schwabapi.com/v1/oauth/authorize?{urlencode(params)}"

def extract_schwab_auth_code(redirect_url):
    parsed = urlparse(redirect_url.strip())
    query = parse_qs(parsed.query)
    code_vals = query.get("code")
    if code_vals and code_vals[0]:
        return code_vals[0]
    return None

def exchange_auth_code_for_tokens(auth_code):
    logger.info("exchange_auth_code_for_tokens: exchanging auth code")
    creds = base64.b64encode(f"{APP_KEY}:{APP_SECRET}".encode()).decode()
    verify = get_requests_verify_setting()
    try:
        r = requests.post(
            "https://api.schwabapi.com/v1/oauth/token",
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=20, verify=verify,
        )
    except requests.exceptions.SSLError as e:
        logger.exception("exchange_auth_code_for_tokens: ssl error")
        set_schwab_error(f"Schwab SSL error during token exchange: {e}", level="error")
        return False, f"SSL certificate error talking to Schwab: {e}"
    except Exception:
        logger.exception("exchange_auth_code_for_tokens: network error")
        set_schwab_error("Schwab token exchange failed due to network error.", level="error")
        return False, "Token exchange failed due to network error. See trading_app.log."
    if r.status_code == 200:
        tokens = r.json()
        tokens["obtained_at"] = time.time()
        save_tokens(tokens)
        logger.info("exchange_auth_code_for_tokens: success")
        set_schwab_error("Schwab login completed and tokens saved.", level="info")
        return True, "Schwab tokens saved successfully."
    try:
        detail = r.json()
    except Exception:
        detail = r.text
    logger.error("exchange_auth_code_for_tokens: failed with status %s detail=%s", r.status_code, str(detail)[:500])
    set_schwab_error(f"Schwab token exchange failed ({r.status_code}).", level="error")
    return False, f"Token exchange failed ({r.status_code}): {detail}"

def get_token():
    tokens = load_tokens()
    if not tokens:
        logger.warning("get_token: no tokens available")
        set_schwab_error("No Schwab access token available.", level="warning")
        return None
    elapsed = time.time() - tokens.get("obtained_at", 0)
    if elapsed > tokens.get("expires_in", 1800) - 120:
        logger.info("get_token: token expired or near expiry, refreshing")
        tokens = refresh_token(tokens["refresh_token"])
    if not tokens:
        logger.error("get_token: refresh failed, no access token available")
        set_schwab_error("Schwab token refresh failed. Reconnect in Setup.", level="error")
        return None
    logger.info("get_token: access token ready")
    set_schwab_error("Schwab access token is ready.", level="info")
    return tokens["access_token"]

def fetch_quotes_schwab(symbols):
    logger.info("fetch_quotes_schwab: requesting quotes for %s", ",".join(symbols))
    token = get_token()
    if not token:
        logger.warning("fetch_quotes_schwab: no token, aborting")
        set_schwab_error("Cannot fetch Schwab quotes: no token.", level="warning")
        return None
    verify = get_requests_verify_setting()
    try:
        r = requests.get("https://api.schwabapi.com/marketdata/v1/quotes",
            headers={"Authorization": f"Bearer {token}"},
            params={"symbols": ",".join(symbols), "fields": "quote"}, timeout=10, verify=verify)
    except requests.exceptions.SSLError as e:
        logger.exception("fetch_quotes_schwab: ssl error")
        set_schwab_error(f"Schwab SSL error during quotes request: {e}", level="error")
        return None
    except Exception:
        logger.exception("fetch_quotes_schwab: network error")
        set_schwab_error("Schwab quote request failed due to network error.", level="error")
        return None
    if r.status_code != 200:
        logger.error("fetch_quotes_schwab: failed with status %s body=%s", r.status_code, r.text[:500])
        set_schwab_error(f"Schwab quotes failed ({r.status_code}).", level="error")
        return None
    logger.info("fetch_quotes_schwab: success")
    set_schwab_error("Schwab quotes loaded successfully.", level="info")
    raw = r.json()
    result = {}
    for s in symbols:
        if s in raw:
            q = raw[s].get("quote", {})
            result[s] = {
                "price":  q.get("lastPrice", 0),
                "change": q.get("netChange", 0),
                "pct":    q.get("netPercentChangeInDouble", 0),
                "volume": q.get("totalVolume", 0) or q.get("regularMarketVolume", 0) or 0,
            }
    return result

def fetch_history_schwab(symbol):
    logger.info("fetch_history_schwab: requesting history for %s", symbol)
    token = get_token()
    if not token:
        logger.warning("fetch_history_schwab: no token, aborting")
        set_schwab_error("Cannot fetch Schwab history: no token.", level="warning")
        return []
    verify = get_requests_verify_setting()
    try:
        r = requests.get("https://api.schwabapi.com/marketdata/v1/pricehistory",
            headers={"Authorization": f"Bearer {token}"},
            params={"symbol": symbol, "periodType": "year", "period": 1,
                    "frequencyType": "daily", "frequency": 1}, timeout=10, verify=verify)
    except requests.exceptions.SSLError as e:
        logger.exception("fetch_history_schwab: ssl error")
        set_schwab_error(f"Schwab SSL error during history request: {e}", level="error")
        return []
    except Exception:
        logger.exception("fetch_history_schwab: network error")
        set_schwab_error("Schwab history request failed due to network error.", level="error")
        return []
    if r.status_code == 200:
        logger.info("fetch_history_schwab: success for %s", symbol)
        set_schwab_error(f"Schwab history loaded for {symbol}.", level="info")
        return [c["close"] for c in r.json().get("candles", [])]
    logger.error("fetch_history_schwab: failed with status %s body=%s", r.status_code, r.text[:500])
    set_schwab_error(f"Schwab history failed for {symbol} ({r.status_code}).", level="error")
    return []

def fetch_history_series_schwab(symbol):
    logger.info("fetch_history_series_schwab: requesting history for %s", symbol)
    token = get_token()
    if not token:
        return []
    verify = get_requests_verify_setting()
    try:
        r = requests.get("https://api.schwabapi.com/marketdata/v1/pricehistory",
            headers={"Authorization": f"Bearer {token}"},
            params={"symbol": symbol, "periodType": "year", "period": 1,
                    "frequencyType": "daily", "frequency": 1}, timeout=10, verify=verify)
        if r.status_code != 200:
            return []
        series = []
        for candle in r.json().get("candles", []):
            stamp = candle.get("datetime")
            close = candle.get("close")
            if stamp is None or close is None:
                continue
            dt = datetime.fromtimestamp(stamp / 1000).date()
            series.append({"date": dt, "close": round(float(close), 2)})
        return series
    except Exception:
        return []

# ─────────────────────────────────────────
#  UNIFIED DATA FETCHER — auto picks source
# ─────────────────────────────────────────
def fetch_quotes(symbols):
    if DATA_SOURCE == "schwab":
        return fetch_quotes_schwab(symbols)
    return fetch_quotes_yahoo(symbols)

def fetch_history(symbol):
    if DATA_SOURCE == "schwab":
        return fetch_history_schwab(symbol)
    return fetch_history_yahoo(symbol)

def fetch_history_series(symbol, period="2y"):
    if DATA_SOURCE == "schwab":
        series = fetch_history_series_schwab(symbol)
        if series:
            return series
    return fetch_history_series_yahoo(symbol, period=period)

def is_demo_mode():
    """Only true if Yahoo fails AND no Schwab key"""
    if DATA_SOURCE == "yahoo":
        return not YFINANCE_OK
    return APP_KEY == DEFAULT_APP_KEY

# ─────────────────────────────────────────
#  INDICATORS
# ─────────────────────────────────────────
def calc_rsi(prices, n=14):
    if len(prices) < n + 1: return 50
    g, l = [], []
    for i in range(1, len(prices)):
        d = prices[i] - prices[i-1]
        g.append(max(d, 0)); l.append(max(-d, 0))
    ag = sum(g[-n:]) / n; al = sum(l[-n:]) / n
    if al == 0: return 100
    return round(100 - 100 / (1 + ag / al), 1)

def calc_ma(prices, n):
    if len(prices) < n: return None
    return round(sum(prices[-n:]) / n, 2)

def find_local_extrema(prices, order=3):
    highs, lows = [], []
    if len(prices) < order * 2 + 1:
        return highs, lows
    for i in range(order, len(prices) - order):
        window = prices[i - order:i + order + 1]
        center = prices[i]
        if center == max(window):
            highs.append((i, center))
        if center == min(window):
            lows.append((i, center))
    return highs, lows

def detect_patterns(closes):
    if len(closes) < 60:
        return []

    patterns = []
    highs, lows = find_local_extrema(closes, order=3)
    price = closes[-1]
    ma50 = calc_ma(closes, 50)
    ma200 = calc_ma(closes, min(200, len(closes)))

    if len(highs) >= 3:
        h1, h2, h3 = highs[-3], highs[-2], highs[-1]
        shoulder_tol = 0.06
        if h2[1] > h1[1] * 1.03 and h2[1] > h3[1] * 1.03 and abs(h1[1] - h3[1]) / max(h1[1], 1) <= shoulder_tol:
            neckline = min(closes[h1[0]:h3[0] + 1]) if h3[0] > h1[0] else min(closes[-20:])
            confidence = 70 if price < neckline else 55
            patterns.append({
                "name": "Head & Shoulders",
                "bias": "Bearish",
                "confidence": confidence,
                "level": neckline,
                "prediction": "Price drops after neckline break",
            })

    if len(lows) >= 2:
        l1, l2 = lows[-2], lows[-1]
        if abs(l1[1] - l2[1]) / max(l1[1], 1) <= 0.04 and price > max(l1[1], l2[1]) * 1.05:
            breakout = max(closes[l1[0]:l2[0] + 1]) if l2[0] > l1[0] else price
            patterns.append({
                "name": "Double Bottom",
                "bias": "Bullish",
                "confidence": 68 if price > breakout else 58,
                "level": breakout,
                "prediction": "Price bounces up after confirmation",
            })

    if len(closes) >= 25:
        rise = (closes[-10] - closes[-25]) / max(closes[-25], 1)
        drift = (closes[-1] - closes[-10]) / max(closes[-10], 1)
        pullback = min(closes[-10:]) / max(max(closes[-15:-10]), 1)
        if rise > 0.08 and -0.06 <= drift <= 0.03 and pullback > 0.94:
            breakout = max(closes[-10:])
            patterns.append({
                "name": "Bull Flag",
                "bias": "Bullish",
                "confidence": 64 if price >= breakout * 0.99 else 56,
                "level": breakout,
                "prediction": "Continues up after tight consolidation",
            })

    if ma50 and ma200 and len(closes) >= 201:
        prev_ma50 = calc_ma(closes[:-1], 50)
        prev_ma200 = calc_ma(closes[:-1], 200)
        if prev_ma50 and prev_ma200 and prev_ma50 >= prev_ma200 and ma50 < ma200:
            patterns.append({
                "name": "Death Cross",
                "bias": "Bearish",
                "confidence": 72,
                "level": ma200,
                "prediction": "Downtrend ahead after 50/200 cross",
            })

    if len(closes) >= 50:
        left = closes[-50:-25]
        base = closes[-25:-8]
        handle = closes[-8:]
        if left and base and handle:
            left_high = max(left)
            base_low = min(base)
            handle_low = min(handle)
            recovered = closes[-1] >= left_high * 0.97
            rounded = base_low < left_high * 0.92 and handle_low > base_low * 1.03
            if recovered and rounded:
                patterns.append({
                    "name": "Cup & Handle",
                    "bias": "Bullish",
                    "confidence": 69 if price >= max(handle) else 60,
                    "level": max(handle),
                    "prediction": "Breakout up if handle high clears",
                })

    if not patterns:
        trend_bias = "Bullish" if ma50 and ma200 and price > ma50 and price > ma200 else "Bearish" if ma50 and ma200 and price < ma50 and price < ma200 else "Neutral"
        patterns.append({
            "name": "No Clear Pattern",
            "bias": trend_bias,
            "confidence": 40,
            "level": price,
            "prediction": "Watch trend and consolidation",
        })

    return sorted(patterns, key=lambda x: x["confidence"], reverse=True)

def detect_statistical_signals(closes, highs, lows):
    if len(closes) < 20:
        return []

    signals = []
    price = closes[-1]
    ma5 = calc_ma(closes, 5)
    ma20 = calc_ma(closes, 20)
    ma50 = calc_ma(closes, 50)
    rsi = calc_rsi(closes)
    atr = calc_atr(highs, lows, closes) if len(closes) >= 15 else None

    if ma5 and ma20:
        slope = (ma5 - ma20) / max(ma20, 1)
        forecast = price * (1 + slope)
        bias = "Bullish" if slope > 0 else "Bearish" if slope < 0 else "Neutral"
        conf = min(75, max(45, int(abs(slope) * 1000) + 50))
        signals.append({
            "name": "Moving Average Forecast",
            "bias": bias,
            "confidence": conf,
            "level": forecast,
            "prediction": f"Trend projection points to about ${forecast:.2f} next",
        })

    if ma20:
        if rsi >= 80:
            signals.append({
                "name": "Mean Reversion",
                "bias": "Bearish",
                "confidence": 72,
                "level": ma20,
                "prediction": f"RSI {rsi:.0f} is stretched; likely drift back toward average",
            })
        elif rsi <= 20:
            signals.append({
                "name": "Mean Reversion",
                "bias": "Bullish",
                "confidence": 72,
                "level": ma20,
                "prediction": f"RSI {rsi:.0f} is washed out; likely bounce toward average",
            })

    if atr:
        low_range = max(price - atr, 0)
        high_range = price + atr
        signals.append({
            "name": "ATR Range",
            "bias": "Neutral",
            "confidence": 65,
            "level": price,
            "prediction": f"Expected near-term range ${low_range:.2f} to ${high_range:.2f}",
        })

    if not signals:
        anchor = ma50 or ma20 or price
        signals.append({
            "name": "Moving Average Forecast",
            "bias": "Neutral",
            "confidence": 40,
            "level": anchor,
            "prediction": "Not enough edge yet; watch trend and volatility",
        })

    return signals

def detect_ml_forecast_signal(closes, highs, lows):
    """
    Lightweight ML-style directional forecast using engineered features instead of
    a true LSTM. Fast enough for the desktop app and still useful for ranking.
    """
    if len(closes) < 60:
        return []

    price = closes[-1]
    rsi = calc_rsi(closes)
    ma20 = calc_ma(closes, 20) or price
    ma50 = calc_ma(closes, 50) or price
    atr = calc_atr(highs, lows, closes) if len(closes) >= 15 else max(price * 0.02, 1)
    mom5 = ((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) >= 6 and closes[-6] else 0
    mom20 = ((closes[-1] - closes[-21]) / closes[-21] * 100) if len(closes) >= 21 and closes[-21] else 0
    trend20 = (price - ma20) / max(ma20, 1)
    trend50 = (price - ma50) / max(ma50, 1)
    vol_norm = atr / max(price, 1)

    # Simple weighted feature model that mimics a directional classifier.
    score = (
        mom5 * 0.35 +
        mom20 * 0.25 +
        trend20 * 100 * 0.20 +
        trend50 * 100 * 0.15 +
        ((50 - abs(rsi - 50)) / 50) * 4 -
        vol_norm * 100 * 0.12
    )

    if score > 1.5:
        bias = "Bullish"
        confidence = min(78, max(52, int(55 + score * 2.2)))
        target = price + atr * (1.2 + min(score / 10, 0.8))
        prediction = f"ML-style model leans up toward about ${target:.2f}"
    elif score < -1.5:
        bias = "Bearish"
        confidence = min(78, max(52, int(55 + abs(score) * 2.2)))
        target = max(price - atr * (1.2 + min(abs(score) / 10, 0.8)), 0)
        prediction = f"ML-style model leans down toward about ${target:.2f}"
    else:
        bias = "Neutral"
        confidence = 48
        target = price
        prediction = f"ML-style model sees range-bound trade near ${price:.2f}"

    return [{
        "name": "ML Forecast",
        "bias": bias,
        "confidence": confidence,
        "level": target,
        "prediction": prediction,
    }]

def detect_options_flow_signal(ticker):
    """
    Proxy for unusual options activity using near-dated option-chain volume/open interest.
    This is not true tape/flow data, but it can still flag unusual call or put activity.
    """
    if not YFINANCE_OK:
        return []
    try:
        t = yf.Ticker(ticker, session=create_yahoo_session())
        expiries = list(t.options or [])
        if not expiries:
            return []
        expiry = expiries[0]
        chain = t.option_chain(expiry)
        calls = chain.calls
        puts = chain.puts
        if calls is None or puts is None or calls.empty or puts.empty:
            return []

        call_vol = float(calls["volume"].fillna(0).sum())
        put_vol = float(puts["volume"].fillna(0).sum())
        call_oi = float(calls["openInterest"].fillna(0).sum())
        put_oi = float(puts["openInterest"].fillna(0).sum())

        if call_vol <= 0 and put_vol <= 0:
            return []

        call_to_put = call_vol / max(put_vol, 1.0)
        call_surge = call_vol / max(call_oi, 1.0)
        put_surge = put_vol / max(put_oi, 1.0)

        signals = []
        if call_to_put >= 1.8 and call_surge >= 0.12:
            conf = min(82, int(55 + call_to_put * 8 + call_surge * 40))
            signals.append({
                "name": "Unusual Options Activity",
                "bias": "Bullish",
                "confidence": conf,
                "level": call_to_put,
                "prediction": f"Unusual call activity: call/put vol {call_to_put:.1f}x into {expiry}",
            })
        elif put_vol > 0 and (put_vol / max(call_vol, 1.0)) >= 1.8 and put_surge >= 0.12:
            put_to_call = put_vol / max(call_vol, 1.0)
            conf = min(82, int(55 + put_to_call * 8 + put_surge * 40))
            signals.append({
                "name": "Unusual Options Activity",
                "bias": "Bearish",
                "confidence": conf,
                "level": put_to_call,
                "prediction": f"Heavy put activity: put/call vol {put_to_call:.1f}x into {expiry}",
            })
        return signals
    except Exception:
        return []

def detect_news_sentiment_signal(ticker):
    """
    Estimate sentiment from recent headlines. This is a lightweight headline
    sentiment model, not a full NLP/news analytics feed.
    """
    positive_words = {
        "beat", "beats", "upgrade", "upgrades", "bullish", "buy", "strong",
        "surge", "growth", "record", "profit", "profits", "winner", "wins",
        "breakout", "raises", "raised", "expands", "partnership", "outperform"
    }
    negative_words = {
        "miss", "misses", "downgrade", "downgrades", "bearish", "sell", "weak",
        "drop", "falls", "fall", "lawsuit", "probe", "cuts", "cut", "warning",
        "slowdown", "decline", "loss", "losses", "underperform", "risk"
    }

    headlines = []
    if YFINANCE_OK:
        try:
            news_items = yf.Ticker(ticker, session=create_yahoo_session()).news or []
            for item in news_items[:8]:
                title = item.get("title") or item.get("content", {}).get("title")
                if title:
                    headlines.append(str(title))
        except Exception:
            pass

    if len(headlines) < 3:
        try:
            query = urlencode({"q": f"{ticker} stock", "hl": "en-US", "gl": "US", "ceid": "US:en"})
            resp = requests.get(
                f"https://news.google.com/rss/search?{query}",
                timeout=10,
                verify=get_requests_verify_setting(),
            )
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item/title")[:8]:
                    if item.text:
                        headlines.append(item.text)
        except Exception:
            pass

    if not headlines:
        return []

    score = 0
    matches = 0
    for headline in headlines[:8]:
        text = headline.lower()
        pos = sum(1 for word in positive_words if word in text)
        neg = sum(1 for word in negative_words if word in text)
        if pos or neg:
            matches += 1
        score += pos - neg

    if score > 0:
        bias = "Bullish"
        confidence = min(80, 52 + min(score * 6, 20) + min(matches * 2, 8))
        prediction = f"Recent headlines lean positive across {len(headlines[:8])} items"
    elif score < 0:
        bias = "Bearish"
        confidence = min(80, 52 + min(abs(score) * 6, 20) + min(matches * 2, 8))
        prediction = f"Recent headlines lean negative across {len(headlines[:8])} items"
    else:
        bias = "Neutral"
        confidence = 48
        prediction = f"Recent headlines look mixed across {len(headlines[:8])} items"

    return [{
        "name": "News Sentiment",
        "bias": bias,
        "confidence": confidence,
        "level": float(len(headlines[:8])),
        "prediction": prediction,
    }]

def score_ticker_signal_set(rows):
    technical_rows = []
    sentiment_rows = []
    for row in rows:
        name = row.get("name", "")
        if name in {"Unusual Options Activity", "News Sentiment"}:
            sentiment_rows.append(row)
        else:
            technical_rows.append(row)

    def avg_score(items):
        if not items:
            return 5.0
        total = 0.0
        for item in items:
            conf = item.get("confidence", 50)
            bias = item.get("bias", "Neutral")
            base = conf / 10.0
            if bias == "Bullish":
                total += max(5.0, base)
            elif bias == "Bearish":
                total += min(5.0, 10 - base)
            else:
                total += 5.0
        return max(1.0, min(10.0, total / len(items)))

    tech = round(avg_score(technical_rows), 1)
    sent = round(avg_score(sentiment_rows), 1)
    combined = round((tech * 0.7) + (sent * 0.3), 1)

    if combined >= 7.5:
        signal = "STRONG BUY"
        color = GREEN
        icon = "FIRE"
    elif combined >= 6.2:
        signal = "BUY"
        color = GREEN
        icon = "UP"
    elif combined <= 3.5:
        signal = "STRONG SELL"
        color = RED
        icon = "DOWN"
    elif combined <= 4.5:
        signal = "SELL"
        color = RED
        icon = "DOWN"
    else:
        signal = "HOLD"
        color = YELLOW
        icon = "WAIT"

    return {
        "technical": tech,
        "sentiment": sent,
        "combined": combined,
        "signal": signal,
        "color": color,
        "icon": icon,
    }

def get_signal(price, rsi, ma50, ma200):
    a50 = price > ma50   if ma50  else False
    a200 = price > ma200 if ma200 else False
    if rsi < 32:                      return "STRONG BUY",  GREEN,  "🟢"
    if rsi < 43 and a50:              return "BUY",          GREEN,  "🟢"
    if rsi > 74:                      return "STRONG SELL",  RED,    "🔴"
    if rsi > 64 and not a50:          return "SELL",         RED,    "🔴"
    if a50 and a200 and rsi > 50:     return "BULLISH",      ACCENT2,"🔵"
    if not a50 and not a200:          return "BEARISH",      YELLOW, "🟡"
    return "HOLD", TEXT2, "⚪"

def est_premium(price, strike, dte=14, iv=0.28):
    mono = (strike - price) / price
    tf = dte / 365
    disc = max(0, 1 - mono * 8)
    return round(max(price * iv * math.sqrt(tf) * 0.4 * disc, 0.05), 2)

# ─────────────────────────────────────────
#  SPREAD SCANNER UNIVERSE
# ─────────────────────────────────────────
# SPMO tracks high-momentum S&P 500 names. This universe mirrors that idea by
# scanning current/recent SPMO-style holdings instead of a broad static watchlist.
SPMO_MOMENTUM_UNIVERSE = [
    "NVDA", "AVGO", "MU", "JNJ", "GOOGL",
    "GOOG", "LRCX", "XOM", "CAT", "AMD",
    "INTC", "AMAT", "RTX", "GE", "CSCO",
    "GEV", "GS", "KLAC", "SNDK", "APH",
    "NEM", "KO", "PM", "WDC", "PLTR",
]

SCAN_UNIVERSE = SPMO_MOMENTUM_UNIVERSE
ETF_SYMBOLS = {"SPY", "QQQ", "SPMO"}

AI_THEMES = {
    "Power & Grid": {
        "color": "#ffd740",
        "tickers": ["CEG", "VST", "ETN", "NRG", "EQIX"],
        "note": "Data center energy & infrastructure demand",
    },
    "Chips & Hardware": {
        "color": "#7c6fff",
        "tickers": ["MRVL", "ARM", "TSM", "ASML", "QCOM"],
        "note": "Next-gen silicon & AI accelerators",
    },
    "AI Software": {
        "color": "#00c896",
        "tickers": ["PLTR", "SNOW", "NET", "DDOG", "MDB"],
        "note": "AI-native enterprise software",
    },
    "Robotics": {
        "color": "#4dd0e1",
        "tickers": ["ISRG", "TER", "ROK", "ABB", "HON"],
        "note": "Physical AI, automation & industrial robots",
    },
}

AI_THEME_TICKERS = [t for s in AI_THEMES.values() for t in s["tickers"]]

def _rebalance_period_key(today=None):
    """Return a cache key for daily or weekly momentum refreshes."""
    today = today or date.today()
    if MOMENTUM_REBALANCE == "daily":
        return today.isoformat()
    iso_year, iso_week, _ = today.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"

def _load_momentum_cache():
    try:
        if os.path.exists(MOMENTUM_CACHE_FILE):
            with open(MOMENTUM_CACHE_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def _save_momentum_cache(cache):
    try:
        with open(MOMENTUM_CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass

def momentum_score_from_closes(closes):
    """
    SPMO-style momentum: 12-month price return excluding the most recent month,
    adjusted by volatility. Higher return with lower volatility ranks better.
    """
    if len(closes) < 230:
        return None
    lookback_end = -21
    lookback_start = max(0, len(closes) - 252 - 21)
    start_price = closes[lookback_start]
    end_price = closes[lookback_end]
    if start_price <= 0 or end_price <= 0:
        return None
    returns = []
    window = closes[lookback_start:lookback_end + 1]
    for i in range(1, len(window)):
        if window[i - 1] > 0:
            returns.append((window[i] - window[i - 1]) / window[i - 1])
    if not returns:
        return None
    avg = sum(returns) / len(returns)
    variance = sum((r - avg) ** 2 for r in returns) / len(returns)
    annual_vol = math.sqrt(variance) * math.sqrt(252)
    price_return = (end_price - start_price) / start_price
    if annual_vol <= 0:
        return None
    return price_return / annual_vol

def get_rebalanced_scan_universe():
    """
    Build a daily/weekly SPMO-inspired universe for the spread scanner.
    Falls back to the seeded SPMO-style holdings if live history is unavailable.
    """
    cache_key = _rebalance_period_key()
    cache = _load_momentum_cache()
    cached = cache.get(cache_key, {}).get("symbols")
    if cached:
        return cached
    if not YFINANCE_OK:
        return SCAN_UNIVERSE[:MOMENTUM_UNIVERSE_SIZE]

    ranked = []
    for ticker in SCAN_UNIVERSE:
        data = fetch_scan_data(ticker, period="15mo")
        if not data:
            continue
        score = momentum_score_from_closes(data["closes"])
        if score is not None:
            ranked.append((score, ticker))
        time.sleep(0.15)

    ranked.sort(reverse=True)
    symbols = [ticker for _, ticker in ranked[:MOMENTUM_UNIVERSE_SIZE]]
    if not symbols:
        symbols = SCAN_UNIVERSE[:MOMENTUM_UNIVERSE_SIZE]

    cache[cache_key] = {
        "rebalance": MOMENTUM_REBALANCE,
        "target_return": MOMENTUM_TARGET_RETURN,
        "symbols": symbols,
        "updated": datetime.now().isoformat(timespec="seconds"),
    }
    _save_momentum_cache(cache)
    return symbols

def calc_atr(highs, lows, closes, n=14):
    if len(closes) < n + 1: return 0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return round(sum(trs[-n:]) / n, 2)

def estimate_iv(price, atr):
    if price <= 0 or atr <= 0: return 0.25
    return round(min(max((atr / price) * math.sqrt(252), 0.10), 2.0), 3)

def bs_call(S, K, T, v):
    from statistics import NormalDist
    if T <= 0 or v <= 0: return max(S-K, 0)
    d1 = (math.log(S/K) + 0.5*v*v*T) / (v*math.sqrt(T))
    d2 = d1 - v*math.sqrt(T)
    nd = NormalDist()
    return S*nd.cdf(d1) - K*nd.cdf(d2)

def bs_put(S, K, T, v):
    from statistics import NormalDist
    if T <= 0 or v <= 0: return max(K-S, 0)
    d1 = (math.log(S/K) + 0.5*v*v*T) / (v*math.sqrt(T))
    d2 = d1 - v*math.sqrt(T)
    nd = NormalDist()
    return K*nd.cdf(-d2) - S*nd.cdf(-d1)

def next_friday(start_date=None):
    start_date = start_date or date.today()
    days_ahead = (4 - start_date.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return start_date + timedelta(days=days_ahead)

def next_covered_call_expiry(start_date=None):
    return next_friday(start_date)

def covered_call_dte(start_date=None):
    start_date = start_date or date.today()
    return max((next_covered_call_expiry(start_date) - start_date).days, 1)

def covered_call_expiry_label(start_date=None):
    return next_covered_call_expiry(start_date).strftime("%b %d")

def next_dte_expiry(days=14, start_date=None):
    start_date = start_date or date.today()
    return start_date + timedelta(days=days)

def parse_expiry_date(expiry_text):
    return datetime.strptime(expiry_text.strip(), "%Y-%m-%d").date()

def strike_step_for_price(price):
    if price < 25:
        return 1
    if price < 200:
        return 2.5
    return 5

def round_to_strike(price, step):
    return round(round(price / step) * step, 2)

def norm_cdf(x):
    from statistics import NormalDist
    return NormalDist().cdf(x)

def probability_below_strike(price, strike, time_to_expiry, iv):
    if price <= 0 or strike <= 0:
        return 0.5
    if time_to_expiry <= 0 or iv <= 0:
        return 1.0 if price < strike else 0.0
    d2 = (math.log(price / strike) - 0.5 * iv * iv * time_to_expiry) / (iv * math.sqrt(time_to_expiry))
    return max(0.0, min(1.0, norm_cdf(-d2)))

def probability_above_strike(price, strike, time_to_expiry, iv):
    return 1.0 - probability_below_strike(price, strike, time_to_expiry, iv)

def score_for_spreads(ticker, closes, highs, lows, price, change_pct, expiry_date):
    """Score a stock for spread quality. Returns dict of metrics."""
    if len(closes) < 22 or price <= 0:
        return None
    dte = max((expiry_date - date.today()).days, 1)
    time_to_expiry = dte / 365
    rsi   = calc_rsi(closes)
    ma20  = calc_ma(closes, 20)
    ma50  = calc_ma(closes, 50)
    ma200 = calc_ma(closes, min(200, len(closes)))
    atr   = calc_atr(highs, lows, closes)
    iv    = estimate_iv(price, atr)
    mom5  = ((closes[-1]-closes[-6])/closes[-6]*100) if len(closes)>=6 else 0

    above_20  = price > (ma20  or price)
    above_50  = price > (ma50  or price)
    above_200 = price > (ma200 or price)

    # ── Bull call spread ──
    bull = 50
    if rsi < 40:        bull += 15
    elif rsi < 50:      bull += 8
    if above_20:        bull += 10
    if above_50:        bull += 10
    if above_200:       bull += 8
    if mom5 > 2:        bull += 10
    if change_pct > 0:  bull += 5
    if iv > 0.30:       bull += 7   # richer premium
    if rsi > 68:        bull -= 20
    if not above_50:    bull -= 10
    if mom5 < -3:       bull -= 15

    # ── Bear put spread ──
    bear = 50
    if rsi > 65:        bear += 15
    elif rsi > 55:      bear += 8
    if not above_20:    bear += 10
    if not above_50:    bear += 10
    if not above_200:   bear += 8
    if mom5 < -2:       bear += 10
    if change_pct < 0:  bear += 5
    if iv > 0.30:       bear += 7
    if rsi < 35:        bear -= 20
    if above_50:        bear -= 10
    if mom5 > 3:        bear -= 15

    # Bull put spread favors the same bullish trend, but benefits more from rich IV.
    bull_put = bull
    if iv > 0.35:       bull_put += 10
    elif iv > 0.25:     bull_put += 5
    if 45 <= rsi <= 65: bull_put += 5
    if rsi < 35:        bull_put -= 8
    if mom5 > 5:        bull_put -= 5  # avoid chasing extended names for short premium

    bull = max(0, min(100, bull))
    bull_put = max(0, min(100, bull_put))
    bear = max(0, min(100, bear))

    # ── Covered Call ──
    cc = 50
    if above_50:          cc += 12
    if above_200:         cc += 8
    if 40 <= rsi <= 65:   cc += 10
    elif rsi > 65:        cc -= 12   # overbought = high assignment risk
    if iv > 0.30:         cc += 15   # rich premium
    elif iv > 0.22:       cc += 8
    if 0 < mom5 < 6:      cc += 8    # mild upward, not runaway
    if mom5 > 8:          cc -= 10   # capping a rocket costs too much
    if change_pct > 0:    cc += 4
    cc = max(0, min(100, cc))

    # ── Long Put ──
    lp = 50
    if rsi > 65:          lp += 15
    elif rsi > 55:        lp += 8
    if not above_20:      lp += 10
    if not above_50:      lp += 10
    if not above_200:     lp += 8
    if mom5 < -2:         lp += 10
    if change_pct < 0:    lp += 5
    if iv < 0.30:         lp += 8    # cheaper puts when IV is low
    if rsi < 35:          lp -= 20
    if above_50:          lp -= 10
    lp = max(0, min(100, lp))

    # Spread suggestions (ATR-based width)
    width = max(round(atr * 1.5 / 5) * 5, 5)
    strike_step = strike_step_for_price(price)

    # Bull call spread strikes
    bull_buy  = round_to_strike(price * 1.01, strike_step)   # slightly OTM
    bull_sell = bull_buy + width
    bull_debit = round(max(bs_call(price, bull_buy, time_to_expiry, iv) -
                           bs_call(price, bull_sell, time_to_expiry, iv), 0.05), 2)
    bull_max_profit = round(width - bull_debit, 2)
    bull_rr = round(bull_max_profit / bull_debit, 1) if bull_debit > 0 else 0
    bull_break_even = round(bull_buy + bull_debit, 2)
    bull_wrong_way = probability_below_strike(price, bull_break_even, time_to_expiry, iv)

    # Bull put spread strikes
    bull_put_short = round_to_strike(price * 0.99, strike_step)   # slightly OTM short put
    bull_put_long  = bull_put_short - width
    bull_put_credit = round(max(
        bs_put(price, bull_put_short, time_to_expiry, iv) -
        bs_put(price, bull_put_long, time_to_expiry, iv), 0.05
    ), 2)
    bull_put_max_loss = round(width - bull_put_credit, 2)
    bull_put_rr = round(
        bull_put_credit / bull_put_max_loss, 1
    ) if bull_put_max_loss > 0 else 0
    bull_put_wrong_way = probability_below_strike(price, bull_put_short, time_to_expiry, iv)

    # Bear put spread strikes
    bear_buy  = round_to_strike(price * 0.99, strike_step)   # slightly OTM
    bear_sell = bear_buy - width
    bear_debit = round(max(bs_put(price, bear_buy, time_to_expiry, iv) -
                           bs_put(price, bear_sell, time_to_expiry, iv), 0.05), 2)
    bear_max_profit = round(width - bear_debit, 2)
    bear_rr = round(bear_max_profit / bear_debit, 1) if bear_debit > 0 else 0
    bear_break_even = round(bear_buy - bear_debit, 2)
    bear_wrong_way = probability_above_strike(price, bear_break_even, time_to_expiry, iv)

    # Covered Call strikes
    cc_strike  = round_to_strike(price * 1.05, strike_step)   # ~5% OTM call
    cc_premium = round(max(bs_call(price, cc_strike, time_to_expiry, iv), 0.05), 2)
    cc_yield_pct  = round(cc_premium / price * 100, 2)
    cc_annualized = round(cc_yield_pct * (365 / dte), 1)       # annualised %
    cc_break_even = round(price - cc_premium, 2)               # downside to break-even
    cc_wrong_way  = probability_below_strike(price, cc_break_even, time_to_expiry, iv)

    # Long Put strikes
    lp_strike = round_to_strike(price * 0.97, strike_step)    # ~3% OTM put
    lp_debit  = round(max(bs_put(price, lp_strike, time_to_expiry, iv), 0.05), 2)
    lp_break_even = round(lp_strike - lp_debit, 2)
    lp_rr = round(lp_break_even / lp_debit, 1) if lp_debit > 0 else 0
    lp_wrong_way  = probability_above_strike(price, lp_strike, time_to_expiry, iv)

    return {
        "ticker": ticker, "price": price, "rsi": rsi,
        "ma50": ma50, "ma200": ma200, "iv": iv, "atr": atr,
        "mom5": mom5, "above_50": above_50, "above_200": above_200,
        "bull_score": bull, "bull_put_score": bull_put, "bear_score": bear,
        "bull_buy": bull_buy, "bull_sell": bull_sell,
        "bull_debit": bull_debit, "bull_profit": bull_max_profit, "bull_rr": bull_rr,
        "bull_break_even": bull_break_even, "bull_wrong_way": bull_wrong_way,
        "bull_put_sell": bull_put_short, "bull_put_buy": bull_put_long,
        "bull_put_credit": bull_put_credit, "bull_put_profit": bull_put_credit,
        "bull_put_risk": bull_put_max_loss, "bull_put_rr": bull_put_rr,
        "bull_put_wrong_way": bull_put_wrong_way,
        "bear_buy": bear_buy, "bear_sell": bear_sell,
        "bear_debit": bear_debit, "bear_profit": bear_max_profit, "bear_rr": bear_rr,
        "bear_break_even": bear_break_even, "bear_wrong_way": bear_wrong_way,
        "cc_score": cc, "cc_strike": cc_strike, "cc_premium": cc_premium,
        "cc_yield_pct": cc_yield_pct, "cc_annualized": cc_annualized,
        "cc_break_even": cc_break_even, "cc_wrong_way": cc_wrong_way,
        "lp_score": lp, "lp_strike": lp_strike, "lp_debit": lp_debit,
        "lp_break_even": lp_break_even, "lp_rr": lp_rr, "lp_wrong_way": lp_wrong_way,
        "width": width, "expiry_date": expiry_date.strftime("%Y-%m-%d"), "dte": dte,
    }

def fetch_scan_data(ticker, period="1y"):
    """Fetch OHLCV history for scanner scoring."""
    if not YFINANCE_OK: return None
    try:
        t = yf.Ticker(ticker)
        h = t.history(period=period, interval="1d")
        if len(h) < 22: return None
        price = float(h["Close"].iloc[-1])
        prev  = float(h["Close"].iloc[-2])
        return {
            "dates":      [idx.to_pydatetime().date() if hasattr(idx, "to_pydatetime") else idx.date() for idx in h.index.tolist()],
            "closes":     [float(x) for x in h["Close"].tolist()],
            "highs":      [float(x) for x in h["High"].tolist()],
            "lows":       [float(x) for x in h["Low"].tolist()],
            "price":      price,
            "change_pct": (price - prev) / prev * 100 if prev else 0,
        }
    except:
        return None

def calc_max_drawdown(equity_curve):
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)
    return max_dd

def backtest_strategy(ticker, strategy, period="1y", shares=100):
    """
    Simple historical backtest using weekly windows and estimated option pricing.
    Returns summary metrics plus per-trade rows.
    """
    data = fetch_scan_data(ticker, period=period)
    if not data or len(data["closes"]) < 40:
        return None

    closes = data["closes"]
    highs = data["highs"]
    lows = data["lows"]
    dates = data["dates"]
    trade_rows = []
    equity = [0.0]
    running_pnl = 0.0

    # Approximate weekly trades using 5 trading day steps and 14 DTE premium model.
    for start in range(20, len(closes) - 6, 5):
        entry_price = closes[start]
        exit_price = closes[start + 5]
        entry_date = dates[start]
        exit_date = dates[start + 5]
        atr_window_high = highs[max(0, start - 14):start + 1]
        atr_window_low = lows[max(0, start - 14):start + 1]
        atr_window_close = closes[max(0, start - 14):start + 1]
        atr = calc_atr(atr_window_high, atr_window_low, atr_window_close) if len(atr_window_close) > 3 else max(entry_price * 0.02, 1)
        iv = estimate_iv(entry_price, atr)
        step = strike_step_for_price(entry_price)
        width = max(round(atr * 1.5 / 5) * 5, 5)

        if strategy == "covered_call":
            strike = round_to_strike(entry_price * 1.03, step)
            premium = est_premium(entry_price, strike, dte=14, iv=iv)
            assigned = exit_price > strike
            pnl_per_share = premium + min(exit_price, strike) - entry_price
            capital = entry_price
            label = f"Sell {strike:.0f}C"
        elif strategy == "bull_put":
            short_put = round_to_strike(entry_price * 0.99, step)
            long_put = short_put - width
            credit = max(bs_put(entry_price, short_put, 14 / 365, iv) - bs_put(entry_price, long_put, 14 / 365, iv), 0.05)
            pnl_per_share = credit if exit_price >= short_put else credit - (short_put - exit_price)
            pnl_per_share = max(pnl_per_share, -(width - credit))
            capital = max(width - credit, 0.01)
            label = f"{short_put:.0f}/{long_put:.0f} Bull Put"
            assigned = exit_price < short_put
        elif strategy == "bull_call":
            long_call = round_to_strike(entry_price * 1.01, step)
            short_call = long_call + width
            debit = max(bs_call(entry_price, long_call, 14 / 365, iv) - bs_call(entry_price, short_call, 14 / 365, iv), 0.05)
            intrinsic = max(min(exit_price, short_call) - long_call, 0.0)
            pnl_per_share = intrinsic - debit
            capital = debit
            label = f"{long_call:.0f}/{short_call:.0f} Bull Call"
            assigned = exit_price < long_call
        else:
            long_put = round_to_strike(entry_price * 0.99, step)
            short_put = long_put - width
            debit = max(bs_put(entry_price, long_put, 14 / 365, iv) - bs_put(entry_price, short_put, 14 / 365, iv), 0.05)
            intrinsic = max(long_put - max(exit_price, short_put), 0.0)
            pnl_per_share = intrinsic - debit
            capital = debit
            label = f"{long_put:.0f}/{short_put:.0f} Bear Put"
            assigned = exit_price > long_put

        trade_pnl = round(pnl_per_share * shares, 2)
        trade_return = (trade_pnl / (capital * shares) * 100) if capital > 0 else 0.0
        running_pnl += trade_pnl
        equity.append(running_pnl)
        trade_rows.append({
            "entry_date": entry_date,
            "exit_date": exit_date,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "label": label,
            "pnl": trade_pnl,
            "return_pct": trade_return,
            "win": trade_pnl > 0,
            "assigned": assigned,
        })

    if not trade_rows:
        return None

    wins = sum(1 for row in trade_rows if row["win"])
    avg_return = sum(row["return_pct"] for row in trade_rows) / len(trade_rows)
    total_pnl = sum(row["pnl"] for row in trade_rows)
    first_trade = trade_rows[0]["entry_date"]
    last_trade = trade_rows[-1]["exit_date"]
    return {
        "ticker": ticker,
        "strategy": strategy,
        "trades": trade_rows,
        "trade_count": len(trade_rows),
        "win_rate": wins / len(trade_rows),
        "avg_return": avg_return,
        "total_pnl": total_pnl,
        "max_drawdown": calc_max_drawdown(equity),
        "first_trade": first_trade,
        "last_trade": last_trade,
    }

# ─────────────────────────────────────────
#  MOCK DATA (used when no API key set)
# ─────────────────────────────────────────
MOCK_PRICES = {
    "GOOGL": {"price": 303.12, "change": 1.43,  "pct": 0.47},
    "AAPL":  {"price": 260.45, "change": 0.87,  "pct": 0.34},
    "MSFT":  {"price": 371.70, "change": -1.20, "pct": -0.32},
    "CCL":   {"price": 27.85,  "change": -0.18, "pct": -0.64},
    "SOFI":  {"price": 8.42,   "change": -0.31, "pct": -3.55},
    "SPY":   {"price": 645.09, "change": -11.73,"pct": -1.79},
    "QQQ":   {"price": 611.07, "change": 0.88,  "pct": 0.14},
}
MOCK_RSI = {"GOOGL":54,"AAPL":49,"MSFT":47,"CCL":42,"SOFI":33,"SPY":52,"QQQ":51}
MOCK_MA50 = {"GOOGL":295.4,"AAPL":255.1,"MSFT":368.5,"CCL":26.9,"SOFI":9.8,"SPY":628.4,"QQQ":597.3}
MOCK_MA200= {"GOOGL":278.6,"AAPL":242.8,"MSFT":410.2,"CCL":24.3,"SOFI":11.4,"SPY":601.2,"QQQ":572.8}


def is_demo_mode():
    """Only true if Yahoo fails AND no Schwab key"""
    if DATA_SOURCE == "yahoo":
        return not YFINANCE_OK
    return APP_KEY == DEFAULT_APP_KEY

# ─────────────────────────────────────────
#  MAIN APP
# ─────────────────────────────────────────
class TradingApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("George's Trading Dashboard")
        self.geometry("1200x800")
        self.minsize(1000, 700)
        self.configure(bg=BG)

        # State
        self.stock_data   = {}
        self.history_data = {}
        self.history_series_data = {}
        self.earnings_timeline_data = {}
        self.pnl_log      = []
        self.last_update  = "Never"
        self.is_running   = True
        self.selected_ticker = tk.StringVar(value="GOOGL")
        self.detail_earnings_range = tk.StringVar(value="1Y")

        self._setup_fonts()
        self._setup_styles()
        self._build_ui()
        self._start_data_thread()

    # ── Fonts ──────────────────────────────
    def _setup_fonts(self):
        self.f_title  = tkfont.Font(family="Segoe UI", size=18, weight="bold")
        self.f_head   = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.f_body   = tkfont.Font(family="Segoe UI", size=10)
        self.f_small  = tkfont.Font(family="Segoe UI", size=9)
        self.f_mono   = tkfont.Font(family="Consolas",  size=11, weight="bold")
        self.f_mono_s = tkfont.Font(family="Consolas",  size=9)
        self.f_price  = tkfont.Font(family="Consolas",  size=14, weight="bold")
        self.f_big    = tkfont.Font(family="Consolas",  size=20, weight="bold")

    # ── ttk Styles ─────────────────────────
    def _setup_styles(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=TEXT, borderwidth=0)
        s.configure("TNotebook",        background=BG2, borderwidth=0, tabmargins=0)
        s.configure("TNotebook.Tab",    background=BG3, foreground=TEXT2,
                    padding=[16,8], font=("Segoe UI", 10))
        s.map("TNotebook.Tab",
              background=[("selected", ACCENT)],
              foreground=[("selected", WHITE)])
        s.configure("TFrame",  background=BG)
        s.configure("TLabel",  background=BG, foreground=TEXT)
        s.configure("TButton", background=BG3, foreground=TEXT, relief="flat",
                    padding=[10,6], font=("Segoe UI", 9))
        s.map("TButton", background=[("active", ACCENT)])
        s.configure("Vertical.TScrollbar", background=BG3, troughcolor=BG,
                    arrowcolor=TEXT2, borderwidth=0)

    # ── Build UI ───────────────────────────
    def _build_ui(self):
        # ── Top Bar ──
        top = tk.Frame(self, bg=BG2, height=56)
        top.pack(fill="x", side="top")
        top.pack_propagate(False)

        tk.Label(top, text="📈", font=("Segoe UI", 20), bg=BG2, fg=ACCENT).pack(side="left", padx=(16,6), pady=10)
        tk.Label(top, text="GEORGE'S TRADING DASHBOARD", font=self.f_head,
                 bg=BG2, fg=TEXT).pack(side="left", pady=10)

        if is_demo_mode():
            tk.Label(top, text="  ⚠ Install yfinance: pip install yfinance  ",
                     font=self.f_small, bg="#3a1a00", fg=YELLOW,
                     relief="flat", padx=8).pack(side="left", padx=16)
        elif DATA_SOURCE == "yahoo":
            tk.Label(top, text="  ● LIVE via Yahoo Finance  ",
                     font=self.f_small, bg="#003a1a", fg=GREEN,
                     relief="flat", padx=8).pack(side="left", padx=16)

        self.lbl_time = tk.Label(top, text="", font=self.f_mono_s, bg=BG2, fg=TEXT2)
        self.lbl_time.pack(side="right", padx=16)

        self.lbl_market = tk.Label(top, text="", font=self.f_small, bg=BG2, fg=TEXT2)
        self.lbl_market.pack(side="right", padx=8)

        self.lbl_update = tk.Label(top, text="Last update: —", font=self.f_small, bg=BG2, fg=TEXT3)
        self.lbl_update.pack(side="right", padx=16)

        tk.Button(top, text="⟳ Refresh", font=self.f_small, bg=ACCENT, fg=WHITE,
                  relief="flat", cursor="hand2", padx=10,
                  command=self._manual_refresh).pack(side="right", padx=8, pady=12)

        # ── Tabs ──
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=0, pady=0)

        tab_dash    = tk.Frame(nb, bg=BG)
        tab_charts  = tk.Frame(nb, bg=BG)
        tab_income  = tk.Frame(nb, bg=BG)
        tab_backtest= tk.Frame(nb, bg=BG)
        tab_patterns= tk.Frame(nb, bg=BG)
        tab_movers  = tk.Frame(nb, bg=BG)
        tab_spmo    = tk.Frame(nb, bg=BG)
        tab_scanner = tk.Frame(nb, bg=BG)
        tab_alerts  = tk.Frame(nb, bg=BG)
        tab_ai      = tk.Frame(nb, bg=BG)
        tab_setup   = tk.Frame(nb, bg=BG)

        nb.add(tab_dash,    text="  Dashboard  ")
        nb.add(tab_charts,  text="  Charts  ")
        nb.add(tab_income,  text="  Income Tracker  ")
        nb.add(tab_backtest,text="  Backtester  ")
        nb.add(tab_patterns,text="  Pattern Detector  ")
        nb.add(tab_movers,  text="  Movers  ")
        nb.add(tab_spmo,    text="  SPMO Strategy  ")
        nb.add(tab_scanner, text="  📡 Spread Scanner  ")
        nb.add(tab_alerts,  text="  Alerts  ")
        nb.add(tab_ai,      text="  🤖 AI Themes  ")
        nb.add(tab_setup,   text="  Setup  ")

        self._build_dashboard(tab_dash)
        self._build_charts(tab_charts)
        self._build_income(tab_income)
        self._build_backtester(tab_backtest)
        self._build_patterns(tab_patterns)
        self._build_movers(tab_movers)
        self._build_spmo(tab_spmo)
        self._build_scanner(tab_scanner)
        self._build_alerts(tab_alerts)
        self._build_ai_themes(tab_ai)
        self._build_setup(tab_setup)

        # Clock tick
        self._tick_clock()

    # ═══════════════════════════════════════
    #  TAB 1 — DASHBOARD
    # ═══════════════════════════════════════
    def _build_dashboard(self, parent):
        # Left panel — stock cards
        left = tk.Frame(parent, bg=BG, width=520)
        left.pack(side="left", fill="y", padx=(12,6), pady=12)
        left.pack_propagate(False)

        tk.Label(left, text="PORTFOLIO", font=self.f_small,
                 bg=BG, fg=TEXT3).pack(anchor="w", pady=(0,6))

        cards_frame = tk.Frame(left, bg=BG)
        cards_frame.pack(fill="both", expand=True)

        self.stock_cards = {}
        tickers = list(PORTFOLIO.keys())
        for i, ticker in enumerate(tickers):
            r, c = divmod(i, 2)
            card = self._make_stock_card(cards_frame, ticker)
            card.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            self.stock_cards[ticker] = card
            cards_frame.columnconfigure(c, weight=1)

        # Market ETFs row
        etf_frame = tk.Frame(left, bg=BG)
        etf_frame.pack(fill="x", pady=(8,0))
        tk.Label(etf_frame, text="MARKET ETFs", font=self.f_small,
                 bg=BG, fg=TEXT3).pack(anchor="w", pady=(0,4))

        etf_row = tk.Frame(etf_frame, bg=BG)
        etf_row.pack(fill="x")
        self.etf_cards = {}
        for i, ticker in enumerate(["SPY","QQQ","SPMO"]):
            card = self._make_etf_card(etf_row, ticker)
            card.grid(row=0, column=i, padx=4, sticky="nsew")
            etf_row.columnconfigure(i, weight=1)
            self.etf_cards[ticker] = card
        # Right panel — detail + summary
        right = tk.Frame(parent, bg=BG)
        right.pack(side="left", fill="both", expand=True, padx=(6,12), pady=12)

        # Summary cards row
        summary = tk.Frame(right, bg=BG)
        summary.pack(fill="x", pady=(0,8))
        self.summary_cards = {}
        metrics = [
            ("WEEKLY INCOME", "$0", ACCENT2),
            ("MONTHLY EST.",  "$0", ACCENT2),
            ("GOAL PROGRESS", "0%", ACCENT),
            ("ACCOUNT SIZE",  f"${ACCOUNT_SIZE:,}", TEXT),
        ]
        for i, (label, val, col) in enumerate(metrics):
            f = tk.Frame(summary, bg=CARD, relief="flat",
                         highlightbackground=BORDER, highlightthickness=1)
            f.grid(row=0, column=i, padx=4, sticky="nsew")
            summary.columnconfigure(i, weight=1)
            tk.Label(f, text=label, font=self.f_small, bg=CARD, fg=TEXT3).pack(pady=(10,2))
            lbl = tk.Label(f, text=val, font=self.f_price, bg=CARD, fg=col)
            lbl.pack(pady=(0,10))
            self.summary_cards[label] = lbl

        # Detail panel
        detail_frame = tk.Frame(right, bg=CARD,
                                highlightbackground=BORDER, highlightthickness=1)
        detail_frame.pack(fill="both", expand=True)
        self._build_detail_panel(detail_frame)

    def _make_stock_card(self, parent, ticker):
        cfg = PORTFOLIO[ticker]
        f = tk.Frame(parent, bg=CARD, cursor="hand2",
                     highlightbackground=BORDER, highlightthickness=1)
        f.bind("<Button-1>", lambda e, t=ticker: self._select_ticker(t))

        # Colored top bar
        bar = tk.Frame(f, bg=cfg["color"], height=3)
        bar.pack(fill="x")
        bar.bind("<Button-1>", lambda e, t=ticker: self._select_ticker(t))

        inner = tk.Frame(f, bg=CARD, padx=10, pady=8)
        inner.pack(fill="both")
        inner.bind("<Button-1>", lambda e, t=ticker: self._select_ticker(t))

        row1 = tk.Frame(inner, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text=ticker, font=self.f_mono, bg=CARD, fg=TEXT).pack(side="left")

        lbl_sig = tk.Label(row1, text="HOLD", font=self.f_small, bg=CARD, fg=TEXT2,
                           relief="flat", padx=6, pady=2)
        lbl_sig.pack(side="right")

        lbl_price = tk.Label(inner, text="$—", font=self.f_price, bg=CARD, fg=TEXT)
        lbl_price.pack(anchor="w")

        lbl_chg = tk.Label(inner, text="—", font=self.f_small, bg=CARD, fg=TEXT2)
        lbl_chg.pack(anchor="w")

        # RSI bar
        rsi_row = tk.Frame(inner, bg=CARD)
        rsi_row.pack(fill="x", pady=(6,0))
        tk.Label(rsi_row, text="RSI", font=self.f_small, bg=CARD, fg=TEXT3, width=4).pack(side="left")
        canvas_rsi = tk.Canvas(rsi_row, height=6, bg=BG3, highlightthickness=0)
        canvas_rsi.pack(side="left", fill="x", expand=True, padx=(4,4))
        lbl_rsi = tk.Label(rsi_row, text="50", font=self.f_mono_s, bg=CARD, fg=TEXT2, width=3)
        lbl_rsi.pack(side="left")

        # Income
        lbl_income = tk.Label(inner, text="Call $— → $—/wk", font=self.f_small, bg=CARD, fg=ACCENT2)
        lbl_income.pack(anchor="w", pady=(4,0))

        # Earnings — starts as loading, gets updated after Yahoo fetch
        lbl_earn = tk.Label(inner, text="ER: loading...", font=self.f_small,
                            bg=CARD, fg=TEXT3)
        lbl_earn.pack(anchor="w")

        # Store refs — include earn so we can update it after fetch
        f._refs = {
            "price": lbl_price, "change": lbl_chg, "signal": lbl_sig,
            "rsi_canvas": canvas_rsi, "rsi_lbl": lbl_rsi, "income": lbl_income,
            "earn": lbl_earn,
        }
        return f

    def _make_etf_card(self, parent, ticker):
        f = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        inner = tk.Frame(f, bg=CARD, padx=10, pady=8)
        inner.pack(fill="both")

        row1 = tk.Frame(inner, bg=CARD)
        row1.pack(fill="x")
        tk.Label(row1, text=ticker, font=self.f_mono, bg=CARD, fg=TEXT).pack(side="left")
        lbl_sig = tk.Label(row1, text="—", font=self.f_small, bg=CARD, fg=TEXT2)
        lbl_sig.pack(side="right")

        lbl_price = tk.Label(inner, text="$—", font=self.f_price, bg=CARD, fg=TEXT)
        lbl_price.pack(anchor="w")
        lbl_chg = tk.Label(inner, text="—", font=self.f_small, bg=CARD, fg=TEXT2)
        lbl_chg.pack(anchor="w")

        f._refs = {"price": lbl_price, "change": lbl_chg, "signal": lbl_sig}
        return f

    def _make_earnings_reaction_card(self, parent, ticker):
        card = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=10, pady=(8,2))
        tk.Label(head, text=ticker, font=self.f_mono, bg=CARD, fg=TEXT).pack(side="left")
        lbl_stats = tk.Label(head, text="Loading earnings history...", font=self.f_small, bg=CARD, fg=TEXT3)
        lbl_stats.pack(side="right")

        canvas = tk.Canvas(card, height=110, bg=BG2, highlightthickness=0)
        canvas.pack(fill="x", padx=10, pady=(0,4))

        lbl_info = tk.Label(card, text="Waiting for history...", font=self.f_small, bg=CARD, fg=TEXT2, justify="left")
        lbl_info.pack(anchor="w", padx=10, pady=(0,8))
        card._refs = {"canvas": canvas, "stats": lbl_stats, "info": lbl_info}
        return card

    def _compute_earnings_reactions(self, ticker):
        series = self.history_series_data.get(ticker, [])
        timeline = self.earnings_timeline_data.get(ticker, {"historical": [], "upcoming": None})
        if len(series) < 10:
            return {"historical": [], "upcoming": timeline.get("upcoming"), "series": series}

        dates = [pt["date"] for pt in series]
        closes = [pt["close"] for pt in series]
        reactions = []
        for event_date in timeline.get("historical", []):
            idx = next((i for i, d in enumerate(dates) if d >= event_date), None)
            if idx is None or idx < 1 or idx >= len(closes) - 1:
                continue
            pre_close = closes[idx - 1]
            day1_close = closes[min(idx + 1, len(closes) - 1)]
            day3_close = closes[min(idx + 3, len(closes) - 1)]
            if not pre_close:
                continue
            day1_pct = ((day1_close - pre_close) / pre_close) * 100
            day3_pct = ((day3_close - pre_close) / pre_close) * 100
            reactions.append({
                "date": dates[idx],
                "index": idx,
                "day1_pct": round(day1_pct, 2),
                "day3_pct": round(day3_pct, 2),
            })
        return {"historical": reactions, "upcoming": timeline.get("upcoming"), "series": series}

    def _filter_series_for_range(self, series, years_label):
        if not series:
            return []
        if years_label == "2Y":
            return series
        end_date = series[-1]["date"]
        start_cutoff = end_date - timedelta(days=365)
        filtered = [pt for pt in series if pt["date"] >= start_cutoff]
        return filtered or series

    def _draw_earnings_mini_chart(self, ticker, canvas, stats_lbl, info_lbl):
        if not canvas or not stats_lbl or not info_lbl:
            return
        canvas.update_idletasks()
        w = max(canvas.winfo_width(), 280)
        h = max(canvas.winfo_height(), 110)
        canvas.delete("all")

        reaction_data = self._compute_earnings_reactions(ticker)
        series = reaction_data["series"]
        if len(series) < 10:
            stats_lbl.config(text="Need more history", fg=TEXT3)
            info_lbl.config(text="Price history is still loading for this symbol.", fg=TEXT3)
            return

        closes = [pt["close"] for pt in series]
        min_p = min(closes)
        max_p = max(closes)
        pad = max((max_p - min_p) * 0.08, 1)
        min_p -= pad
        max_p += pad
        x_pad = 8
        y_pad = 10
        usable_w = max(w - x_pad * 2, 10)
        usable_h = max(h - y_pad * 2, 10)

        def x_for_idx(idx):
            denom = max(len(series) - 1, 1)
            return x_pad + (idx / denom) * usable_w

        def y_for_price(price):
            span = max(max_p - min_p, 1)
            return y_pad + (max_p - price) / span * usable_h

        points = []
        for idx, pt in enumerate(series):
            points.extend([x_for_idx(idx), y_for_price(pt["close"])])
        cfg = PORTFOLIO.get(ticker, {})
        canvas.create_line(*points, fill=cfg.get("color", ACCENT), width=2, smooth=True)

        hist_events = reaction_data["historical"][-5:]
        for event in hist_events:
            x = x_for_idx(event["index"])
            drop = event["day3_pct"] < 0
            line_color = RED if drop else GREEN
            canvas.create_line(x, y_pad, x, h - y_pad, fill=line_color, dash=(3, 4))
            canvas.create_text(
                min(x + 18, w - 24),
                y_pad + 10,
                text=f"{event['day3_pct']:+.1f}%",
                fill=line_color,
                font=("Segoe UI", 7, "bold")
            )

        upcoming = reaction_data["upcoming"]
        if upcoming:
            last_date = series[-1]["date"]
            days_forward = (upcoming - last_date).days
            if days_forward >= 0:
                projected_idx = (len(series) - 1) + max(days_forward, 1)
                future_x = min(x_pad + (projected_idx / max(len(series) + 10, 1)) * usable_w, w - x_pad)
                canvas.create_line(future_x, y_pad, future_x, h - y_pad, fill=YELLOW, dash=(2, 2))
                canvas.create_text(
                    future_x,
                    h - 8,
                    text=upcoming.strftime("%b %d"),
                    fill=YELLOW,
                    font=("Segoe UI", 7, "bold")
                )

        worst_drop = min((e["day3_pct"] for e in hist_events), default=None)
        avg_move = None
        if hist_events:
            avg_move = sum(e["day3_pct"] for e in hist_events) / len(hist_events)

        stats_parts = []
        if worst_drop is not None:
            stats_parts.append(f"Worst 3D: {worst_drop:+.1f}%")
        if avg_move is not None:
            stats_parts.append(f"Avg 3D: {avg_move:+.1f}%")
        stats_lbl.config(
            text="   |   ".join(stats_parts) if stats_parts else "No past earnings reactions",
            fg=RED if worst_drop is not None and worst_drop < -3 else TEXT2
        )

        current_text = upcoming.strftime("%b %d") if upcoming else "—"
        hist_text = ", ".join(e["date"].strftime("%b %d") for e in hist_events[-3:]) if hist_events else "None"
        info_lbl.config(
            text=f"Current ER: {current_text}   |   Recent ERs: {hist_text}",
            fg=TEXT2
        )

    def _render_earnings_dashboard(self):
        return

    def _draw_detail_earnings_chart(self, ticker):
        if not hasattr(self, "detail_earnings_plot_frame"):
            return
        if self.detail_earnings_canvas_widget is not None:
            self.detail_earnings_canvas_widget.get_tk_widget().destroy()
            self.detail_earnings_canvas_widget = None

        range_label = self.detail_earnings_range.get() if hasattr(self, "detail_earnings_range") else "1Y"
        reaction_data = self._compute_earnings_reactions(ticker)
        full_series = reaction_data["series"]
        series = self._filter_series_for_range(full_series, range_label)
        if len(series) < 10:
            self.detail_earnings_stats.config(text="History still loading", fg=TEXT3)
            self.detail_earnings_info.config(text="Not enough price history yet to draw the earnings chart.", fg=TEXT3)
            return

        series_dates = {pt["date"] for pt in series}
        hist_events = [e for e in reaction_data["historical"] if e["date"] in series_dates]
        dates = [pt["date"] for pt in series]
        closes = [pt["close"] for pt in series]
        color = PORTFOLIO.get(ticker, {}).get("color", ACCENT)

        if not MATPLOTLIB_OK:
            self.detail_earnings_stats.config(text="matplotlib not installed", fg=RED)
            self.detail_earnings_info.config(text="Install matplotlib to view the earnings chart.", fg=TEXT3)
            return

        fig = Figure(figsize=(8.6, 3.2), facecolor=BG2)
        fig.subplots_adjust(left=0.08, right=0.98, top=0.9, bottom=0.2)
        ax = fig.add_subplot(111)
        ax.set_facecolor(BG2)
        ax.plot(dates, closes, color=color, linewidth=1.8)
        ax.fill_between(dates, closes, min(closes) * 0.98, color=color, alpha=0.08)

        x_min = min(dates)
        x_max = max(dates)
        right_pad_days = 14 if range_label == "1Y" else 21
        ax.set_xlim(x_min, x_max + timedelta(days=right_pad_days))

        for event in hist_events:
            line_color = RED if event["day3_pct"] < 0 else GREEN
            ax.axvline(event["date"], color=line_color, linestyle="--", linewidth=1.2, alpha=0.9, zorder=5)
            nearest_close = closes[min(range(len(dates)), key=lambda i: abs((dates[i] - event["date"]).days))]
            ax.annotate(
                f"{event['day3_pct']:+.1f}%",
                xy=(event["date"], nearest_close),
                xytext=(4, 8),
                textcoords="offset points",
                color=line_color,
                fontsize=8,
                fontweight="bold"
            )

        upcoming = reaction_data["upcoming"]
        if not upcoming:
            upcoming = parse_short_earnings_date(get_earnings(ticker))
        if upcoming:
            ax.axvline(upcoming, color=YELLOW, linestyle="-", linewidth=2.2, alpha=0.95, zorder=6)
            ax.text(upcoming, ax.get_ylim()[1], f" Next ER {upcoming.strftime('%b %d')}",
                    color=YELLOW, fontsize=8, va="top", ha="left")

        ax.grid(axis="y", color=BORDER, linestyle="--", linewidth=0.6, alpha=0.6)
        ax.spines[:].set_color(BORDER)
        ax.tick_params(axis="x", colors=TEXT3, labelsize=8)
        ax.tick_params(axis="y", colors=TEXT3, labelsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:.0f}"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1 if range_label == "1Y" else 2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        fig.autofmt_xdate(rotation=0, ha="center")
        ax.set_title(f"{ticker} {range_label} Price History With Earnings", color=TEXT, fontsize=10, loc="left", pad=8)

        self.detail_earnings_canvas_widget = FigureCanvasTkAgg(fig, master=self.detail_earnings_plot_frame)
        self.detail_earnings_canvas_widget.draw()
        self.detail_earnings_canvas_widget.get_tk_widget().pack(fill="both", expand=True)

        worst_drop = min((e["day3_pct"] for e in hist_events), default=None)
        avg_drop = (sum(e["day3_pct"] for e in hist_events) / len(hist_events)) if hist_events else None
        stats = []
        if worst_drop is not None:
            stats.append(f"Worst 3D after ER: {worst_drop:+.1f}%")
        if avg_drop is not None:
            stats.append(f"Avg 3D after ER: {avg_drop:+.1f}%")
        stats.insert(0, f"Range: {range_label}")
        self.detail_earnings_stats.config(
            text="   |   ".join(stats) if stats else "No historical earnings reactions found",
            fg=RED if worst_drop is not None and worst_drop < -3 else TEXT2
        )

        recent_hist = ", ".join(e["date"].strftime("%b %d") for e in hist_events[-4:]) if hist_events else "None"
        upcoming_text = upcoming.strftime("%b %d") if upcoming else "—"
        self.detail_earnings_info.config(
            text=f"Current ER: {upcoming_text}   |   Historical ERs: {recent_hist}",
            fg=TEXT2
        )

    def _build_detail_panel(self, parent):
        tk.Label(parent, text="POSITION DETAIL",
                 font=self.f_small, bg=CARD, fg=TEXT3).pack(anchor="w", padx=14, pady=(12,0))

        self.detail_ticker  = tk.Label(parent, text="Select a stock →",
                                       font=self.f_big, bg=CARD, fg=TEXT)
        self.detail_ticker.pack(anchor="w", padx=14, pady=(4,0))

        self.detail_price   = tk.Label(parent, text="", font=self.f_price, bg=CARD, fg=TEXT)
        self.detail_price.pack(anchor="w", padx=14)

        self.detail_signal  = tk.Label(parent, text="", font=self.f_head, bg=CARD, fg=ACCENT2)
        self.detail_signal.pack(anchor="w", padx=14, pady=(6,0))

        sep = tk.Frame(parent, bg=BORDER, height=1)
        sep.pack(fill="x", padx=14, pady=8)

        grid = tk.Frame(parent, bg=CARD)
        grid.pack(fill="x", padx=14)
        self.detail_labels = {}
        items = [("RSI","—"),("50-Day MA","—"),("200-Day MA","—"),
                 ("vs MA50","—"),("vs MA200","—"),("Weekly Income","—")]
        for i, (k, v) in enumerate(items):
            r, c = divmod(i, 2)
            box = tk.Frame(grid, bg=BG3, padx=10, pady=8)
            box.grid(row=r, column=c, padx=4, pady=4, sticky="nsew")
            grid.columnconfigure(c, weight=1)
            tk.Label(box, text=k, font=self.f_small, bg=BG3, fg=TEXT3).pack(anchor="w")
            lbl = tk.Label(box, text=v, font=self.f_head, bg=BG3, fg=TEXT)
            lbl.pack(anchor="w")
            self.detail_labels[k] = lbl

        chart_sep = tk.Frame(parent, bg=BORDER, height=1)
        chart_sep.pack(fill="x", padx=14, pady=8)

        chart_wrap = tk.Frame(parent, bg=CARD, padx=14, pady=4)
        chart_wrap.pack(fill="both", expand=True)
        self.detail_earnings_title = tk.Label(
            chart_wrap,
            text="1Y PRICE HISTORY WITH EARNINGS",
            font=self.f_small,
            bg=CARD,
            fg=TEXT3
        )
        self.detail_earnings_title.pack(anchor="w", pady=(0,6))
        range_row = tk.Frame(chart_wrap, bg=CARD)
        range_row.pack(fill="x", pady=(0,4))
        tk.Label(range_row, text="Range:", font=self.f_small, bg=CARD, fg=TEXT3).pack(side="left")
        for label in ("1Y", "2Y"):
            tk.Radiobutton(
                range_row,
                text=label,
                value=label,
                variable=self.detail_earnings_range,
                command=lambda: self._draw_detail_earnings_chart(self.selected_ticker.get()),
                bg=CARD,
                fg=TEXT2,
                selectcolor=ACCENT,
                activebackground=CARD,
                activeforeground=TEXT,
                font=self.f_small,
                relief="flat",
                cursor="hand2"
            ).pack(side="left", padx=(8, 0))
        self.detail_earnings_stats = tk.Label(
            chart_wrap, text="", font=self.f_small, bg=CARD, fg=TEXT2
        )
        self.detail_earnings_stats.pack(anchor="w")
        self.detail_earnings_plot_frame = tk.Frame(chart_wrap, bg=BG2, height=260)
        self.detail_earnings_plot_frame.pack(fill="both", expand=True, pady=(6,4))
        self.detail_earnings_plot_frame.pack_propagate(False)
        self.detail_earnings_canvas_widget = None
        self.detail_earnings_info = tk.Label(
            chart_wrap, text="", font=self.f_small, bg=CARD, fg=TEXT2, justify="left"
        )
        self.detail_earnings_info.pack(anchor="w", pady=(0,6))

        # Covered call action row
        sep2 = tk.Frame(parent, bg=BORDER, height=1)
        sep2.pack(fill="x", padx=14, pady=8)

        action = tk.Frame(parent, bg=CARD, padx=14)
        action.pack(fill="x")
        self.detail_call_title = tk.Label(
            action,
            text=f"COVERED CALL - {covered_call_expiry_label()} Expiry",
            font=self.f_small,
            bg=CARD,
            fg=TEXT3
        )
        self.detail_call_title.pack(anchor="w", pady=(0,6))

        self.detail_call = tk.Label(action, text="", font=self.f_head, bg=CARD, fg=ACCENT2)
        self.detail_call.pack(anchor="w")

        self.detail_earn = tk.Label(action, text="", font=self.f_small, bg=CARD, fg=YELLOW)
        self.detail_earn.pack(anchor="w", pady=(4,0))

    # ═══════════════════════════════════════
    #  TAB 2 — CHARTS
    # ═══════════════════════════════════════
    def _build_charts(self, parent):
        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=12, pady=(12,6))

        tk.Label(top, text="Price History & Indicators", font=self.f_head,
                 bg=BG, fg=TEXT).pack(side="left")

        self.chart_ticker_var = tk.StringVar(value="GOOGL")
        for t in PORTFOLIO.keys():
            btn = tk.Radiobutton(top, text=t, variable=self.chart_ticker_var,
                                 value=t, command=self._update_chart,
                                 bg=BG, fg=TEXT2, selectcolor=ACCENT,
                                 activebackground=BG, font=self.f_small,
                                 relief="flat", cursor="hand2")
            btn.pack(side="left", padx=6)

        self.chart_frame = tk.Frame(parent, bg=BG)
        self.chart_frame.pack(fill="both", expand=True, padx=12, pady=(0,12))
        self._draw_chart("GOOGL")

    def _draw_chart(self, ticker):
        for w in self.chart_frame.winfo_children():
            w.destroy()

        if not MATPLOTLIB_OK:
            tk.Label(self.chart_frame,
                     text="Install matplotlib:\npip install matplotlib",
                     font=self.f_head, bg=BG, fg=RED).pack(expand=True)
            return

        history = self.history_data.get(ticker, [])
        series = self.history_series_data.get(ticker, [])
        if len(history) < 5:
            # Demo price history
            import random
            random.seed(hash(ticker))
            base = MOCK_PRICES.get(ticker, {}).get("price", 100)
            history = [base * (1 + random.gauss(0, 0.015)) for _ in range(120)]
            for i in range(1, len(history)):
                history[i] = history[i-1] * (1 + random.gauss(0.0002, 0.012))

        n = len(history)
        if series:
            dates = [item.get("date") for item in series[:n]]
            if len(dates) < n:
                dates += [None] * (n - len(dates))
        else:
            dates = [None] * n
        xs = list(range(n))
        ma50_vals = [calc_ma(history[:i+1], 50) or history[i] for i in range(n)]
        ma200_vals = [calc_ma(history[:i+1], 200) or history[i] for i in range(n)]

        fig = Figure(figsize=(8, 4.5), facecolor=BG)
        fig.subplots_adjust(left=0.06, right=0.98, top=0.88, bottom=0.18, hspace=0.1)

        ax1 = fig.add_subplot(211)
        ax2 = fig.add_subplot(212, sharex=ax1)

        for ax in [ax1, ax2]:
            ax.set_facecolor(BG2)
            ax.tick_params(colors=TEXT3, labelsize=8)
            ax.spines[:].set_color(BORDER)

        cfg   = PORTFOLIO.get(ticker, {})
        color = cfg.get("color", ACCENT)

        # Price line
        ax1.plot(xs, history, color=color, linewidth=1.5, alpha=0.9, label=ticker)
        ax1.plot(xs, ma50_vals,  color=ACCENT2, linewidth=1, alpha=0.7, linestyle="--", label="MA50")
        ax1.plot(xs, ma200_vals, color=YELLOW,  linewidth=1, alpha=0.7, linestyle=":",  label="MA200")
        ax1.fill_between(xs, history, min(history)*0.98, alpha=0.08, color=color)

        # Hover tooltip for price points
        annot = ax1.annotate(
            "",
            xy=(0, 0),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=8,
            color=TEXT,
            bbox={"boxstyle": "round,pad=0.3", "fc": BG3, "ec": TEXT3, "alpha": 0.95},
            arrowprops={"arrowstyle": "->", "color": TEXT},
        )
        annot.set_visible(False)

        tooltip_lbl = tk.Label(
            self.chart_frame,
            text="",
            font=self.f_body,
            bg=BG3,
            fg=TEXT,
            bd=1,
            relief="solid",
            justify="left",
        )
        tooltip_lbl.place_forget()

        def update_annot(ind):
            x = ind
            price = history[x]
            date_label = dates[x].strftime("%b %d, %Y") if dates[x] else f"Day {x + 1}"
            annot.xy = (x, price)
            annot.set_text(f"{date_label}\n${price:.2f}")
            tooltip_lbl.config(text=f"{date_label}\n${price:.2f}")

        def on_motion(event):
            if event.inaxes != ax1 or event.xdata is None:
                if annot.get_visible():
                    annot.set_visible(False)
                    canvas.draw_idle()
                tooltip_lbl.place_forget()
                return

            nearest = min(range(n), key=lambda i: abs(i - event.xdata))
            if abs(nearest - event.xdata) <= 0.5:
                update_annot(nearest)
                annot.set_visible(True)
                tooltip_lbl.place(x=event.x + 12, y=event.y + 12)
                tooltip_lbl.lift()
                canvas.draw_idle()
            else:
                if annot.get_visible():
                    annot.set_visible(False)
                    canvas.draw_idle()
                tooltip_lbl.place_forget()

        # Strike line
        if cfg.get("call_strike"):
            ax1.axhline(y=cfg["call_strike"], color=RED, linewidth=0.8,
                        linestyle="--", alpha=0.7, label=f"Call Strike ${cfg['call_strike']}")

        ax1.set_title(f"{ticker}  |  {n}-Day History",
                      color=TEXT, fontsize=10, pad=6, loc="left")
        ax1.legend(loc="upper left", fontsize=7, facecolor=BG3,
                   labelcolor=TEXT2, framealpha=0.8)
        ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"${x:.0f}"))

        # RSI
        rsi_vals = [calc_rsi(history[:i+1]) for i in range(max(15, n))]
        rsi_vals = rsi_vals[-n:]
        rsi_xs   = list(range(len(rsi_vals)))

        rsi_colors = [GREEN if v < 35 else RED if v > 65 else ACCENT2 for v in rsi_vals]
        ax2.plot(rsi_xs, rsi_vals, color=ACCENT, linewidth=1.2)
        ax2.fill_between(rsi_xs, rsi_vals, 50, where=[v > 50 for v in rsi_vals],
                         alpha=0.15, color=GREEN)
        ax2.fill_between(rsi_xs, rsi_vals, 50, where=[v <= 50 for v in rsi_vals],
                         alpha=0.15, color=RED)
        ax2.axhline(y=70, color=RED,   linewidth=0.7, linestyle="--", alpha=0.5)
        ax2.axhline(y=30, color=GREEN, linewidth=0.7, linestyle="--", alpha=0.5)
        ax2.axhline(y=50, color=BORDER, linewidth=0.5, alpha=0.5)
        ax2.set_ylim(0, 100)
        ax2.set_ylabel("RSI", color=TEXT2, fontsize=8)

        canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        canvas.draw()
        fig.canvas.mpl_connect("motion_notify_event", on_motion)
        canvas.get_tk_widget().pack(fill="both", expand=True)

    def _update_chart(self):
        self._draw_chart(self.chart_ticker_var.get())

    # ═══════════════════════════════════════
    #  TAB 3 — INCOME TRACKER
    # ═══════════════════════════════════════
    def _build_income(self, parent):
        tk.Label(parent, text="Monthly Income Tracker — $5,000 Goal",
                 font=self.f_head, bg=BG, fg=TEXT).pack(anchor="w", padx=14, pady=(12,0))

        # Progress bar
        prog_frame = tk.Frame(parent, bg=CARD,
                              highlightbackground=BORDER, highlightthickness=1)
        prog_frame.pack(fill="x", padx=12, pady=8)
        inner = tk.Frame(prog_frame, bg=CARD, padx=14, pady=12)
        inner.pack(fill="x")

        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x")
        tk.Label(row, text="Monthly Covered Call Income",
                 font=self.f_body, bg=CARD, fg=TEXT2).pack(side="left")
        self.income_total_lbl = tk.Label(row, text="$—  /  $5,000",
                                          font=self.f_head, bg=CARD, fg=ACCENT2)
        self.income_total_lbl.pack(side="right")

        self.prog_canvas = tk.Canvas(inner, height=14, bg=BG3, highlightthickness=0)
        self.prog_canvas.pack(fill="x", pady=6)

        # Per-stock breakdown table
        cols_frame = tk.Frame(parent, bg=BG)
        cols_frame.pack(fill="both", expand=True, padx=12, pady=(0,12))

        headers = ["TICKER","SHARES","STRIKE","PRICE","PREMIUM/SHR","WEEKLY","MONTHLY","SIGNAL"]
        col_widths = [80,70,70,90,100,90,100,100]
        hdr = tk.Frame(cols_frame, bg=BG3)
        hdr.pack(fill="x")
        for h, w in zip(headers, col_widths):
            tk.Label(hdr, text=h, font=self.f_small, bg=BG3, fg=TEXT3,
                     width=w//7, anchor="w").pack(side="left", padx=6, pady=6)

        self.income_rows = {}
        for ticker in PORTFOLIO.keys():
            row_frame = tk.Frame(cols_frame, bg=CARD,
                                 highlightbackground=BORDER, highlightthickness=1)
            row_frame.pack(fill="x", pady=1)
            labels = {}
            cfg = PORTFOLIO[ticker]
            defaults = [ticker, str(cfg["shares"]), f"${cfg['call_strike']}",
                        "$—", "$—", "$—", "$—", "—"]
            for val, w in zip(defaults, col_widths):
                lbl = tk.Label(row_frame, text=val, font=self.f_mono_s,
                               bg=CARD, fg=TEXT, width=w//7, anchor="w")
                lbl.pack(side="left", padx=6, pady=8)
                labels[len(labels)] = lbl
            self.income_rows[ticker] = labels

        # Totals row
        total_row = tk.Frame(cols_frame, bg=BG2,
                             highlightbackground=ACCENT, highlightthickness=1)
        total_row.pack(fill="x", pady=(4,0))
        tk.Label(total_row, text="TOTAL", font=self.f_head, bg=BG2, fg=TEXT, width=11).pack(side="left", padx=6, pady=8)
        tk.Label(total_row, text="", bg=BG2, width=30).pack(side="left")
        self.total_weekly_lbl  = tk.Label(total_row, text="$—", font=self.f_head, bg=BG2, fg=ACCENT2, width=12)
        self.total_weekly_lbl.pack(side="left", padx=6)
        self.total_monthly_lbl = tk.Label(total_row, text="$—", font=self.f_head, bg=BG2, fg=ACCENT2, width=14)
        self.total_monthly_lbl.pack(side="left", padx=6)

    # ═══════════════════════════════════════
    #  TAB 4 — SPREAD SCANNER
    # ═══════════════════════════════════════
    def _build_backtester(self, parent):
        self.backtest_results = None

        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(top, text="Historical Backtester",
                 font=self.f_head, bg=BG, fg=TEXT).pack(side="left")

        self.backtest_status = tk.Label(
            top,
            text='Test ideas like: "If I sold this covered call every week for 1 year..."',
            font=self.f_small, bg=BG, fg=TEXT2
        )
        self.backtest_status.pack(side="left", padx=16)

        explainer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        explainer.pack(fill="x", padx=12, pady=(0, 8))
        self.backtest_explainer = tk.Label(
            explainer,
            text=(
                "This estimates what repeated weekly trades would have looked like over the chosen period. "
                "It uses modeled option pricing, so treat it as a comparison tool, not exact historical fills."
            ),
            font=self.f_small, bg=CARD, fg=TEXT2, wraplength=1050, justify="left"
        )
        self.backtest_explainer.pack(anchor="w", padx=12, pady=(10, 10))

        controls = tk.Frame(parent, bg=BG2, highlightbackground=BORDER, highlightthickness=1)
        controls.pack(fill="x", padx=12, pady=(0, 8))
        inner = tk.Frame(controls, bg=BG2, padx=12, pady=10)
        inner.pack(fill="x")

        tk.Label(inner, text="Ticker", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left")
        self.backtest_ticker = tk.StringVar(value="GOOGL")
        tk.Entry(inner, textvariable=self.backtest_ticker, font=self.f_mono_s, width=10,
                 bg=BG3, fg=TEXT, insertbackground=TEXT, relief="flat").pack(side="left", padx=(6, 16))

        tk.Label(inner, text="Strategy", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left")
        self.backtest_strategy = tk.StringVar(value="covered_call")
        ttk.Combobox(inner, textvariable=self.backtest_strategy, width=16, state="readonly",
                     values=["covered_call", "bull_put", "bull_call", "bear_put"]).pack(side="left", padx=(6, 16))

        tk.Label(inner, text="Period", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left")
        self.backtest_period = tk.StringVar(value="1y")
        ttk.Combobox(inner, textvariable=self.backtest_period, width=8, state="readonly",
                     values=["6mo", "1y", "2y"]).pack(side="left", padx=(6, 16))

        tk.Button(inner, text="RUN BACKTEST", font=self.f_head,
                  bg=GREEN, fg="#000000", relief="flat", cursor="hand2",
                  padx=16, pady=6, command=self._run_backtest).pack(side="right")

        summary = tk.Frame(parent, bg=BG)
        summary.pack(fill="x", padx=12, pady=(0, 8))
        self.backtest_cards = {}
        for title in ["EST. TOTAL P/L", "WIN RATE", "AVG TRADE RETURN", "MAX DRAWDOWN"]:
            card = tk.Frame(summary, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=4)
            tk.Label(card, text=title, font=self.f_small, bg=CARD, fg=TEXT3).pack(anchor="w", padx=12, pady=(10, 2))
            val = tk.Label(card, text="?", font=self.f_head, bg=CARD, fg=TEXT)
            val.pack(anchor="w", padx=12, pady=(0, 10))
            self.backtest_cards[title] = val

        table_wrap = tk.Frame(parent, bg=BG)
        table_wrap.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        hdr = tk.Frame(table_wrap, bg=BG3)
        hdr.pack(fill="x")
        headers = [("TRADE", 6), ("DATES", 22), ("SETUP", 18), ("ENTRY/EXIT", 18), ("P/L", 10), ("RETURN", 10), ("RESULT", 10)]
        for h, w in headers:
            tk.Label(hdr, text=h, font=self.f_small, bg=BG3, fg=TEXT3,
                     width=w, anchor="w").pack(side="left", padx=5, pady=6)

        self.backtest_table = tk.Frame(table_wrap, bg=BG)
        self.backtest_table.pack(fill="both", expand=True)
        tk.Label(self.backtest_table, text="Run a backtest to see historical trade results.",
                 font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)

    def _run_backtest(self):
        ticker = self.backtest_ticker.get().strip().upper()
        strategy = self.backtest_strategy.get().strip()
        period = self.backtest_period.get().strip()
        self.backtest_status.config(text=f"Running {strategy} backtest for {ticker} over {period}...", fg=YELLOW)
        self.after(10, lambda: self._finish_backtest(ticker, strategy, period))

    def _finish_backtest(self, ticker, strategy, period):
        results = backtest_strategy(ticker, strategy, period=period)
        self.backtest_results = results
        self._render_backtest_results()

    def _render_backtest_results(self):
        for w in self.backtest_table.winfo_children():
            w.destroy()

        if not self.backtest_results:
            self.backtest_status.config(text="Backtest failed. Check ticker/data availability.", fg=RED)
            for val in self.backtest_cards.values():
                val.config(text="?", fg=TEXT)
            self.backtest_explainer.config(
                text="No results were generated. Try a liquid ticker and a longer lookback like 1Y or 2Y.",
                fg=TEXT3
            )
            tk.Label(self.backtest_table, text="No backtest results available.",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)
            return

        r = self.backtest_results
        self.backtest_status.config(
            text=f"{r['ticker']} {r['strategy']} backtest complete - {r['trade_count']} simulated trades",
            fg=GREEN
        )
        self.backtest_explainer.config(
            text=(
                f"Showing estimated {r['strategy']} trades for {r['ticker']} from "
                f"{r['first_trade'].strftime('%b %d, %Y')} to {r['last_trade'].strftime('%b %d, %Y')}. "
                "Each row is one simulated weekly trade: entry date, exit date, setup used, dollars made or lost, and percent return."
            ),
            fg=TEXT2
        )
        self.backtest_cards["EST. TOTAL P/L"].config(text=f"${r['total_pnl']:,.0f}", fg=GREEN if r["total_pnl"] >= 0 else RED)
        self.backtest_cards["WIN RATE"].config(text=f"{r['win_rate'] * 100:.1f}%", fg=TEXT)
        self.backtest_cards["AVG TRADE RETURN"].config(text=f"{r['avg_return']:.2f}%", fg=TEXT)
        self.backtest_cards["MAX DRAWDOWN"].config(text=f"{r['max_drawdown'] * 100:.1f}%", fg=RED if r["max_drawdown"] > 0.15 else YELLOW)

        for idx, row in enumerate(r["trades"], start=1):
            bg_c = CARD if idx % 2 else BG2
            line = tk.Frame(self.backtest_table, bg=bg_c, highlightbackground=BORDER, highlightthickness=1)
            line.pack(fill="x", pady=1)
            vals = [
                str(idx),
                f"{row['entry_date']:%b %d} -> {row['exit_date']:%b %d}",
                row["label"],
                f"${row['entry_price']:.2f} -> ${row['exit_price']:.2f}",
                f"${row['pnl']:.0f}",
                f"{row['return_pct']:.2f}%",
                "WIN" if row["win"] else "LOSS" if not row["assigned"] else "ASSIGNED/LOSS",
            ]
            widths = [6, 22, 18, 18, 10, 10, 10]
            for i, (val, w) in enumerate(zip(vals, widths)):
                fg = GREEN if i == 6 and row["win"] else RED if i == 6 else TEXT
                tk.Label(line, text=val, font=self.f_mono_s, bg=bg_c, fg=fg,
                         width=w, anchor="w").pack(side="left", padx=5, pady=8)

    def _build_patterns(self, parent):
        self.pattern_results = []
        self.pattern_collapsed = {}

        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(top, text="Pattern Detector",
                 font=self.f_head, bg=BG, fg=TEXT).pack(side="left")

        self.pattern_status = tk.Label(
            top,
            text="Scan chart patterns plus moving-average forecast, mean reversion, ATR range, and ML-style directional models.",
            font=self.f_small, bg=BG, fg=TEXT2
        )
        self.pattern_status.pack(side="left", padx=16)

        tk.Button(top, text="SCAN PATTERNS", font=self.f_head,
                  bg=ACCENT, fg=WHITE, relief="flat", cursor="hand2",
                  padx=16, pady=6,
                  command=self._run_pattern_scan).pack(side="right")

        explainer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        explainer.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(
            explainer,
            text=(
                "Pattern signals are heuristic, not guarantees. Use them with trend, volume, RSI, and broader market context. "
                "Confidence is a practical score based on how closely the recent price action matches each pattern or model."
            ),
            font=self.f_small, bg=CARD, fg=TEXT2, wraplength=1050, justify="left"
        ).pack(anchor="w", padx=12, pady=(10, 10))
        tk.Label(
            explainer,
            text=(
                "How to use this: Level is the trigger price or reference value to watch. "
                "Prediction is the expected move if the setup confirms. "
                "ML Forecast is a lightweight directional model, Mean Reversion looks for RSI extremes, "
                "ATR Range estimates expected movement size, News Sentiment scores recent headlines, and Unusual Options Activity is a proxy from option-chain volume."
            ),
            font=self.f_small, bg=CARD, fg=YELLOW, wraplength=1050, justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 10))

        table = tk.Frame(parent, bg=BG)
        table.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        hdr = tk.Frame(table, bg=BG3)
        hdr.pack(fill="x")
        headers = [("TICKER", 8), ("PATTERN", 20), ("BIAS", 10), ("CONF", 8), ("LEVEL", 10), ("PREDICTION", 36)]
        for h, w in headers:
            tk.Label(hdr, text=h, font=self.f_small, bg=BG3, fg=TEXT3,
                     width=w, anchor="w").pack(side="left", padx=5, pady=6)

        pattern_scroll_frame = tk.Frame(table, bg=BG)
        pattern_scroll_frame.pack(fill="both", expand=True)
        self.pattern_canvas = tk.Canvas(pattern_scroll_frame, bg=BG, highlightthickness=0)
        pattern_sb = ttk.Scrollbar(pattern_scroll_frame, orient="vertical", command=self.pattern_canvas.yview)
        pattern_sb.pack(side="right", fill="y")
        self.pattern_canvas.pack(fill="both", expand=True)
        self.pattern_canvas.configure(yscrollcommand=pattern_sb.set)
        self.pattern_table = tk.Frame(self.pattern_canvas, bg=BG)
        self.pattern_canvas.create_window((0, 0), window=self.pattern_table, anchor="nw")
        self.pattern_table.bind("<Configure>", lambda e: self.pattern_canvas.configure(
            scrollregion=self.pattern_canvas.bbox("all")))
        tk.Label(self.pattern_table, text="Press SCAN PATTERNS to detect chart and statistical setups.",
                 font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)

    def _run_pattern_scan(self):
        self.pattern_status.config(text="Scanning chart, statistical, options, and ML-style signals...", fg=YELLOW)
        self.after(10, self._finish_pattern_scan)

    def _finish_pattern_scan(self):
        symbols = []
        for ticker in list(PORTFOLIO.keys()) + list(SCAN_UNIVERSE):
            if ticker not in symbols:
                symbols.append(ticker)

        results = []
        for idx, ticker in enumerate(symbols):
            self.pattern_status.config(text=f"Scanning {idx + 1}/{len(symbols)}: {ticker}...", fg=YELLOW)
            data = fetch_scan_data(ticker, period="1y")
            if not data:
                continue
            for pattern in detect_patterns(data["closes"]):
                row = {"ticker": ticker}
                row.update(pattern)
                results.append(row)
            for signal in detect_statistical_signals(data["closes"], data["highs"], data["lows"]):
                row = {"ticker": ticker}
                row.update(signal)
                results.append(row)
            for signal in detect_ml_forecast_signal(data["closes"], data["highs"], data["lows"]):
                row = {"ticker": ticker}
                row.update(signal)
                results.append(row)
            for signal in detect_options_flow_signal(ticker):
                row = {"ticker": ticker}
                row.update(signal)
                results.append(row)
            for signal in detect_news_sentiment_signal(ticker):
                row = {"ticker": ticker}
                row.update(signal)
                results.append(row)

        self.pattern_results = sorted(results, key=lambda r: (r["ticker"], -r["confidence"], r["name"]))
        self.pattern_collapsed = {ticker: True for ticker in {row["ticker"] for row in self.pattern_results}}
        self._render_pattern_results()

    def _render_pattern_results(self):
        for w in self.pattern_table.winfo_children():
            w.destroy()

        if not self.pattern_results:
            self.pattern_status.config(text="No patterns found. Check data availability.", fg=RED)
            tk.Label(self.pattern_table, text="No pattern results available.",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)
            return

        self.pattern_status.config(text=f"Pattern scan complete - {len(self.pattern_results)} signals ranked", fg=GREEN)
        grouped = {}
        for row in self.pattern_results[:60]:
            grouped.setdefault(row["ticker"], []).append(row)

        for ticker in sorted(grouped.keys()):
            rows = grouped[ticker]
            self.pattern_collapsed.setdefault(ticker, False)
            top_signal = rows[0]
            scorecard = score_ticker_signal_set(rows)
            bias_color = GREEN if top_signal["bias"] == "Bullish" else RED if top_signal["bias"] == "Bearish" else YELLOW

            header = tk.Frame(self.pattern_table, bg=BG3, highlightbackground=BORDER, highlightthickness=1)
            header.pack(fill="x", pady=(4, 1))
            toggle_text = "+" if self.pattern_collapsed[ticker] else "-"
            tk.Button(
                header,
                text=toggle_text,
                font=self.f_small,
                bg=BG3,
                fg=TEXT,
                relief="flat",
                cursor="hand2",
                width=2,
                command=lambda t=ticker: self._toggle_pattern_ticker(t),
            ).pack(side="left", padx=(6, 8), pady=6)
            tk.Label(header, text=ticker, font=self.f_mono, bg=BG3, fg=TEXT, width=8, anchor="w").pack(side="left", padx=5)
            tk.Label(header, text=top_signal["name"], font=self.f_small, bg=BG3, fg=TEXT2, width=20, anchor="w").pack(side="left", padx=5)
            tk.Label(header, text=top_signal["bias"], font=self.f_small, bg=BG3, fg=bias_color, width=10, anchor="w").pack(side="left", padx=5)
            tk.Label(header, text=f"{len(rows)} signals", font=self.f_small, bg=BG3, fg=ACCENT2, width=10, anchor="w").pack(side="left", padx=5)
            tk.Label(header, text=f"Tech {scorecard['technical']:.1f}/10", font=self.f_small, bg=BG3, fg=TEXT, width=13, anchor="w").pack(side="left", padx=5)
            tk.Label(header, text=f"Sent {scorecard['sentiment']:.1f}/10", font=self.f_small, bg=BG3, fg=TEXT, width=13, anchor="w").pack(side="left", padx=5)
            tk.Label(header, text=f"{scorecard['signal']} {scorecard['combined']:.1f}/10", font=self.f_small, bg=BG3, fg=scorecard["color"], width=18, anchor="w").pack(side="left", padx=5)

            if self.pattern_collapsed[ticker]:
                continue

            for idx, row in enumerate(rows, start=1):
                bg_c = CARD if idx % 2 else BG2
                line = tk.Frame(self.pattern_table, bg=bg_c, highlightbackground=BORDER, highlightthickness=1)
                line.pack(fill="x", pady=1)
                row_bias_color = GREEN if row["bias"] == "Bullish" else RED if row["bias"] == "Bearish" else YELLOW
                vals = [
                    "",
                    row["name"],
                    row["bias"],
                    f"{row['confidence']}",
                    f"{row['level']:.2f}x" if row["name"] == "Unusual Options Activity" else (
                        f"{int(row['level'])} news" if row["name"] == "News Sentiment" else f"${row['level']:.2f}"
                    ),
                    row["prediction"],
                ]
                widths = [8, 20, 10, 8, 10, 36]
                for i, (val, w) in enumerate(zip(vals, widths)):
                    fg = row_bias_color if i == 2 else ACCENT2 if i == 3 else TEXT
                    tk.Label(line, text=val, font=self.f_mono_s if i < 5 else self.f_small,
                             bg=bg_c, fg=fg, width=w, anchor="w").pack(side="left", padx=5, pady=8)

    def _toggle_pattern_ticker(self, ticker):
        self.pattern_collapsed[ticker] = not self.pattern_collapsed.get(ticker, False)
        self._render_pattern_results()

    def _build_ai_themes(self, parent):
        self.ai_sector_tables = {}

        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(top, text="AI Next-Wave Themes", font=self.f_head, bg=BG, fg=TEXT).pack(side="left")
        self.ai_status = tk.Label(top, text="Tracking 20 names across 4 AI themes.",
                                  font=self.f_small, bg=BG, fg=TEXT2)
        self.ai_status.pack(side="left", padx=16)

        grid = tk.Frame(parent, bg=BG)
        grid.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        for idx, (sector, cfg) in enumerate(AI_THEMES.items()):
            row_i, col_i = divmod(idx, 2)
            card = tk.Frame(grid, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=row_i, column=col_i, sticky="nsew", padx=4, pady=4)
            grid.rowconfigure(row_i, weight=1)

            head = tk.Frame(card, bg=BG3, padx=10, pady=6)
            head.pack(fill="x")
            dot = tk.Label(head, text="●", font=self.f_body, bg=BG3, fg=cfg["color"])
            dot.pack(side="left")
            tk.Label(head, text=f"  {sector}", font=self.f_head, bg=BG3, fg=TEXT).pack(side="left")
            tk.Label(head, text=cfg["note"], font=self.f_small, bg=BG3, fg=TEXT2).pack(side="right")

            hdr = tk.Frame(card, bg=BG2, padx=6, pady=4)
            hdr.pack(fill="x")
            for label, width, anchor in [
                ("TICKER", 8, "w"), ("PRICE", 10, "e"), ("CHG%", 8, "e"),
                ("RSI", 6, "e"), ("SIGNAL", 12, "w"),
            ]:
                tk.Label(hdr, text=label, font=self.f_small, bg=BG2, fg=TEXT3,
                         width=width, anchor=anchor).pack(side="left", padx=4)

            table = tk.Frame(card, bg=CARD)
            table.pack(fill="both", expand=True)
            self.ai_sector_tables[sector] = table

            tk.Label(table, text="Loading...", font=self.f_small, bg=CARD, fg=TEXT3).pack(pady=16)

    def _render_ai_themes(self):
        if not hasattr(self, "ai_sector_tables"):
            return
        any_data = False
        for sector, cfg in AI_THEMES.items():
            table = self.ai_sector_tables[sector]
            for w in table.winfo_children():
                w.destroy()

            for i, ticker in enumerate(cfg["tickers"]):
                d = self.stock_data.get(ticker)
                if not d or not d.get("price"):
                    row = tk.Frame(table, bg=BG2 if i % 2 else CARD)
                    row.pack(fill="x")
                    tk.Label(row, text=ticker, font=self.f_mono_s, bg=row["bg"],
                             fg=TEXT3, width=8, anchor="w").pack(side="left", padx=6, pady=6)
                    tk.Label(row, text="—", font=self.f_mono_s, bg=row["bg"],
                             fg=TEXT3).pack(side="left", padx=4)
                    continue

                any_data = True
                price = d["price"]
                pct   = d["pct"]
                hist  = self.history_data.get(ticker, [])
                rsi   = calc_rsi(hist) if hist else 50
                ma50  = calc_ma(hist, 50)
                ma200 = calc_ma(hist, 200)
                sig, sig_color, _ = get_signal(price, rsi, ma50 or price, ma200 or price)

                bg_c    = BG2 if i % 2 else CARD
                chg_col = GREEN if pct >= 0 else RED
                rsi_col = GREEN if rsi < 35 else RED if rsi > 65 else TEXT2

                row = tk.Frame(table, bg=bg_c, cursor="hand2")
                row.pack(fill="x")
                row.bind("<Button-1>", lambda e, t=ticker: self._jump_to_mover_ticker(t))

                vals = [
                    (ticker,           8,  "w", TEXT,    self.f_mono_s),
                    (f"${price:.2f}",  10, "e", TEXT,    self.f_mono_s),
                    (f"{pct:+.2f}%",   8,  "e", chg_col, self.f_mono_s),
                    (str(int(rsi)),    6,  "e", rsi_col, self.f_mono_s),
                    (sig,              12, "w", sig_color, self.f_small),
                ]
                for text, width, anchor, fg, font in vals:
                    lbl = tk.Label(row, text=text, font=font, bg=bg_c, fg=fg,
                                   width=width, anchor=anchor)
                    lbl.pack(side="left", padx=4, pady=6)
                    lbl.bind("<Button-1>", lambda e, t=ticker: self._jump_to_mover_ticker(t))

        if any_data:
            self.ai_status.config(text=f"Tracking {len(AI_THEME_TICKERS)} names across {len(AI_THEMES)} AI themes.", fg=GREEN)

    def _build_movers(self, parent):
        self.movers_universe = sorted(set(list(PORTFOLIO.keys()) + list(ETF_SYMBOLS) + list(SCAN_UNIVERSE)))

        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))
        tk.Label(top, text="Biggest Gainers & Losers",
                 font=self.f_head, bg=BG, fg=TEXT).pack(side="left")
        self.movers_status = tk.Label(
            top,
            text=f"Tracking {len(self.movers_universe)} names across portfolio, ETFs, and scan universe.",
            font=self.f_small, bg=BG, fg=TEXT2
        )
        self.movers_status.pack(side="left", padx=16)

        split = tk.Frame(parent, bg=BG)
        split.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        gainers = tk.Frame(split, bg=BG)
        gainers.pack(side="left", fill="both", expand=True, padx=(0, 4))
        tk.Label(gainers, text="BIGGEST GAINERS", font=self.f_head, bg=BG, fg=GREEN).pack(anchor="w", pady=(0, 6))
        gain_hdr = tk.Frame(gainers, bg=BG3)
        gain_hdr.pack(fill="x")
        for h, w in [("TICKER", 9), ("PRICE", 9), ("CHANGE", 9), ("%", 8), ("TODAY VOL", 12)]:
            tk.Label(gain_hdr, text=h, font=self.f_small, bg=BG3, fg=TEXT3,
                     width=w, anchor="w").pack(side="left", padx=5, pady=6)
        self.gainers_table = tk.Frame(gainers, bg=BG)
        self.gainers_table.pack(fill="both", expand=True)

        losers = tk.Frame(split, bg=BG)
        losers.pack(side="left", fill="both", expand=True, padx=(4, 4))
        tk.Label(losers, text="BIGGEST LOSERS", font=self.f_head, bg=BG, fg=RED).pack(anchor="w", pady=(0, 6))
        loss_hdr = tk.Frame(losers, bg=BG3)
        loss_hdr.pack(fill="x")
        for h, w in [("TICKER", 9), ("PRICE", 9), ("CHANGE", 9), ("%", 8), ("TODAY VOL", 12)]:
            tk.Label(loss_hdr, text=h, font=self.f_small, bg=BG3, fg=TEXT3,
                     width=w, anchor="w").pack(side="left", padx=5, pady=6)
        self.losers_table = tk.Frame(losers, bg=BG)
        self.losers_table.pack(fill="both", expand=True)

        volume = tk.Frame(split, bg=BG)
        volume.pack(side="left", fill="both", expand=True, padx=(4, 0))
        tk.Label(volume, text="TOP VOLUME MOVERS", font=self.f_head, bg=BG, fg=ACCENT2).pack(anchor="w", pady=(0, 6))
        vol_hdr = tk.Frame(volume, bg=BG3)
        vol_hdr.pack(fill="x")
        for h, w in [("TICKER", 9), ("PRICE", 9), ("CHANGE", 9), ("%", 8), ("TODAY VOL", 12)]:
            tk.Label(vol_hdr, text=h, font=self.f_small, bg=BG3, fg=TEXT3,
                     width=w, anchor="w").pack(side="left", padx=5, pady=6)
        self.volume_table = tk.Frame(volume, bg=BG)
        self.volume_table.pack(fill="both", expand=True)

        tk.Label(self.gainers_table, text="Refreshing movers with market data...",
                 font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)
        tk.Label(self.losers_table, text="Refreshing movers with market data...",
                 font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)
        tk.Label(self.volume_table, text="Refreshing movers with market data...",
                 font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)

    def _render_movers(self):
        if not hasattr(self, "gainers_table"):
            return
        for w in self.gainers_table.winfo_children():
            w.destroy()
        for w in self.losers_table.winfo_children():
            w.destroy()
        for w in self.volume_table.winfo_children():
            w.destroy()

        universe_data = []
        for ticker in self.movers_universe:
            d = self.stock_data.get(ticker)
            if d and d.get("price"):
                universe_data.append((ticker, d))

        if not universe_data:
            self.movers_status.config(text="No mover data available yet.", fg=RED)
            tk.Label(self.gainers_table, text="No mover data available.",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)
            tk.Label(self.losers_table, text="No mover data available.",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)
            tk.Label(self.volume_table, text="No mover data available.",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)
            return

        gainers = sorted(universe_data, key=lambda x: x[1].get("pct", 0), reverse=True)[:10]
        losers = sorted(universe_data, key=lambda x: x[1].get("pct", 0))[:10]
        top_volume = sorted(universe_data, key=lambda x: x[1].get("volume", 0), reverse=True)[:10]
        self.movers_status.config(text=f"Showing movers from {len(universe_data)} tracked names.", fg=GREEN)

        def render_rows(parent, rows, color):
            for idx, (ticker, d) in enumerate(rows, start=1):
                bg_c = CARD if idx % 2 else BG2
                row = tk.Frame(parent, bg=bg_c, highlightbackground=BORDER, highlightthickness=1, cursor="hand2")
                row.pack(fill="x", pady=1)
                vals = [
                    ticker,
                    f"${d.get('price', 0):.2f}",
                    f"{d.get('change', 0):+.2f}",
                    f"{d.get('pct', 0):+.2f}%",
                    f"{int(d.get('volume', 0)):,}",
                ]
                widths = [9, 9, 9, 8, 12]
                for i, (val, w) in enumerate(zip(vals, widths)):
                    fg = color if i in (2, 3) else TEXT
                    lbl = tk.Label(row, text=val, font=self.f_mono_s, bg=bg_c, fg=fg,
                                   width=w, anchor="w")
                    lbl.pack(side="left", padx=5, pady=8)
                    lbl.bind("<Button-1>", lambda e, t=ticker: self._jump_to_mover_ticker(t))
                row.bind("<Button-1>", lambda e, t=ticker: self._jump_to_mover_ticker(t))

        render_rows(self.gainers_table, gainers, GREEN)
        render_rows(self.losers_table, losers, RED)
        render_rows(self.volume_table, top_volume, ACCENT2)

    def _jump_to_mover_ticker(self, ticker):
        self._select_ticker(ticker)
        if hasattr(self, "chart_ticker_var"):
            self.chart_ticker_var.set(ticker)
            self._update_chart()

    def _build_spmo(self, parent):
        self.spmo_running = False

        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=12, pady=(12, 6))

        tk.Label(top, text="SPMO Strategy - Momentum Buy/Sell",
                 font=self.f_head, bg=BG, fg=TEXT).pack(side="left")

        self.spmo_status = tk.Label(
            top,
            text=f"Press Refresh to build {MOMENTUM_REBALANCE} SPMO-style buy/sell list",
            font=self.f_small, bg=BG, fg=TEXT2
        )
        self.spmo_status.pack(side="left", padx=16)

        tk.Button(top, text="REFRESH SIGNALS", font=self.f_head,
                  bg=ACCENT, fg=WHITE, relief="flat", cursor="hand2",
                  padx=16, pady=6,
                  command=self._run_spmo_strategy).pack(side="right")

        explainer = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        explainer.pack(fill="x", padx=12, pady=(0, 8))
        tk.Label(
            explainer,
            text=(
                "SPMO-inspired model: rank high-momentum S&P 500 names by "
                "12-month return excluding the latest month, adjusted for volatility. "
                "This app refreshes that list daily/weekly for active trading signals."
            ),
            font=self.f_small, bg=CARD, fg=TEXT2, wraplength=1050, justify="left"
        ).pack(anchor="w", padx=12, pady=(10, 4))
        tk.Label(
            explainer,
            text=(
                f"Target: seek 40% annual growth plus income opportunities. "
                "Signals are decision support, not a guarantee."
            ),
            font=self.f_small, bg=CARD, fg=YELLOW, wraplength=1050, justify="left"
        ).pack(anchor="w", padx=12, pady=(0, 10))

        table = tk.Frame(parent, bg=BG)
        table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        headers = ["RANK", "TICKER", "ACTION", "PRICE", "MOM SCORE", "RSI", "TREND", "5D MOM", "INCOME IDEA"]
        widths = [6, 8, 10, 10, 11, 7, 12, 9, 24]
        hdr = tk.Frame(table, bg=BG3)
        hdr.pack(fill="x")
        for h, w in zip(headers, widths):
            tk.Label(hdr, text=h, font=self.f_small, bg=BG3, fg=TEXT3,
                     width=w, anchor="w").pack(side="left", padx=5, pady=6)

        self.spmo_table = tk.Frame(table, bg=BG)
        self.spmo_table.pack(fill="both", expand=True)

        tk.Label(self.spmo_table, text="Press REFRESH SIGNALS to generate buy/sell candidates.",
                 font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)

    def _run_spmo_strategy(self):
        if self.spmo_running:
            return
        self.spmo_running = True
        self.spmo_status.config(text="Rebalancing SPMO-style universe and building signals...", fg=YELLOW)
        threading.Thread(target=self._spmo_strategy_thread, daemon=True).start()

    def _spmo_strategy_thread(self):
        symbols = get_rebalanced_scan_universe()
        rows = []
        for i, ticker in enumerate(symbols):
            self.after(0, lambda t=ticker, i=i: self.spmo_status.config(
                text=f"Scoring {i+1}/{len(symbols)}: {t}...", fg=YELLOW))
            data = fetch_scan_data(ticker, period="15mo")
            if not data:
                continue
            closes = data["closes"]
            price = data["price"]
            score = momentum_score_from_closes(closes)
            rsi = calc_rsi(closes)
            ma50 = calc_ma(closes, 50)
            ma200 = calc_ma(closes, min(200, len(closes)))
            mom5 = ((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) >= 6 and closes[-6] else 0
            above_50 = price > ma50 if ma50 else False
            above_200 = price > ma200 if ma200 else False

            if score is None:
                continue
            if score > 0.8 and above_50 and above_200 and rsi < 72:
                action = "BUY"
                color = GREEN
                income = "Hold shares; sell covered calls on strength"
            elif score < 0.25 or not above_50 or rsi > 78:
                action = "SELL/TRIM"
                color = RED
                income = "Reduce exposure; wait for reset"
            else:
                action = "HOLD"
                color = YELLOW
                income = "Use smaller position or cash-secured puts"

            rows.append({
                "ticker": ticker, "action": action, "color": color,
                "price": price, "score": score, "rsi": rsi,
                "trend": "Above 50/200" if above_50 and above_200 else "Weakening",
                "mom5": mom5, "income": income,
            })
            time.sleep(0.15)

        rows.sort(key=lambda r: r["score"], reverse=True)
        self.spmo_running = False
        self.after(0, lambda: self._render_spmo_strategy(rows))

    def _render_spmo_strategy(self, rows):
        for w in self.spmo_table.winfo_children():
            w.destroy()

        if not rows:
            self.spmo_status.config(text="No SPMO signals available. Check data source/yfinance.", fg=RED)
            tk.Label(self.spmo_table, text="No data available.",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=24)
            return

        widths = [6, 8, 10, 10, 11, 7, 12, 9, 24]
        for rank, r in enumerate(rows, start=1):
            bg_c = CARD if rank % 2 else BG2
            row = tk.Frame(self.spmo_table, bg=bg_c, highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill="x", pady=1)
            vals = [
                str(rank),
                r["ticker"],
                r["action"],
                f"${r['price']:.2f}",
                f"{r['score']:.2f}",
                f"{r['rsi']:.0f}",
                r["trend"],
                f"{r['mom5']:.1f}%",
                r["income"],
            ]
            for idx, (val, w) in enumerate(zip(vals, widths)):
                fg = r["color"] if idx == 2 else TEXT
                tk.Label(row, text=val, font=self.f_mono_s if idx < 8 else self.f_small,
                         bg=bg_c, fg=fg, width=w, anchor="w").pack(side="left", padx=5, pady=8)

        buys = sum(1 for r in rows if r["action"] == "BUY")
        trims = sum(1 for r in rows if r["action"] == "SELL/TRIM")
        self.spmo_status.config(
            text=f"{MOMENTUM_REBALANCE.title()} SPMO strategy ready: {buys} buys, {trims} trims, {len(rows)} ranked",
            fg=GREEN
        )

    def _build_scanner(self, parent):
        self.scanner_results = []
        self.scanner_running = False
        self.scanner_auto_refresh = tk.BooleanVar(value=False)
        self.scanner_auto_interval = tk.IntVar(value=5)
        self.last_scanner_run_ts = 0.0

        # ── Top bar ──
        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x", padx=12, pady=(12,6))

        tk.Label(top, text="📡 Spread Scanner", font=self.f_head,
                 bg=BG, fg=TEXT).pack(side="left")

        self.scan_status = tk.Label(top, text="Press Scan to find best setups",
                                    font=self.f_small, bg=BG, fg=TEXT2)
        self.scan_status.pack(side="left", padx=16)

        tk.Button(top, text="▶  SCAN NOW", font=self.f_head,
                  bg=GREEN, fg="#000000", relief="flat", cursor="hand2",
                  padx=16, pady=6,
                  command=self._run_scanner).pack(side="right")

        # ── Filter bar ──
        filt = tk.Frame(parent, bg=BG2,
                        highlightbackground=BORDER, highlightthickness=1)
        filt.pack(fill="x", padx=12, pady=(0,8))
        fi = tk.Frame(filt, bg=BG2, padx=12, pady=8)
        fi.pack(fill="x")

        tk.Label(fi, text="Show:", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left")
        self.scan_filter = tk.StringVar(value="ALL")
        for val, lbl in [("ALL","All"), ("BULL","🟢 Bullish Only"), ("BEAR","🔴 Bearish Only")]:
            tk.Radiobutton(fi, text=lbl, variable=self.scan_filter, value=val,
                           command=self._render_scanner_results,
                           bg=BG2, fg=TEXT2, selectcolor=ACCENT,
                           activebackground=BG2, font=self.f_small,
                           relief="flat", cursor="hand2").pack(side="left", padx=10)

        tk.Label(fi, text="  Min Score:", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left", padx=(16,4))
        self.min_score = tk.IntVar(value=60)
        tk.Scale(fi, from_=40, to=90, orient="horizontal", variable=self.min_score,
                 bg=BG2, fg=TEXT2, highlightthickness=0, troughcolor=BG3,
                 command=lambda e: self._render_scanner_results(),
                 length=120, sliderrelief="flat").pack(side="left")
        self.min_score_lbl = tk.Label(fi, text="60", font=self.f_mono_s, bg=BG2, fg=ACCENT)
        self.min_score_lbl.pack(side="left", padx=4)
        self.min_score.trace_add("write", lambda *a: self.min_score_lbl.config(
            text=str(self.min_score.get())))

        tk.Label(fi, text="  Expiry:", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left", padx=(16,4))
        self.scan_expiry = tk.StringVar(value=next_dte_expiry(14).strftime("%Y-%m-%d"))
        tk.Entry(fi, textvariable=self.scan_expiry, font=self.f_mono_s, width=12,
                 bg=BG3, fg=TEXT, insertbackground=TEXT,
                 relief="flat").pack(side="left")
        tk.Label(fi, text="Fixed at 14 DTE", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left", padx=(4,0))

        tk.Checkbutton(fi, text="Auto Refresh", variable=self.scanner_auto_refresh,
                       bg=BG2, fg=TEXT2, selectcolor=ACCENT, activebackground=BG2,
                       font=self.f_small, relief="flat", cursor="hand2").pack(side="left", padx=(16, 4))
        tk.Label(fi, text="Every", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left", padx=(6, 4))
        ttk.Combobox(fi, textvariable=self.scanner_auto_interval, width=4, state="readonly",
                     values=[1, 3, 5, 10, 15]).pack(side="left")
        tk.Label(fi, text="min", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left", padx=(4, 0))

        # ── Split view: Bullish left, Bearish right ──
        split = tk.Frame(parent, bg=BG)
        split.pack(fill="both", expand=True, padx=12, pady=(0,12))

        # Bullish panel
        bull_frame = tk.Frame(split, bg=BG)
        bull_frame.pack(side="left", fill="both", expand=True, padx=(0,4))
        tk.Label(bull_frame, text="🟢  BULLISH SPREADS",
                 font=self.f_head, bg=BG, fg=GREEN).pack(anchor="w", pady=(0,6))

        bull_hdr = tk.Frame(bull_frame, bg=BG3)
        bull_hdr.pack(fill="x")
        for h, w in [("TYPE",10),("TICKER",6),("PRICE",8),("BUY",6),("SELL",6),
                     ("14D EXP",10),("ENTRY",7),("MAX P/L",10),("R:R",5),("RISK",7),("RSI",5)]:
            tk.Label(bull_hdr, text=h, font=self.f_small, bg=BG3,
                     fg=TEXT3, width=w, anchor="w").pack(side="left", padx=4, pady=5)

        bull_scroll_frame = tk.Frame(bull_frame, bg=BG)
        bull_scroll_frame.pack(fill="both", expand=True)
        bull_canvas = tk.Canvas(bull_scroll_frame, bg=BG, highlightthickness=0)
        bull_sb = ttk.Scrollbar(bull_scroll_frame, orient="vertical",
                                command=bull_canvas.yview)
        bull_sb.pack(side="right", fill="y")
        bull_canvas.pack(fill="both", expand=True)
        bull_canvas.configure(yscrollcommand=bull_sb.set)
        self.bull_inner = tk.Frame(bull_canvas, bg=BG)
        bull_canvas.create_window((0,0), window=self.bull_inner, anchor="nw")
        self.bull_inner.bind("<Configure>", lambda e: bull_canvas.configure(
            scrollregion=bull_canvas.bbox("all")))
        self.bull_canvas_ref = bull_canvas

        # Bearish panel
        bear_frame = tk.Frame(split, bg=BG)
        bear_frame.pack(side="left", fill="both", expand=True, padx=(4,0))
        tk.Label(bear_frame, text="🔴  BEAR PUT SPREADS",
                 font=self.f_head, bg=BG, fg=RED).pack(anchor="w", pady=(0,6))

        bear_hdr = tk.Frame(bear_frame, bg=BG3)
        bear_hdr.pack(fill="x")
        for h, w in [("TICKER",6),("PRICE",8),("BUY",6),("SELL",6),
                     ("14D EXP",10),("DEBIT",7),("MAX PROFIT",10),("R:R",5),("RISK",7),("RSI",5)]:
            tk.Label(bear_hdr, text=h, font=self.f_small, bg=BG3,
                     fg=TEXT3, width=w, anchor="w").pack(side="left", padx=4, pady=5)

        bear_scroll_frame = tk.Frame(bear_frame, bg=BG)
        bear_scroll_frame.pack(fill="both", expand=True)
        bear_canvas = tk.Canvas(bear_scroll_frame, bg=BG, highlightthickness=0)
        bear_sb = ttk.Scrollbar(bear_scroll_frame, orient="vertical",
                                command=bear_canvas.yview)
        bear_sb.pack(side="right", fill="y")
        bear_canvas.pack(fill="both", expand=True)
        bear_canvas.configure(yscrollcommand=bear_sb.set)
        self.bear_inner = tk.Frame(bear_canvas, bg=BG)
        bear_canvas.create_window((0,0), window=self.bear_inner, anchor="nw")
        self.bear_inner.bind("<Configure>", lambda e: bear_canvas.configure(
            scrollregion=bear_canvas.bbox("all")))
        self.bear_canvas_ref = bear_canvas

    def _run_scanner(self):
        if self.scanner_running:
            return
        expiry_date = next_dte_expiry(14)
        self.scan_expiry.set(expiry_date.strftime("%Y-%m-%d"))
        self.scanner_running = True
        self.last_scanner_run_ts = time.time()
        self.scan_status.config(text="Rebalancing SPMO-style momentum universe...", fg=YELLOW)
        self.scan_status.config(
            text=f"Building {MOMENTUM_REBALANCE} momentum list for fixed 14-day expiry {expiry_date:%Y-%m-%d}...",
            fg=YELLOW
        )
        threading.Thread(target=self._scanner_thread, args=(expiry_date,), daemon=True).start()

    def _maybe_auto_refresh_scanner(self):
        if not hasattr(self, "scanner_auto_refresh") or not self.scanner_auto_refresh.get():
            return
        if self.scanner_running:
            return
        interval_sec = max(self.scanner_auto_interval.get(), 1) * 60
        if time.time() - self.last_scanner_run_ts >= interval_sec:
            self.after(0, self._run_scanner)

    def _scanner_thread(self, expiry_date):
        results = []
        scan_universe = get_rebalanced_scan_universe()
        for i, ticker in enumerate(scan_universe):
            self.after(0, lambda t=ticker, i=i: self.scan_status.config(
                text=f"⟳ Scanning {i+1}/{len(scan_universe)}: {t}...", fg=YELLOW))
            data = fetch_scan_data(ticker)
            if data:
                scored = score_for_spreads(
                    ticker, data["closes"], data["highs"],
                    data["lows"], data["price"], data["change_pct"], expiry_date
                )
                if scored:
                    results.append(scored)
            time.sleep(0.3)  # Polite rate limiting

        self.scanner_results = results
        self.scanner_running = False
        self.after(0, lambda: self.scan_status.config(
            text=f"✅ {MOMENTUM_REBALANCE.title()} SPMO-style scan complete — {len(results)} stocks analyzed", fg=GREEN))
        self.after(0, self._render_scanner_results)

    def _render_scanner_results(self):
        # Clear panels
        for w in self.bull_inner.winfo_children(): w.destroy()
        for w in self.bear_inner.winfo_children(): w.destroy()

        if not self.scanner_results:
            tk.Label(self.bull_inner, text="Press SCAN NOW to find setups",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=20)
            tk.Label(self.bear_inner, text="Press SCAN NOW to find setups",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=20)
            return

        filt      = self.scan_filter.get()
        min_score = self.min_score.get()

        # Sort and filter
        bull_call_list = sorted(
            [r for r in self.scanner_results if r["bull_score"] >= min_score],
            key=lambda x: x["bull_score"], reverse=True
        )
        bull_put_list = sorted(
            [r for r in self.scanner_results if r["bull_put_score"] >= min_score],
            key=lambda x: x["bull_put_score"], reverse=True
        )
        bear_list = sorted(
            [r for r in self.scanner_results if r["bear_score"] >= min_score],
            key=lambda x: x["bear_score"], reverse=True
        )
        cc_list = sorted(
            [r for r in self.scanner_results if r.get("cc_score", 0) >= min_score],
            key=lambda x: x.get("cc_score", 0), reverse=True
        )
        lp_list = sorted(
            [r for r in self.scanner_results if r.get("lp_score", 0) >= min_score],
            key=lambda x: x.get("lp_score", 0), reverse=True
        )

        if filt == "BEAR":
            bull_call_list = []
            bull_put_list = []
            cc_list = []
        if filt == "BULL":
            bear_list = []
            lp_list = []

        def score_color(s):
            return GREEN if s >= 75 else YELLOW if s >= 60 else TEXT2

        def make_row(parent, r, strategy):
            is_bull = strategy in ("bull_call", "bull_put", "covered_call")
            bg_c = "#0d1a0d" if is_bull else "#1a0d0d"
            row = tk.Frame(parent, bg=bg_c,
                           highlightbackground=BORDER, highlightthickness=1,
                           cursor="hand2")
            row.pack(fill="x", pady=2)

            if strategy == "bull_call":
                strategy_label = "Bull Call"
                entry = r["bull_debit"]
                pnl = r["bull_profit"]
                rr = r["bull_rr"]
                buy_s = r["bull_buy"]
                sell_s = r["bull_sell"]
                wrong_way = r["bull_wrong_way"]
                score_val = r["bull_score"]
            elif strategy == "bull_put":
                strategy_label = "Bull Put"
                entry = r["bull_put_credit"]
                pnl = r["bull_put_profit"]
                rr = r["bull_put_rr"]
                buy_s = r["bull_put_buy"]
                sell_s = r["bull_put_sell"]
                wrong_way = r["bull_put_wrong_way"]
                score_val = r["bull_put_score"]
            elif strategy == "covered_call":
                strategy_label = "Cov Call"
                entry = r["cc_premium"]
                pnl = r["cc_premium"]
                rr = r.get("cc_annualized", 0)   # annualised yield as R:R column
                buy_s = r["price"]               # stock price (you own the shares)
                sell_s = r["cc_strike"]
                wrong_way = r["cc_wrong_way"]
                score_val = r.get("cc_score", 0)
            elif strategy == "long_put":
                strategy_label = "Long Put"
                entry = r["lp_debit"]
                pnl = r["lp_break_even"]
                rr = r["lp_rr"]
                buy_s = r["lp_strike"]
                sell_s = 0
                wrong_way = r["lp_wrong_way"]
                score_val = r.get("lp_score", 0)
            else:
                strategy_label = "Bear Put"
                entry = r["bear_debit"]
                pnl = r["bear_profit"]
                rr = r["bear_rr"]
                buy_s = r["bear_buy"]
                sell_s = r["bear_sell"]
                wrong_way = r["bear_wrong_way"]
                score_val = r["bear_score"]
            sig_color  = GREEN if is_bull else RED
            risk_color = RED if wrong_way >= 0.5 else YELLOW if wrong_way >= 0.35 else GREEN
            sc_color   = score_color(score_val)

            if strategy == "covered_call":
                sell_disp = f"${sell_s:.0f}"
                buy_disp  = "Own"
                rr_disp   = f"{rr:.0f}%/yr"
                pnl_disp  = f"${pnl:.2f} cr"
            elif strategy == "long_put":
                sell_disp = "—"
                buy_disp  = f"${buy_s:.0f}"
                rr_disp   = f"{rr}:1"
                pnl_disp  = f"${pnl:.2f} BE"
            else:
                sell_disp = f"${sell_s:.0f}"
                buy_disp  = f"${buy_s:.0f}"
                rr_disp   = f"{rr}:1"
                pnl_disp  = f"${pnl:.2f}"

            cols = [
                (strategy_label,        10, sig_color),
                (r["ticker"],           6,  sig_color),
                (f"${r['price']:.2f}",  8,  TEXT),
                (buy_disp,              6,  TEXT2),
                (sell_disp,             6,  TEXT2),
                (r["expiry_date"],      10, ACCENT2),
                (f"${entry:.2f}",       7,  YELLOW),
                (pnl_disp,              10, GREEN),
                (rr_disp,               6,  CYAN),
                (f"{wrong_way*100:.0f}%", 7, risk_color),
                (f"{r['rsi']:.0f}",     5,  TEXT2),
                (f"★{score_val}",       5,  sc_color),
                ("🎯 Rate Entry",        12, ACCENT),
            ]
            for val, w, fg in cols:
                lbl = tk.Label(row, text=val, font=self.f_mono_s, bg=bg_c,
                               fg=fg, width=w, anchor="w")
                lbl.pack(side="left", padx=4, pady=6)

            # Click any part of row to open entry scorer
            for widget in row.winfo_children():
                widget.bind("<Button-1>",
                    lambda e, rec=r, strat=strategy: self._open_entry_scorer_strategy(rec, strat))
            row.bind("<Button-1>",
                lambda e, rec=r, strat=strategy: self._open_entry_scorer_strategy(rec, strat))

        if not bull_call_list and not bull_put_list and not cc_list:
            tk.Label(self.bull_inner, text="No bullish setups above threshold",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=10)
        else:
            if bull_call_list:
                tk.Label(self.bull_inner, text="Bull Call Spreads",
                         font=self.f_small, bg=BG, fg=TEXT3).pack(anchor="w", pady=(0,4))
                for r in bull_call_list[:10]:
                    make_row(self.bull_inner, r, strategy="bull_call")
            if bull_put_list:
                tk.Label(self.bull_inner, text="Bull Put Spreads",
                         font=self.f_small, bg=BG, fg=TEXT3).pack(anchor="w", pady=(8,4))
                for r in bull_put_list[:10]:
                    make_row(self.bull_inner, r, strategy="bull_put")
            if cc_list:
                tk.Label(self.bull_inner, text="Covered Calls  (sell OTM call vs owned shares)",
                         font=self.f_small, bg=BG, fg=TEXT3).pack(anchor="w", pady=(8,4))
                for r in cc_list[:10]:
                    make_row(self.bull_inner, r, strategy="covered_call")

        if not bear_list and not lp_list:
            tk.Label(self.bear_inner, text="No bearish setups above threshold",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=10)
        else:
            if bear_list:
                tk.Label(self.bear_inner, text="Bear Put Spreads",
                         font=self.f_small, bg=BG, fg=TEXT3).pack(anchor="w", pady=(0,4))
                for r in bear_list[:10]:
                    make_row(self.bear_inner, r, strategy="bear_put")
            if lp_list:
                tk.Label(self.bear_inner, text="Long Puts  (directional bearish)",
                         font=self.f_small, bg=BG, fg=TEXT3).pack(anchor="w", pady=(8,4))
                for r in lp_list[:10]:
                    make_row(self.bear_inner, r, strategy="long_put")

        self.bull_canvas_ref.update_idletasks()
        self.bull_canvas_ref.configure(scrollregion=self.bull_canvas_ref.bbox("all"))
        self.bear_canvas_ref.update_idletasks()
        self.bear_canvas_ref.configure(scrollregion=self.bear_canvas_ref.bbox("all"))

    # ═══════════════════════════════════════
    #  ENTRY SCORER POPUP
    # ═══════════════════════════════════════
    def _open_entry_scorer(self, r, is_bull):
        """Opens the 10-point entry scoring popup for a spread."""
        win = tk.Toplevel(self)
        win.title(f"Entry Scorer — {r['ticker']} {'Bull Call' if is_bull else 'Bear Put'} Spread")
        win.geometry("560x720")
        win.configure(bg=BG)
        win.resizable(False, False)

        direction = "BULL CALL SPREAD" if is_bull else "BEAR PUT SPREAD"
        dir_color = GREEN if is_bull else RED
        buy_s  = r["bull_buy"]    if is_bull else r["bear_buy"]
        sell_s = r["bull_sell"]   if is_bull else r["bear_sell"]
        debit  = r["bull_debit"]  if is_bull else r["bear_debit"]
        profit = r["bull_profit"] if is_bull else r["bear_profit"]
        rr     = r["bull_rr"]     if is_bull else r["bear_rr"]

        # ── Header ──
        hdr = tk.Frame(win, bg=BG2, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"{r['ticker']}  —  {direction}",
                 font=self.f_head, bg=BG2, fg=dir_color).pack()
        tk.Label(hdr,
                 text=f"Buy ${buy_s:.0f} / Sell ${sell_s:.0f}  |  "
                      f"Debit ${debit:.2f}  |  Max Profit ${profit:.2f}  |  R:R {rr}:1",
                 font=self.f_small, bg=BG2, fg=TEXT2).pack(pady=(2,0))

        # Pre-filled auto scores from scanner data
        above_50  = r.get("above_50", False)
        above_200 = r.get("above_200", False)
        rsi       = r.get("rsi", 50)
        mom5      = r.get("mom5", 0)
        iv        = r.get("iv", 0.25)

        # Auto-determine some answers
        if is_bull:
            daily_trend_auto  = 1 if above_50 else 0
            rsi_auto          = 1 if rsi < 55 else 0
            momentum_auto     = 1 if mom5 > 0 else 0
        else:
            daily_trend_auto  = 1 if not above_50 else 0
            rsi_auto          = 1 if rsi > 45 else 0
            momentum_auto     = 1 if mom5 < 0 else 0

        iv_auto = 1 if iv > 0.25 else 0

        # ── Questions ──
        questions = [
            # (label, points, auto_value, description)
            ("Daily trend agrees with direction?",  2, daily_trend_auto,
             f"Price {'above' if is_bull else 'below'} 50 MA → auto-detected"),
            ("Hourly trend confirms?",              2, None,
             "Check hourly chart — higher highs/lows for bull, lower for bear"),
            ("RSI in right zone?",                  1, rsi_auto,
             f"RSI is {rsi:.0f} — {'good for bull (<55)' if is_bull else 'good for bear (>45)'}"),
            ("Volume confirms the move?",           1, None,
             "Today's volume higher than average? Check thinkorswim"),
            ("Clear S/R level identified?",         1, None,
             "Can you see a clear support (bull) or resistance (bear) level on chart?"),
            ("Breakout/Bounce trigger seen?",       1, None,
             "Price just broke resistance (bull) or bounced off support (bear)?"),
            ("VIX below 25?",                       1, None,
             "Low VIX = calm market = trends more reliable. Check VIX."),
            ("Put/Call ratio agrees?",              1, None,
             f"{'Below 0.7 = bullish' if is_bull else 'Above 1.0 = bearish'} — check barchart.com"),
            ("IV elevated for good premium?",       1, iv_auto,
             f"IV estimated at {iv:.0%} — {'good premium' if iv > 0.25 else 'low premium'}"),
            ("Time is 10am–11:30am or 2–3:30pm?",  None, None,
             "Best entry windows — avoid first 30 min and last 30 min"),
        ]

        scroll_c = tk.Canvas(win, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(win, orient="vertical", command=scroll_c.yview)
        sb.pack(side="right", fill="y")
        scroll_c.pack(fill="both", expand=True, padx=0)
        scroll_c.configure(yscrollcommand=sb.set)
        inner = tk.Frame(scroll_c, bg=BG)
        scroll_c.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: scroll_c.configure(
            scrollregion=scroll_c.bbox("all")))

        tk.Label(inner, text="ENTRY CHECKLIST — Answer all 10 questions",
                 font=self.f_small, bg=BG, fg=TEXT3).pack(anchor="w", padx=16, pady=(12,6))

        answer_vars = []
        total_points = sum(q[1] for q in questions if q[1] is not None)

        for i, (label, pts, auto_val, desc) in enumerate(questions):
            box = tk.Frame(inner, bg=CARD,
                           highlightbackground=BORDER, highlightthickness=1)
            box.pack(fill="x", padx=12, pady=3)

            top_row = tk.Frame(box, bg=CARD)
            top_row.pack(fill="x", padx=12, pady=(10,2))

            pts_text = f"+{pts}pts" if pts else "Timing"
            pts_color = ACCENT2 if pts and pts >= 2 else YELLOW if pts else TEXT3
            tk.Label(top_row, text=pts_text, font=self.f_mono_s,
                     bg=CARD, fg=pts_color, width=7).pack(side="left")
            tk.Label(top_row, text=label, font=self.f_body,
                     bg=CARD, fg=TEXT).pack(side="left", padx=6)

            tk.Label(box, text=desc, font=self.f_small,
                     bg=CARD, fg=TEXT3, anchor="w").pack(anchor="w", padx=12, pady=(0,6))

            var = tk.IntVar(value=auto_val if auto_val is not None else -1)
            answer_vars.append((var, pts))

            btn_row = tk.Frame(box, bg=CARD)
            btn_row.pack(anchor="w", padx=12, pady=(0,10))

            auto_label = " (auto)" if auto_val is not None else ""
            for val, lbl, col in [(1, f"✅ YES{auto_label}", GREEN),
                                   (0, "❌ NO", RED),
                                   (-1, "⬜ SKIP", TEXT3)]:
                tk.Radiobutton(btn_row, text=lbl, variable=var, value=val,
                               bg=CARD, fg=col, selectcolor=BG3,
                               activebackground=CARD, font=self.f_small,
                               relief="flat", cursor="hand2",
                               command=lambda: self._update_entry_score(
                                   answer_vars, total_points,
                                   score_lbl, verdict_lbl, size_lbl,
                                   action_lbl, bar_canvas, is_bull,
                                   debit, profit)).pack(side="left", padx=8)

        # ── Score Panel ──
        score_panel = tk.Frame(win, bg=BG2,
                               highlightbackground=ACCENT, highlightthickness=1)
        score_panel.pack(fill="x", padx=12, pady=8, side="bottom")
        sp_inner = tk.Frame(score_panel, bg=BG2, padx=16, pady=12)
        sp_inner.pack(fill="x")

        bar_canvas = tk.Canvas(sp_inner, height=12, bg=BG3, highlightthickness=0)
        bar_canvas.pack(fill="x", pady=(0,8))

        row1 = tk.Frame(sp_inner, bg=BG2)
        row1.pack(fill="x")
        tk.Label(row1, text="ENTRY SCORE:", font=self.f_head,
                 bg=BG2, fg=TEXT2).pack(side="left")
        score_lbl = tk.Label(row1, text="—  / 10", font=self.f_price,
                              bg=BG2, fg=TEXT)
        score_lbl.pack(side="left", padx=8)
        verdict_lbl = tk.Label(row1, text="Answer questions above",
                                font=self.f_head, bg=BG2, fg=TEXT3)
        verdict_lbl.pack(side="right")

        row2 = tk.Frame(sp_inner, bg=BG2)
        row2.pack(fill="x", pady=(6,0))
        tk.Label(row2, text="SIZE:", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left")
        size_lbl = tk.Label(row2, text="—", font=self.f_head, bg=BG2, fg=TEXT2)
        size_lbl.pack(side="left", padx=8)

        action_lbl = tk.Label(sp_inner, text="", font=self.f_body,
                               bg=BG2, fg=TEXT2, wraplength=500, justify="left")
        action_lbl.pack(anchor="w", pady=(6,0))

        # Trigger initial calculation with auto values
        self._update_entry_score(answer_vars, total_points, score_lbl,
                                  verdict_lbl, size_lbl, action_lbl,
                                  bar_canvas, is_bull, debit, profit)

    def _update_entry_score(self, answer_vars, total_points, score_lbl,
                             verdict_lbl, size_lbl, action_lbl,
                             bar_canvas, is_bull, debit, profit):
        """Recalculate and display entry score."""
        earned = sum(pts for var, pts in answer_vars
                     if pts and var.get() == 1)
        answered = sum(1 for var, pts in answer_vars
                       if pts and var.get() in (0, 1))

        if answered == 0:
            score_lbl.config(text="—  / 10", fg=TEXT)
            verdict_lbl.config(text="Answer questions above", fg=TEXT3)
            size_lbl.config(text="—", fg=TEXT2)
            action_lbl.config(text="")
            return

        # Normalize to 10
        max_possible = sum(pts for _, pts in answer_vars if pts)
        score_10 = round((earned / max_possible) * 10, 1)

        # Colors and verdict
        if score_10 >= 8:
            color   = GREEN
            verdict = "🔥 HIGH CONVICTION — ENTER NOW"
            size    = f"Up to 15 contracts  (max ${debit*1500:.0f} risk)"
            action  = (f"Strong setup. {'Bull call spread' if is_bull else 'Bear put spread'} "
                       f"confirmed by {answered} indicators. "
                       f"Enter at market open between 10:00–11:30 AM. "
                       f"Set stop loss at 50% of debit paid. "
                       f"Target: close at 75% of max profit.")
        elif score_10 >= 6:
            color   = YELLOW
            verdict = "✅ GOOD SETUP — ENTER STANDARD SIZE"
            size    = f"5–8 contracts  (max ${debit*800:.0f} risk)"
            action  = (f"Solid setup but not all signals aligned. "
                       f"Enter with standard size. Wait for "
                       f"{'price to hold above support' if is_bull else 'price to hold below resistance'} "
                       f"before adding. Stop at 50% debit loss.")
        elif score_10 >= 4:
            color   = YELLOW
            verdict = "⚠️ WEAK SETUP — WAIT OR SKIP"
            size    = "1–2 contracts only  (small test)"
            action  = (f"Too many signals missing. Best to wait for more "
                       f"confirmation. If you must enter, use minimal size "
                       f"and tight stop. Consider checking again in 1–2 hours.")
        else:
            color   = RED
            verdict = "❌ SKIP THIS TRADE"
            size    = "Do NOT enter"
            action  = (f"Setup not confirmed. Forcing this trade risks capital. "
                       f"Wait for a better setup — there will always be another opportunity. "
                       f"Patience is an edge.")

        score_lbl.config(text=f"{score_10:.1f}  / 10", fg=color)
        verdict_lbl.config(text=verdict, fg=color)
        size_lbl.config(text=size, fg=color)
        action_lbl.config(text=action, fg=TEXT2)

        # Progress bar
        bar_canvas.update_idletasks()
        w = bar_canvas.winfo_width()
        if w > 1:
            bar_canvas.delete("all")
            fill_w = int((score_10 / 10) * w)
            bar_canvas.create_rectangle(0, 0, w, 12, fill=BG3, outline="")
            bar_canvas.create_rectangle(0, 0, fill_w, 12, fill=color, outline="")

    # ═══════════════════════════════════════
    #  TAB 5 — ALERTS
    # ═══════════════════════════════════════
    def _open_entry_scorer_strategy(self, r, strategy):
        strategy_cfg = {
            "bull_call": {
                "title": "Bull Call",
                "direction": "BULL CALL SPREAD",
                "color": GREEN,
                "is_bull": True,
                "buy": r["bull_buy"],
                "sell": r["bull_sell"],
                "entry_label": "Debit",
                "entry_value": r["bull_debit"],
                "pnl_label": "Max Profit",
                "pnl_value": r["bull_profit"],
                "risk_value": r["bull_debit"],
                "wrong_way": r["bull_wrong_way"],
                "rr": r["bull_rr"],
                "support_text": "price to hold above support",
                "strategy_name": "Bull call spread",
            },
            "bull_put": {
                "title": "Bull Put",
                "direction": "BULL PUT SPREAD",
                "color": GREEN,
                "is_bull": True,
                "buy": r["bull_put_buy"],
                "sell": r["bull_put_sell"],
                "entry_label": "Credit",
                "entry_value": r["bull_put_credit"],
                "pnl_label": "Max Profit",
                "pnl_value": r["bull_put_profit"],
                "risk_value": r["bull_put_risk"],
                "wrong_way": r["bull_put_wrong_way"],
                "rr": r["bull_put_rr"],
                "support_text": "price to stay above the short put strike",
                "strategy_name": "Bull put spread",
            },
            "bear_put": {
                "title": "Bear Put",
                "direction": "BEAR PUT SPREAD",
                "color": RED,
                "is_bull": False,
                "buy": r["bear_buy"],
                "sell": r["bear_sell"],
                "entry_label": "Debit",
                "entry_value": r["bear_debit"],
                "pnl_label": "Max Profit",
                "pnl_value": r["bear_profit"],
                "risk_value": r["bear_debit"],
                "wrong_way": r["bear_wrong_way"],
                "rr": r["bear_rr"],
                "support_text": "price to hold below resistance",
                "strategy_name": "Bear put spread",
            },
            "covered_call": {
                "title": "Covered Call",
                "direction": "COVERED CALL",
                "color": GREEN,
                "is_bull": True,
                "buy": r["price"],
                "sell": r.get("cc_strike", 0),
                "entry_label": "Credit",
                "entry_value": r.get("cc_premium", 0),
                "pnl_label": "Max Income",
                "pnl_value": r.get("cc_premium", 0),
                "risk_value": r.get("cc_premium", 0),
                "wrong_way": r.get("cc_wrong_way", 0),
                "rr": r.get("cc_annualized", 0),
                "support_text": "stock to stay below the short call strike",
                "strategy_name": "Covered call",
            },
            "long_put": {
                "title": "Long Put",
                "direction": "LONG PUT",
                "color": RED,
                "is_bull": False,
                "buy": r.get("lp_strike", 0),
                "sell": 0,
                "entry_label": "Debit",
                "entry_value": r.get("lp_debit", 0),
                "pnl_label": "Break-Even",
                "pnl_value": r.get("lp_break_even", 0),
                "risk_value": r.get("lp_debit", 0),
                "wrong_way": r.get("lp_wrong_way", 0),
                "rr": r.get("lp_rr", 0),
                "support_text": "stock to fall below the put strike",
                "strategy_name": "Long put",
            },
        }[strategy]

        win = tk.Toplevel(self)
        win.title(f"Entry Scorer - {r['ticker']} {strategy_cfg['title']} Spread")
        win.geometry("560x720")
        win.configure(bg=BG)
        win.resizable(False, False)

        is_bull = strategy_cfg["is_bull"]
        hdr = tk.Frame(win, bg=BG2, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"{r['ticker']}  -  {strategy_cfg['direction']}",
                 font=self.f_head, bg=BG2, fg=strategy_cfg["color"]).pack()
        if strategy == "covered_call":
            hdr_detail = (
                f"Stock ${strategy_cfg['buy']:.2f}  |  Sell Call ${strategy_cfg['sell']:.0f}  |  "
                f"Credit ${strategy_cfg['entry_value']:.2f}  |  "
                f"Annualised {strategy_cfg['rr']:.0f}%/yr  |  "
                f"Downside {strategy_cfg['wrong_way']*100:.0f}% risk"
            )
        elif strategy == "long_put":
            hdr_detail = (
                f"Buy Put ${strategy_cfg['buy']:.0f}  |  "
                f"Debit ${strategy_cfg['entry_value']:.2f}  |  "
                f"Break-Even ${strategy_cfg['pnl_value']:.2f}  |  "
                f"R:R {strategy_cfg['rr']}:1  |  "
                f"Expires worthless {strategy_cfg['wrong_way']*100:.0f}%"
            )
        else:
            hdr_detail = (
                f"Buy ${strategy_cfg['buy']:.0f} / Sell ${strategy_cfg['sell']:.0f}  |  "
                f"{strategy_cfg['entry_label']} ${strategy_cfg['entry_value']:.2f}  |  "
                f"{strategy_cfg['pnl_label']} ${strategy_cfg['pnl_value']:.2f}  |  "
                f"R:R {strategy_cfg['rr']}:1  |  Wrong-Way {strategy_cfg['wrong_way']*100:.0f}%"
            )
        tk.Label(hdr, text=hdr_detail, font=self.f_small, bg=BG2, fg=TEXT2).pack(pady=(2, 0))

        above_50 = r.get("above_50", False)
        rsi = r.get("rsi", 50)
        mom5 = r.get("mom5", 0)
        iv = r.get("iv", 0.25)

        if strategy == "covered_call":
            daily_trend_auto = 1 if above_50 else 0
            rsi_auto         = 1 if 40 <= rsi <= 65 else 0
            momentum_auto    = 1 if 0 < mom5 < 6 else 0
            iv_auto          = 1 if iv > 0.25 else 0
            questions = [
                ("Stock in mild uptrend?",                2, daily_trend_auto,
                 f"Price above 50 MA ({above_50}) — auto-detected"),
                ("Sell strike at key resistance?",        2, None,
                 f"${strategy_cfg['sell']:.0f} should be near chart resistance — check weekly chart"),
                ("RSI not overbought (<65)?",             1, rsi_auto,
                 f"RSI is {rsi:.0f} — selling into overbought risk assignment too soon"),
                ("IV elevated (premium worth it)?",       1, iv_auto,
                 f"IV ~{iv:.0%} — want >25% for meaningful income. {'Good' if iv > 0.25 else 'Low premium'}"),
                ("No major earnings before expiry?",      2, None,
                 "Check earnings calendar — IV crush after earnings can hurt premium quality"),
                ("Premium > 1% of stock price?",          1, 1 if iv > 0.20 else 0,
                 f"${strategy_cfg['entry_value']:.2f} / ${r['price']:.2f} = {strategy_cfg['entry_value']/r['price']*100:.1f}% — want >1%"),
                ("Would you be OK holding the stock?",    1, None,
                 "Covered call = you stay long the stock. If you'd hate owning it, skip it."),
                ("VIX below 30?",                         1, None,
                 "VIX > 30 = vol spike — wait for calmer tape to sell premium"),
                ("Momentum not too strong (not chasing)?",1, momentum_auto,
                 f"5-day mom {mom5:.1f}% — if stock is running hard, cap is costly"),
                ("Time is 10am-11:30am or 2pm-3:30pm?",  None, None,
                 "Best windows to sell premium — avoid opening and closing volatility"),
            ]
        elif strategy == "long_put":
            daily_trend_auto = 1 if not above_50 else 0
            rsi_auto         = 1 if rsi > 55 else 0
            momentum_auto    = 1 if mom5 < -2 else 0
            iv_auto          = 1 if iv < 0.35 else 0
            questions = [
                ("Stock in downtrend?",                   2, daily_trend_auto,
                 f"Price {'above' if above_50 else 'below'} 50 MA — auto-detected"),
                ("RSI elevated or turning down?",         2, rsi_auto,
                 f"RSI is {rsi:.0f} — ideally >55 for bearish entry"),
                ("Negative momentum?",                    1, momentum_auto,
                 f"5-day momentum {mom5:.1f}% — want <-2% for conviction"),
                ("IV not already sky-high?",              1, iv_auto,
                 f"IV ~{iv:.0%} — buying puts when IV is high means overpaying. Want <35%"),
                ("Volume confirms breakdown?",            1, None,
                 "Today's vol > average on a down day? Check thinkorswim"),
                ("Key support broken?",                   2, None,
                 f"Has stock broken below a clear support level? Strike ${strategy_cfg['buy']:.0f}"),
                ("VIX below 25?",                         1, None,
                 "Low VIX = cheap puts. High VIX = expensive. Best to buy when VIX is calm."),
                ("Put/Call ratio bearish (>0.9)?",        1, None,
                 "Check barchart.com — elevated put/call = institutional hedging/bearish"),
                ("No upcoming catalyst that could reverse?", None, None,
                 "Earnings, Fed, macro events? A surprise reversal kills long puts fast"),
                ("Time is 10am-11:30am or 2pm-3:30pm?",  None, None,
                 "Best entry windows — avoid opening gap noise and closing melt-up"),
            ]
        else:
            if is_bull:
                daily_trend_auto = 1 if above_50 else 0
                rsi_auto         = 1 if rsi < 55 else 0
                momentum_auto    = 1 if mom5 > 0 else 0
            else:
                daily_trend_auto = 1 if not above_50 else 0
                rsi_auto         = 1 if rsi > 45 else 0
                momentum_auto    = 1 if mom5 < 0 else 0
            iv_auto = 1 if iv > 0.25 else 0
            questions = [
                ("Daily trend agrees with direction?", 2, daily_trend_auto,
                 f"Price {'above' if is_bull else 'below'} 50 MA -> auto-detected"),
                ("Hourly trend confirms?", 2, None,
                 "Check hourly chart -> higher highs/lows for bull, lower for bear"),
                ("RSI in right zone?", 1, rsi_auto,
                 f"RSI is {rsi:.0f} -> {'good for bull (<55)' if is_bull else 'good for bear (>45)'}"),
                ("Volume confirms the move?", 1, None,
                 "Today's volume higher than average? Check thinkorswim"),
                ("Clear S/R level identified?", 1, None,
                 "Can you see a clear support (bull) or resistance (bear) level on chart?"),
                ("Breakout/Bounce trigger seen?", 1, None,
                 "Price just broke resistance (bull) or bounced off support (bear)?"),
                ("VIX below 25?", 1, None, "Low VIX = calmer tape. Check VIX."),
                ("Put/Call ratio agrees?", 1, None,
                 f"{'Below 0.7 = bullish' if is_bull else 'Above 1.0 = bearish'} -> check barchart.com"),
                ("IV elevated for good premium?", 1, iv_auto,
                 f"IV estimated at {iv:.0%} -> {'good premium' if iv > 0.25 else 'low premium'}"),
                ("Time is 10am-11:30am or 2pm-3:30pm?", None, None,
                 "Best entry windows -> avoid first 30 min and last 30 min"),
            ]

        scroll_c = tk.Canvas(win, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(win, orient="vertical", command=scroll_c.yview)
        sb.pack(side="right", fill="y")
        scroll_c.pack(fill="both", expand=True, padx=0)
        scroll_c.configure(yscrollcommand=sb.set)
        inner = tk.Frame(scroll_c, bg=BG)
        scroll_c.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: scroll_c.configure(scrollregion=scroll_c.bbox("all")))

        tk.Label(inner, text="ENTRY CHECKLIST - Answer all 10 questions",
                 font=self.f_small, bg=BG, fg=TEXT3).pack(anchor="w", padx=16, pady=(12, 6))

        answer_vars = []
        for label, pts, auto_val, desc in questions:
            box = tk.Frame(inner, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            box.pack(fill="x", padx=12, pady=3)

            top_row = tk.Frame(box, bg=CARD)
            top_row.pack(fill="x", padx=12, pady=(10, 2))
            pts_text = f"+{pts}pts" if pts else "Timing"
            pts_color = ACCENT2 if pts and pts >= 2 else YELLOW if pts else TEXT3
            tk.Label(top_row, text=pts_text, font=self.f_mono_s,
                     bg=CARD, fg=pts_color, width=7).pack(side="left")
            tk.Label(top_row, text=label, font=self.f_body,
                     bg=CARD, fg=TEXT).pack(side="left", padx=6)
            tk.Label(box, text=desc, font=self.f_small,
                     bg=CARD, fg=TEXT3, anchor="w").pack(anchor="w", padx=12, pady=(0, 6))

            var = tk.IntVar(value=auto_val if auto_val is not None else -1)
            answer_vars.append((var, pts))
            btn_row = tk.Frame(box, bg=CARD)
            btn_row.pack(anchor="w", padx=12, pady=(0, 10))

            auto_label = " (auto)" if auto_val is not None else ""
            for val, lbl, col in [(1, f"YES{auto_label}", GREEN), (0, "NO", RED), (-1, "SKIP", TEXT3)]:
                tk.Radiobutton(
                    btn_row, text=lbl, variable=var, value=val,
                    bg=CARD, fg=col, selectcolor=BG3, activebackground=CARD,
                    font=self.f_small, relief="flat", cursor="hand2",
                    command=lambda: self._update_entry_score_strategy(
                        answer_vars, score_lbl, verdict_lbl, size_lbl,
                        action_lbl, bar_canvas, strategy_cfg["strategy_name"],
                        strategy_cfg["entry_label"], strategy_cfg["support_text"],
                        strategy_cfg["risk_value"])
                ).pack(side="left", padx=8)

        score_panel = tk.Frame(win, bg=BG2, highlightbackground=ACCENT, highlightthickness=1)
        score_panel.pack(fill="x", padx=12, pady=8, side="bottom")
        sp_inner = tk.Frame(score_panel, bg=BG2, padx=16, pady=12)
        sp_inner.pack(fill="x")
        bar_canvas = tk.Canvas(sp_inner, height=12, bg=BG3, highlightthickness=0)
        bar_canvas.pack(fill="x", pady=(0, 8))

        row1 = tk.Frame(sp_inner, bg=BG2)
        row1.pack(fill="x")
        tk.Label(row1, text="ENTRY SCORE:", font=self.f_head, bg=BG2, fg=TEXT2).pack(side="left")
        score_lbl = tk.Label(row1, text="- / 10", font=self.f_price, bg=BG2, fg=TEXT)
        score_lbl.pack(side="left", padx=8)
        verdict_lbl = tk.Label(row1, text="Answer questions above",
                               font=self.f_head, bg=BG2, fg=TEXT3)
        verdict_lbl.pack(side="right")

        row2 = tk.Frame(sp_inner, bg=BG2)
        row2.pack(fill="x", pady=(6, 0))
        tk.Label(row2, text="SIZE:", font=self.f_small, bg=BG2, fg=TEXT3).pack(side="left")
        size_lbl = tk.Label(row2, text="-", font=self.f_head, bg=BG2, fg=TEXT2)
        size_lbl.pack(side="left", padx=8)
        action_lbl = tk.Label(sp_inner, text="", font=self.f_body,
                              bg=BG2, fg=TEXT2, wraplength=500, justify="left")
        action_lbl.pack(anchor="w", pady=(6, 0))

        self._update_entry_score_strategy(
            answer_vars, score_lbl, verdict_lbl, size_lbl, action_lbl, bar_canvas,
            strategy_cfg["strategy_name"], strategy_cfg["entry_label"],
            strategy_cfg["support_text"], strategy_cfg["risk_value"]
        )

    def _update_entry_score_strategy(self, answer_vars, score_lbl, verdict_lbl, size_lbl,
                                     action_lbl, bar_canvas, strategy_name, entry_label,
                                     support_text, risk_value):
        earned = sum(pts for var, pts in answer_vars if pts and var.get() == 1)
        answered = sum(1 for var, pts in answer_vars if pts and var.get() in (0, 1))

        if answered == 0:
            score_lbl.config(text="- / 10", fg=TEXT)
            verdict_lbl.config(text="Answer questions above", fg=TEXT3)
            size_lbl.config(text="-", fg=TEXT2)
            action_lbl.config(text="")
            return

        max_possible = sum(pts for _, pts in answer_vars if pts)
        score_10 = round((earned / max_possible) * 10, 1)

        is_cc = strategy_name == "Covered call"
        is_lp = strategy_name == "Long put"

        if score_10 >= 8:
            color = GREEN
            verdict = "HIGH CONVICTION - ENTER NOW"
            if is_cc:
                size   = "Sell CC on full position  (all 100-share lots you hold)"
                action = (
                    f"Strong setup. {strategy_name} confirmed by {answered} checks. "
                    f"Sell the ${risk_value:.2f} credit call now — strike sits at resistance. "
                    f"Let it expire or buy back at 25% of credit received to free up the position."
                )
            elif is_lp:
                size   = f"5-10 contracts  (max ${risk_value*1000:.0f} at risk)"
                action = (
                    f"Strong bearish setup. {strategy_name} confirmed by {answered} indicators. "
                    f"Buy puts between 10:00-11:30 AM. "
                    f"Exit at 2-3× debit paid or cut if stock reclaims the key level."
                )
            else:
                size   = f"Up to 15 contracts  (max ${risk_value*1500:.0f} risk)"
                action = (
                    f"Strong setup. {strategy_name} confirmed by {answered} indicators. "
                    f"Enter between 10:00-11:30 AM if price action stays clean. "
                    f"Set stop loss at 50% of {'credit received' if entry_label == 'Credit' else 'debit paid'}. "
                    f"Target: close at 75% of max profit."
                )
        elif score_10 >= 6:
            color = YELLOW
            verdict = "GOOD SETUP - ENTER STANDARD SIZE"
            if is_cc:
                size   = "Sell CC on 50-75% of your position"
                action = (
                    f"Solid income setup. Sell covered calls on part of your position. "
                    f"Wait for {support_text}. "
                    f"Buy back if stock spikes and credit doubles against you."
                )
            elif is_lp:
                size   = f"3-5 contracts  (max ${risk_value*500:.0f} at risk)"
                action = (
                    f"Good bearish signal but not fully aligned. Enter standard size. "
                    f"Wait for {support_text}. "
                    f"Exit at 2× debit or cut at 50% debit loss."
                )
            else:
                size   = f"5-8 contracts  (max ${risk_value*800:.0f} risk)"
                action = (
                    f"Solid setup but not all signals aligned. Enter with standard size. "
                    f"Wait for {support_text} before adding. "
                    f"Stop at 50% {'credit loss' if entry_label == 'Credit' else 'debit loss'}."
                )
        elif score_10 >= 4:
            color = YELLOW
            verdict = "WEAK SETUP - WAIT OR SKIP"
            if is_cc:
                size   = "Sell CC on 25% of position only"
                action = "Conditions marginal — sell small or wait for IV to rise or stock to reach resistance."
            elif is_lp:
                size   = "1-2 contracts only  (small test)"
                action = "Too many signals missing. Wait for breakdown confirmation before sizing up."
            else:
                size   = "1-2 contracts only  (small test)"
                action = (
                    "Too many signals missing. Best to wait for more confirmation. "
                    "If you must enter, use minimal size and a tight stop."
                )
        else:
            color = RED
            verdict = "SKIP THIS TRADE"
            size = "Do NOT enter"
            if is_cc:
                action = "Conditions not right for selling premium here. Wait for higher IV or better trend alignment."
            elif is_lp:
                action = "No clear bearish edge. Forcing a long put here risks a full debit loss. Wait for a cleaner setup."
            else:
                action = "Setup not confirmed. Waiting for a cleaner entry is the better trade."

        score_lbl.config(text=f"{score_10:.1f} / 10", fg=color)
        verdict_lbl.config(text=verdict, fg=color)
        size_lbl.config(text=size, fg=color)
        action_lbl.config(text=action, fg=TEXT2)

        bar_canvas.update_idletasks()
        w = bar_canvas.winfo_width()
        if w > 1:
            bar_canvas.delete("all")
            fill_w = int((score_10 / 10) * w)
            bar_canvas.create_rectangle(0, 0, w, 12, fill=BG3, outline="")
            bar_canvas.create_rectangle(0, 0, fill_w, 12, fill=color, outline="")

    def _build_alerts(self, parent):
        tk.Label(parent, text="Active Alerts & Signals",
                 font=self.f_head, bg=BG, fg=TEXT).pack(anchor="w", padx=14, pady=(12,0))

        self.alerts_frame = tk.Frame(parent, bg=BG)
        self.alerts_frame.pack(fill="both", expand=True, padx=12, pady=8)

        self._render_alerts([])

    def _render_alerts(self, alerts):
        for w in self.alerts_frame.winfo_children():
            w.destroy()

        if not alerts:
            tk.Label(self.alerts_frame, text="No alerts — market looks stable.",
                     font=self.f_body, bg=BG, fg=TEXT3).pack(pady=20)
            return

        for icon, msg, color in alerts:
            row = tk.Frame(self.alerts_frame, bg=CARD,
                           highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=icon, font=self.f_head, bg=CARD, fg=color,
                     width=3).pack(side="left", padx=10, pady=10)
            tk.Label(row, text=msg, font=self.f_body, bg=CARD, fg=TEXT,
                     anchor="w").pack(side="left", fill="x", expand=True, pady=10)

    # ═══════════════════════════════════════
    #  TAB 5 — SETUP
    # ═══════════════════════════════════════
    def _build_setup(self, parent):
        canvas = tk.Canvas(parent, bg=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.pack(fill="both", expand=True)
        canvas.configure(yscrollcommand=scroll.set)

        inner = tk.Frame(canvas, bg=BG)
        canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        steps = [
            ("✅ STEP 1 — Install & Run (Do This Now)", GREEN,
             "Run this one command in Command Prompt:\n\n"
             "   pip install requests matplotlib pandas numpy pillow yfinance\n\n"
             "Then run:  python trading_app.py\n"
             "Live prices from Yahoo Finance start immediately — no login needed."),
            ("📊 CURRENT DATA SOURCE — Yahoo Finance", GREEN,
             "Your dashboard is live right now using Yahoo Finance.\n\n"
             "What you get:\n"
             "• Real stock prices (15 min delay during market hours)\n"
             "• 1 year price history for charts\n"
             "• RSI + 50/200-day moving averages calculated automatically\n"
             "• Buy/Sell signals updated every 30 seconds\n"
             "• Covered call income estimates\n\n"
             "No API key. No login. Works instantly."),
            ("🔜 UPGRADE — Switch to Schwab API (In ~2 Days)", ACCENT,
             "Once your Schwab API is approved:\n\n"
             "1. Open trading_app.py in Notepad\n"
             "2. Find line:  DATA_SOURCE = \"yahoo\"\n"
             "3. Change to:  DATA_SOURCE = \"schwab\"\n"
             "4. Add your keys:\n"
             "       APP_KEY    = \"your-key-here\"\n"
             "       APP_SECRET = \"your-secret-here\"\n"
             "5. Save and restart\n\n"
             "Schwab gives you: real-time prices + your actual account positions."),
            ("⚠️ Yahoo Finance Limitations", YELLOW,
             "• 15-minute delayed prices (not real-time)\n"
             "• No access to your real Schwab account or positions\n"
             "• Cannot place trades\n"
             "• Occasionally slow during high traffic\n\n"
             "For a $230k account, upgrading to Schwab API in 2 days is worth it."),
        ]

        for title, color, text in steps:
            box = tk.Frame(inner, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            box.pack(fill="x", padx=12, pady=4)
            tk.Label(box, text=title, font=self.f_head, bg=CARD, fg=color).pack(
                anchor="w", padx=14, pady=(12,4))
            tk.Label(box, text=text, font=self.f_body, bg=CARD, fg=TEXT2,
                     justify="left", anchor="w").pack(anchor="w", padx=14, pady=(0,12))

        # Auth buttons
        btn_frame = tk.Frame(inner, bg=BG)
        btn_frame.pack(fill="x", padx=12, pady=8)
        tk.Button(btn_frame, text="Open Schwab Login in Browser",
                  font=self.f_head, bg=ACCENT, fg=WHITE, relief="flat",
                  cursor="hand2", padx=16, pady=10,
                  command=self._open_schwab_login).pack(anchor="w")
        tk.Button(btn_frame, text="Paste Redirect URL + Save Token",
                  font=self.f_head, bg=GREEN, fg="#000000", relief="flat",
                  cursor="hand2", padx=16, pady=10,
                  command=self._complete_schwab_login).pack(anchor="w", pady=(8, 0))
        self.schwab_token_lbl = tk.Label(
            btn_frame,
            text=f"Schwab token status: {'Connected' if load_tokens() else 'No token saved yet'}",
            font=self.f_small, bg=BG, fg=TEXT2
        )
        self.schwab_token_lbl.pack(anchor="w", pady=(10, 0))
        self.schwab_error_lbl = tk.Label(
            btn_frame,
            text=f"Last Schwab status: {LAST_SCHWAB_ERROR}",
            font=self.f_small, bg=BG, fg=YELLOW, wraplength=900, justify="left"
        )
        self.schwab_error_lbl.pack(anchor="w", pady=(6, 0))
        if os.environ.get("SCHWAB_SSL_NO_VERIFY", "").strip().lower() in {"1", "true", "yes"}:
            tk.Label(
                btn_frame,
                text="WARNING: Schwab SSL verification is disabled for this run.",
                font=self.f_small, bg=BG, fg=RED, wraplength=900, justify="left"
            ).pack(anchor="w", pady=(6, 0))

    def _open_schwab_login(self):
        logger.info("_open_schwab_login: user initiated Schwab login")
        if APP_KEY == DEFAULT_APP_KEY or not APP_SECRET:
            logger.error("_open_schwab_login: missing app key or secret")
            self._update_schwab_status_labels()
            messagebox.showerror(
                "Schwab Setup",
                "Add SCHWAB_APP_KEY and SCHWAB_APP_SECRET before logging in.",
            )
            return
        webbrowser.open(build_schwab_authorize_url())
        self._update_schwab_status_labels()
        messagebox.showinfo(
            "Schwab Login",
            "Log in at Schwab, then copy the full redirected URL from your browser and click "
            "'Paste Redirect URL + Save Token'.",
        )

    def _complete_schwab_login(self):
        logger.info("_complete_schwab_login: waiting for pasted redirect URL")
        redirect_url = simpledialog.askstring(
            "Schwab Redirect URL",
            "Paste the full URL you were redirected to after Schwab login:",
            parent=self,
        )
        if not redirect_url:
            logger.warning("_complete_schwab_login: user cancelled redirect URL prompt")
            self._update_schwab_status_labels()
            return
        auth_code = extract_schwab_auth_code(redirect_url)
        if not auth_code:
            logger.error("_complete_schwab_login: no auth code found in pasted URL")
            self._update_schwab_status_labels()
            messagebox.showerror(
                "Schwab Login",
                "No authorization code was found in that URL. Paste the full redirected URL.",
            )
            return
        ok, msg = exchange_auth_code_for_tokens(auth_code)
        self._update_schwab_status_labels()
        if ok:
            logger.info("_complete_schwab_login: token exchange completed successfully")
            messagebox.showinfo("Schwab Login", msg)
        else:
            logger.error("_complete_schwab_login: token exchange failed: %s", msg)
            messagebox.showerror("Schwab Login", msg)

    def _update_schwab_status_labels(self):
        if hasattr(self, "schwab_token_lbl"):
            self.schwab_token_lbl.config(
                text=f"Schwab token status: {'Connected' if load_tokens() else 'No token saved yet'}"
            )
        if hasattr(self, "schwab_error_lbl"):
            self.schwab_error_lbl.config(text=f"Last Schwab status: {LAST_SCHWAB_ERROR}")

    # ─────────────────────────────────────────
    #  DATA UPDATE
    # ─────────────────────────────────────────
    def _start_data_thread(self):
        def run():
            # Fetch earnings dates first (in background)
            all_tickers = list(PORTFOLIO.keys()) + list(SCAN_UNIVERSE)
            self.after(0, lambda: self.lbl_update.config(
                text="⟳ Fetching earnings dates...", fg=YELLOW))
            fetch_all_earnings(list(set(all_tickers)))
            self.after(0, lambda: self.lbl_update.config(
                text="⟳ Loading price history...", fg=YELLOW))

            # Load price history
            if not is_demo_mode():
                for ticker in list(PORTFOLIO.keys()) + ["SPY","QQQ","SPMO"]:
                    self.history_data[ticker] = fetch_history(ticker)
                    self.history_series_data[ticker] = fetch_history_series(ticker, period="2y")
                    if ticker in PORTFOLIO:
                        self.earnings_timeline_data[ticker] = fetch_earnings_timeline_yahoo(ticker)
                for ticker in AI_THEME_TICKERS:
                    if ticker not in self.history_data:
                        self.history_data[ticker] = fetch_history(ticker)

            # Refresh earnings cards now that we have dates
            self.after(0, self._refresh_earnings_labels)
            self.after(0, self._render_earnings_dashboard)

            while self.is_running:
                self._refresh_data()
                self._maybe_auto_refresh_scanner()
                time.sleep(30)
        t = threading.Thread(target=run, daemon=True)
        t.start()

    def _refresh_earnings_labels(self):
        """Update earnings labels on stock cards after fetch completes."""
        for ticker, card in self.stock_cards.items():
            earn = get_earnings(ticker)
            if hasattr(card, "_refs") and "earn" in card._refs:
                days_away = self._days_to_earnings(earn)
                color = RED if days_away is not None and days_away <= 7 else YELLOW
                card._refs["earn"].config(
                    text=f"ER: {earn}" + (" ⚠ SOON" if days_away is not None and days_away <= 7 else ""),
                    fg=color)

    def _days_to_earnings(self, earn_str):
        """Return days until earnings, or None if unknown."""
        if not earn_str or earn_str == "—":
            return None
        try:
            from datetime import datetime
            dt = datetime.strptime(f"{earn_str} {datetime.now().year}", "%b %d %Y")
            delta = (dt.date() - datetime.now().date()).days
            if delta < 0:
                dt = datetime.strptime(f"{earn_str} {datetime.now().year + 1}", "%b %d %Y")
                delta = (dt.date() - datetime.now().date()).days
            return delta
        except Exception:
            return None

    def _manual_refresh(self):
        threading.Thread(target=self._refresh_data, daemon=True).start()

    def _refresh_data(self):
        all_symbols = list(dict.fromkeys(list(PORTFOLIO.keys()) + list(ETF_SYMBOLS) + list(SCAN_UNIVERSE) + AI_THEME_TICKERS))

        if is_demo_mode():
            # Fallback mock data
            import random
            raw = {}
            for t in all_symbols:
                mock = MOCK_PRICES.get(t, {})
                p = mock.get("price", 100) * (1 + random.gauss(0, 0.001))
                raw[t] = {"price": p, "change": mock.get("change", 0),
                          "pct": mock.get("pct", 0)}
        else:
            quotes = fetch_quotes(all_symbols)
            if not quotes:
                self.after(0, lambda: self.lbl_update.config(
                    text="⚠ Connection failed — retrying...", fg=RED))
                return
            raw = quotes  # already in {price, change, pct} format

        self.stock_data  = raw
        self.last_update = datetime.now().strftime("%I:%M:%S %p")
        self.after(0, lambda: self._update_ui(raw))

    def _update_ui(self, raw):
        self.lbl_update.config(text=f"Updated: {self.last_update}", fg=TEXT3)

        alerts  = []
        total_w = 0
        total_m = 0

        # Update stock cards
        for ticker, card in self.stock_cards.items():
            if ticker not in raw:
                continue
            d     = raw[ticker]
            price = d["price"]
            chg   = d["change"]
            pct   = d["pct"]
            refs  = card._refs
            cfg   = PORTFOLIO[ticker]

            # RSI + MA from history or mock
            if is_demo_mode():
                rsi  = MOCK_RSI.get(ticker, 50)
                ma50 = MOCK_MA50.get(ticker)
                ma200= MOCK_MA200.get(ticker)
            else:
                hist  = self.history_data.get(ticker, [])
                rsi   = calc_rsi(hist) if hist else 50
                ma50  = calc_ma(hist, 50)
                ma200 = calc_ma(hist, 200)

            sig, sig_color, sig_icon = get_signal(price, rsi, ma50 or price, ma200 or price)

            # Update labels
            refs["price"].config(text=f"${price:.2f}", fg=TEXT)
            chg_col = GREEN if chg >= 0 else RED
            arrow   = "▲" if chg >= 0 else "▼"
            refs["change"].config(text=f"{arrow} {abs(pct):.2f}%  ${abs(chg):.2f}", fg=chg_col)
            refs["signal"].config(text=sig, fg=sig_color, bg=CARD)

            # RSI bar
            canvas = refs["rsi_canvas"]
            canvas.update_idletasks()
            w = canvas.winfo_width()
            if w > 1:
                canvas.delete("all")
                rsi_w = int(rsi / 100 * w)
                rsi_col = GREEN if rsi < 35 else (RED if rsi > 65 else YELLOW)
                canvas.create_rectangle(0, 0, rsi_w, 6, fill=rsi_col, outline="")
            refs["rsi_lbl"].config(text=str(int(rsi)), fg=GREEN if rsi < 35 else RED if rsi > 65 else TEXT2)

            # Income
            dte     = covered_call_dte()
            prem    = est_premium(price, cfg["call_strike"], dte=dte)
            weekly  = prem * 100 * (cfg["shares"] // 100)
            monthly = weekly * 4.3
            total_w += weekly
            total_m += monthly
            refs["income"].config(text=f"Call ${cfg['call_strike']} -> ${weekly:.0f}/wk")

            # Highlight selected
            border_col = ACCENT if self.selected_ticker.get() == ticker else BORDER
            card.config(highlightbackground=border_col)

            # Income table row
            if ticker in self.income_rows:
                row = self.income_rows[ticker]
                row[3].config(text=f"${price:.2f}")
                row[4].config(text=f"${prem:.2f}")
                row[5].config(text=f"${weekly:.0f}", fg=ACCENT2)
                row[6].config(text=f"${monthly:.0f}", fg=ACCENT2)
                row[7].config(text=sig, fg=sig_color)

            # Alerts
            if rsi < 32:
                alerts.append(("🟢", f"{ticker}: RSI {rsi:.0f} — Oversold, strong buy signal", GREEN))
            elif rsi > 72:
                alerts.append(("🔴", f"{ticker}: RSI {rsi:.0f} — Overbought, sell covered call now", RED))
            if ma50 and price < ma50 * 0.97:
                alerts.append(("⚠️", f"{ticker}: Price 3%+ below 50-day MA — be cautious", YELLOW))
            earn = get_earnings(ticker)
            if earn and earn != "—":
                days = self._days_to_earnings(earn)
                if days is not None and days <= 14:
                    color = RED if days <= 5 else YELLOW
                    alerts.append(("📅", f"{ticker}: Earnings {earn} ({days}d away) — close options before this date", color))

            # Detail panel
            if self.selected_ticker.get() == ticker:
                self._update_detail(ticker, price, chg, pct, rsi, ma50, ma200, sig, sig_color, prem, weekly)

        # ETF cards
        for ticker, card in self.etf_cards.items():
            if ticker not in raw:
                continue
            d = raw[ticker]
            refs = card._refs
            chg_col = GREEN if d["change"] >= 0 else RED
            arrow   = "▲" if d["change"] >= 0 else "▼"
            refs["price"].config(text=f"${d['price']:.2f}")
            refs["change"].config(text=f"{arrow} {abs(d['pct']):.2f}%", fg=chg_col)

            if is_demo_mode():
                rsi  = MOCK_RSI.get(ticker, 50)
                ma50 = MOCK_MA50.get(ticker)
            else:
                hist = self.history_data.get(ticker, [])
                rsi  = calc_rsi(hist) if hist else 50
                ma50 = calc_ma(hist, 50)
            sig, sig_color, _ = get_signal(d["price"], rsi, ma50 or d["price"], d["price"])
            refs["signal"].config(text=sig, fg=sig_color)

        # Summary
        grand = total_m + 1800
        pct_goal = min(grand / MONTHLY_GOAL * 100, 999)
        self.summary_cards["WEEKLY INCOME"].config(text=f"${total_w:,.0f}", fg=ACCENT2)
        self.summary_cards["MONTHLY EST."].config(text=f"${grand:,.0f}", fg=ACCENT2)
        goal_col = GREEN if pct_goal >= 100 else YELLOW if pct_goal >= 70 else RED
        self.summary_cards["GOAL PROGRESS"].config(text=f"{pct_goal:.0f}%", fg=goal_col)

        # Income totals
        self.total_weekly_lbl.config(text=f"${total_w:,.0f}/wk")
        self.total_monthly_lbl.config(text=f"${total_m:,.0f}/mo")
        self.income_total_lbl.config(text=f"${grand:,.0f}  /  ${MONTHLY_GOAL:,}")

        # Progress bar
        self.prog_canvas.update_idletasks()
        pw = self.prog_canvas.winfo_width()
        if pw > 1:
            self.prog_canvas.delete("all")
            fill_w = int(min(grand / MONTHLY_GOAL, 1.0) * pw)
            self.prog_canvas.create_rectangle(0,0,pw,14, fill=BG3, outline="")
            self.prog_canvas.create_rectangle(0,0,fill_w,14, fill=goal_col, outline="")

        # Alerts
        self._render_alerts(alerts)
        self._render_movers()
        self._render_ai_themes()
        self._render_earnings_dashboard()

    def _update_detail(self, ticker, price, chg, pct, rsi, ma50, ma200, sig, sig_color, prem, weekly):
        cfg = PORTFOLIO[ticker]
        dte = covered_call_dte()
        expiry_label = covered_call_expiry_label()
        self.detail_call_title.config(text=f"COVERED CALL - {expiry_label} Expiry")
        self.detail_ticker.config(text=ticker, fg=cfg.get("color", ACCENT))
        chg_col = GREEN if chg >= 0 else RED
        arrow   = "▲" if chg >= 0 else "▼"
        self.detail_price.config(text=f"${price:.2f}  {arrow} {abs(pct):.2f}%", fg=chg_col)
        self.detail_signal.config(text=f"● {sig}", fg=sig_color)

        rsi_col = GREEN if rsi < 35 else RED if rsi > 65 else TEXT
        self.detail_labels["RSI"].config(text=str(int(rsi)), fg=rsi_col)
        self.detail_labels["50-Day MA"].config(text=f"${ma50:.2f}" if ma50 else "—")
        self.detail_labels["200-Day MA"].config(text=f"${ma200:.2f}" if ma200 else "—")
        a50  = price > (ma50  or 0)
        a200 = price > (ma200 or 0)
        self.detail_labels["vs MA50"].config(
            text="↑ ABOVE" if a50  else "↓ BELOW", fg=GREEN if a50  else RED)
        self.detail_labels["vs MA200"].config(
            text="↑ ABOVE" if a200 else "↓ BELOW", fg=GREEN if a200 else RED)
        self.detail_labels["Weekly Income"].config(text=f"${weekly:.0f}", fg=ACCENT2)
        self._draw_detail_earnings_chart(ticker)

        self.detail_call.config(
            text=f"Strike: ${cfg['call_strike']}   Premium: ${prem:.2f}/share   "
                 f"Income: ${weekly:.0f}/wk  ->  ${weekly*4.3:.0f}/mo   ({dte} DTE)")
        earn = get_earnings(ticker)
        days = self._days_to_earnings(earn)
        earn_text = f"⚠️  Earnings: {earn}"
        if days is not None:
            earn_text += f"  ({days} days away)"
            if days <= 7:
                earn_text += "  — CLOSE OPTIONS NOW"
        self.detail_earn.config(text=earn_text,
            fg=RED if days is not None and days <= 7 else YELLOW)

    def _select_ticker(self, ticker):
        self.selected_ticker.set(ticker)
        if ticker in self.stock_data:
            d = self.stock_data[ticker]
            price = d["price"]
            cfg   = PORTFOLIO[ticker]
            if is_demo_mode():
                rsi  = MOCK_RSI.get(ticker, 50)
                ma50 = MOCK_MA50.get(ticker)
                ma200= MOCK_MA200.get(ticker)
            else:
                hist  = self.history_data.get(ticker, [])
                rsi   = calc_rsi(hist) if hist else 50
                ma50  = calc_ma(hist, 50)
                ma200 = calc_ma(hist, 200)
            sig, sig_color, _ = get_signal(price, rsi, ma50 or price, ma200 or price)
            dte    = covered_call_dte()
            prem   = est_premium(price, cfg["call_strike"], dte=dte)
            weekly = prem * 100 * (cfg["shares"] // 100)
            self._update_detail(ticker, d["price"], d["change"], d["pct"],
                                rsi, ma50, ma200, sig, sig_color, prem, weekly)
        # Redraw borders
        for t, card in self.stock_cards.items():
            card.config(highlightbackground=ACCENT if t == ticker else BORDER)

    # ─────────────────────────────────────────
    #  CLOCK
    # ─────────────────────────────────────────
    def _tick_clock(self):
        now = datetime.now()
        self.lbl_time.config(text=now.strftime("%a %b %d  %I:%M:%S %p"))

        h, m = now.hour, now.minute
        t = h * 60 + m
        if 570 <= t < 1200:
            self.lbl_market.config(text="● MARKET OPEN", fg=GREEN)
        elif 540 <= t < 570:
            self.lbl_market.config(text="● PRE-MARKET", fg=YELLOW)
        else:
            self.lbl_market.config(text="● CLOSED", fg=RED)

        self.after(1000, self._tick_clock)

    def on_close(self):
        self.is_running = False
        self.destroy()

# ─────────────────────────────────────────
#  LAUNCH
# ─────────────────────────────────────────
if __name__ == "__main__":
    app = TradingApp()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
