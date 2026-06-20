import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from urllib.parse import urlencode

from config import yf, YFINANCE_OK, curl_requests, certifi, ETF_SYMBOLS, EARNINGS_DATES, logger


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


def fetch_quotes_yahoo(symbols):
    """Fetch live quotes from Yahoo Finance - no API key needed"""
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
    if not earn_str or earn_str == "—" or earn_str == "-":
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
