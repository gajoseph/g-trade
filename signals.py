import requests
import xml.etree.ElementTree as ET
from urllib.parse import urlencode

from config import YFINANCE_OK, yf, GREEN, RED, YELLOW, logger
from indicators import (
    calc_rsi, calc_ma, calc_atr, find_local_extrema,
    calc_macd, calc_bollinger, calc_keltner, calc_adx, calc_obv, calc_cmf,
)
from schwab_data import get_requests_verify_setting
from yahoo_data import create_yahoo_session


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


def detect_advanced_technical_signals(closes, highs, lows, volumes=None):
    """
    MACD momentum, Bollinger/Keltner squeeze, ADX trend strength, and (when volume
    history is available) OBV/CMF volume confirmation. Each check only appends a row
    when there's enough history to compute it, rather than forcing a fallback row.
    """
    if len(closes) < 35:
        return []

    signals = []
    price = closes[-1]

    macd_line, signal_line, histogram = calc_macd(closes)
    if len(histogram) >= 2:
        if histogram[-2] <= 0 < histogram[-1]:
            signals.append({
                "name": "MACD", "bias": "Bullish", "confidence": 70,
                "level": round(macd_line[-1], 3),
                "prediction": "MACD crossed above signal line; bullish momentum shift",
            })
        elif histogram[-2] >= 0 > histogram[-1]:
            signals.append({
                "name": "MACD", "bias": "Bearish", "confidence": 70,
                "level": round(macd_line[-1], 3),
                "prediction": "MACD crossed below signal line; bearish momentum shift",
            })
        else:
            bias = "Bullish" if histogram[-1] > 0 else "Bearish" if histogram[-1] < 0 else "Neutral"
            signals.append({
                "name": "MACD", "bias": bias, "confidence": 52,
                "level": round(macd_line[-1], 3),
                "prediction": f"MACD histogram {'positive' if histogram[-1] > 0 else 'negative'}; momentum still {bias.lower()}",
            })

    bb_upper, bb_mid, bb_lower = calc_bollinger(closes)
    kc_upper, kc_mid, kc_lower = calc_keltner(highs, lows, closes)
    if bb_upper and kc_upper:
        squeeze_on = bb_upper < kc_upper and bb_lower > kc_lower
        if squeeze_on:
            signals.append({
                "name": "Bollinger/Keltner Squeeze", "bias": "Neutral", "confidence": 55,
                "level": bb_mid,
                "prediction": "Volatility squeeze (Bollinger inside Keltner); breakout pending",
            })
        elif price > bb_upper:
            signals.append({
                "name": "Bollinger/Keltner Squeeze", "bias": "Bullish", "confidence": 68,
                "level": bb_upper,
                "prediction": "Price broke above upper Bollinger band; volatility expansion to the upside",
            })
        elif price < bb_lower:
            signals.append({
                "name": "Bollinger/Keltner Squeeze", "bias": "Bearish", "confidence": 68,
                "level": bb_lower,
                "prediction": "Price broke below lower Bollinger band; volatility expansion to the downside",
            })

    adx, plus_di, minus_di = calc_adx(highs, lows, closes)
    if adx:
        if adx < 20:
            signals.append({
                "name": "ADX Trend Strength", "bias": "Neutral", "confidence": 40,
                "level": adx,
                "prediction": f"ADX {adx} is below 20; choppy, no clear trend to follow",
            })
        else:
            bias = "Bullish" if plus_di > minus_di else "Bearish"
            conf = min(80, int(60 + min(adx - 20, 40) * 0.5))
            strength = "strong" if adx > 40 else "developing"
            signals.append({
                "name": "ADX Trend Strength", "bias": bias, "confidence": conf,
                "level": adx,
                "prediction": f"ADX {adx} ({strength} trend), +DI {plus_di} vs -DI {minus_di}",
            })

    if volumes and len(volumes) >= max(20, len(closes) - 5):
        cmf = calc_cmf(highs, lows, closes, volumes)
        obv = calc_obv(closes, volumes)
        if obv and len(obv) >= 10 and len(closes) >= 10:
            obv_slope = obv[-1] - obv[-10]
            price_slope = closes[-1] - closes[-10]
            if cmf > 0.05 and price_slope > 0 and obv_slope > 0:
                signals.append({
                    "name": "Volume Flow", "bias": "Bullish", "confidence": 65,
                    "level": cmf,
                    "prediction": f"Money flow confirms the uptrend (CMF {cmf})",
                })
            elif cmf < -0.05 and price_slope < 0 and obv_slope < 0:
                signals.append({
                    "name": "Volume Flow", "bias": "Bearish", "confidence": 65,
                    "level": cmf,
                    "prediction": f"Money flow confirms the downtrend (CMF {cmf})",
                })
            elif price_slope > 0 and (cmf < 0 or obv_slope < 0):
                signals.append({
                    "name": "Volume Flow", "bias": "Bearish", "confidence": 50,
                    "level": cmf,
                    "prediction": "Price rising on weak/negative volume flow; possible divergence",
                })
            elif price_slope < 0 and (cmf > 0 or obv_slope > 0):
                signals.append({
                    "name": "Volume Flow", "bias": "Bullish", "confidence": 50,
                    "level": cmf,
                    "prediction": "Price falling while volume flow holds up; possible bullish divergence",
                })
            else:
                signals.append({
                    "name": "Volume Flow", "bias": "Neutral", "confidence": 45,
                    "level": cmf,
                    "prediction": f"Volume flow is mixed (CMF {cmf})",
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
