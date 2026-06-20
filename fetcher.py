from config import DATA_SOURCE, DEFAULT_APP_KEY, APP_KEY, YFINANCE_OK
from yahoo_data import fetch_quotes_yahoo, fetch_history_yahoo, fetch_history_series_yahoo
from schwab_data import fetch_quotes_schwab, fetch_history_schwab, fetch_history_series_schwab


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
    if DATA_SOURCE == "yahoo":
        return not YFINANCE_OK
    return APP_KEY == DEFAULT_APP_KEY
