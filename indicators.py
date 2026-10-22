import math
from datetime import date, timedelta

from config import GREEN, RED, YELLOW, TEXT2, ACCENT2


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


def calc_atr(highs, lows, closes, n=14):
    if len(closes) < n + 1: return 0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return round(sum(trs[-n:]) / n, 2)


def calc_ema(prices, n):
    if len(prices) < n: return []
    k = 2 / (n + 1)
    ema = [sum(prices[:n]) / n]
    for p in prices[n:]:
        ema.append(p * k + ema[-1] * (1 - k))
    return ema


def calc_macd(prices, fast=12, slow=26, signal=9):
    if len(prices) < slow + signal: return [], [], []
    ema_fast = calc_ema(prices, fast)
    ema_slow = calc_ema(prices, slow)
    offset = len(ema_fast) - len(ema_slow)
    macd_line = [f - s for f, s in zip(ema_fast[offset:], ema_slow)]
    if len(macd_line) < signal: return macd_line, [], []
    signal_line = calc_ema(macd_line, signal)
    offset2 = len(macd_line) - len(signal_line)
    histogram = [m - s for m, s in zip(macd_line[offset2:], signal_line)]
    return macd_line, signal_line, histogram


def calc_bollinger(prices, n=20, num_std=2):
    if len(prices) < n: return None, None, None
    window = prices[-n:]
    mid = sum(window) / n
    variance = sum((p - mid) ** 2 for p in window) / n
    std = math.sqrt(variance)
    return round(mid + num_std * std, 2), round(mid, 2), round(mid - num_std * std, 2)


def calc_keltner(highs, lows, closes, n=20, atr_mult=1.5):
    if len(closes) < n: return None, None, None
    ema = calc_ema(closes, n)
    if not ema: return None, None, None
    mid = ema[-1]
    atr = calc_atr(highs, lows, closes, n)
    return round(mid + atr_mult * atr, 2), round(mid, 2), round(mid - atr_mult * atr, 2)


def calc_adx(highs, lows, closes, n=14):
    if len(closes) < n * 2: return 0, 0, 0
    plus_dm, minus_dm, trs = [], [], []
    for i in range(1, len(closes)):
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0)
        minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0)
        trs.append(max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1])))

    def wilder_smooth(values, n):
        smoothed = [sum(values[:n])]
        for v in values[n:]:
            smoothed.append(smoothed[-1] - smoothed[-1] / n + v)
        return smoothed

    smoothed_tr = wilder_smooth(trs, n)
    smoothed_plus_dm = wilder_smooth(plus_dm, n)
    smoothed_minus_dm = wilder_smooth(minus_dm, n)

    plus_di = [100 * pdm / tr if tr else 0 for pdm, tr in zip(smoothed_plus_dm, smoothed_tr)]
    minus_di = [100 * mdm / tr if tr else 0 for mdm, tr in zip(smoothed_minus_dm, smoothed_tr)]
    dx = [100 * abs(p - m) / (p + m) if (p + m) else 0 for p, m in zip(plus_di, minus_di)]

    if len(dx) < n: return 0, round(plus_di[-1], 1), round(minus_di[-1], 1)
    adx = sum(dx[:n]) / n
    for d in dx[n:]:
        adx = (adx * (n - 1) + d) / n
    return round(adx, 1), round(plus_di[-1], 1), round(minus_di[-1], 1)


def calc_obv(closes, volumes):
    if len(closes) < 2 or len(volumes) < len(closes): return []
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def calc_cmf(highs, lows, closes, volumes, n=20):
    if len(closes) < n or len(volumes) < n: return 0
    mfv_sum, vol_sum = 0, 0
    for i in range(-n, 0):
        rng = highs[i] - lows[i]
        mfm = ((closes[i] - lows[i]) - (highs[i] - closes[i])) / rng if rng else 0
        mfv_sum += mfm * volumes[i]
        vol_sum += volumes[i]
    return round(mfv_sum / vol_sum, 3) if vol_sum else 0


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
    from datetime import datetime
    return datetime.strptime(expiry_text.strip(), "%Y-%m-%d").date()


def strike_step_for_price(price):
    if price < 25:
        return 1
    if price < 200:
        return 2.5
    return 5


def round_to_strike(price, step):
    return round(round(price / step) * step, 2)


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
