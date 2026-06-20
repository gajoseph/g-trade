import os
import json
import time
import base64
import requests
from urllib.parse import urlparse, parse_qs, urlencode

from config import APP_KEY, APP_SECRET, REDIRECT_URI, TOKEN_FILE, logger, set_schwab_error, certifi


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
            from datetime import datetime
            dt = datetime.fromtimestamp(stamp / 1000).date()
            series.append({"date": dt, "close": round(float(close), 2)})
        return series
    except Exception:
        return []


    
