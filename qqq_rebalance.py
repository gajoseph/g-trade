"""
QQQ Top-10 portfolio rebalancer.

Strategy:
  - Use QQQ's trend (MA50 / MA200 / RSI) to set the overall equity allocation.
  - Within the equity sleeve, mirror QQQ's top-10 holdings by weight.
  - Compare current holdings to those target dollar amounts and emit trades.

QQQ top-10 weights are approximate (update quarterly as QQQ rebalances).

Usage:
    python qqq_rebalance.py
"""

from config import ACCOUNT_SIZE, logger
from indicators import calc_ma, calc_rsi
from yahoo_data import fetch_history_yahoo, fetch_quotes_yahoo


# ---------------------------------------------------------------------------
# QQQ Top-10 holdings with approximate index weights (sum < 1.0)
# Update these after each quarterly QQQ rebalance.
# ---------------------------------------------------------------------------
QQQ_TOP10 = {
    "MSFT":  0.087,
    "AAPL":  0.085,
    "NVDA":  0.075,
    "AMZN":  0.055,
    "META":  0.050,
    "GOOGL": 0.048,
    "GOOG":  0.045,
    "TSLA":  0.035,
    "AVGO":  0.033,
    "COST":  0.028,
}

# Total weight in the top-10 slice (used to normalise to 100 % within the sleeve)
_TOP10_TOTAL = sum(QQQ_TOP10.values())

# Regime → what fraction of the total account goes into equities
REGIME_EQUITY_PCT = {
    "Risk-On":  0.90,
    "Caution":  0.60,
    "Risk-Off": 0.25,
}

MIN_TRADE_THRESHOLD = 500   # skip orders smaller than this dollar amount


# ---------------------------------------------------------------------------
# Regime detection
# ---------------------------------------------------------------------------

def classify_qqq_regime(closes: list[float]) -> str:
    if len(closes) < 51:
        return "Caution"
    price  = closes[-1]
    ma50   = calc_ma(closes, 50)
    ma200  = calc_ma(closes, min(200, len(closes)))
    rsi    = calc_rsi(closes)
    above_50  = price > ma50  if ma50  else False
    above_200 = price > ma200 if ma200 else False
    if above_50 and above_200 and rsi >= 45:
        return "Risk-On"
    if not above_50 and not above_200:
        return "Risk-Off"
    return "Caution"


# ---------------------------------------------------------------------------
# Target allocation
# ---------------------------------------------------------------------------

def build_targets(regime: str, total_account: float) -> dict[str, float]:
    """
    Return {ticker: target_dollar_value} for the QQQ top-10 holdings given
    the current regime equity allocation.
    """
    equity_budget = total_account * REGIME_EQUITY_PCT[regime]
    targets = {}
    for ticker, raw_weight in QQQ_TOP10.items():
        normalised = raw_weight / _TOP10_TOTAL      # weight within the sleeve
        targets[ticker] = equity_budget * normalised
    return targets


# ---------------------------------------------------------------------------
# Current holdings  (shares × live price)
# ---------------------------------------------------------------------------

def current_values(quotes: dict) -> dict[str, dict]:
    """
    Return per-ticker current data. Tickers not in PORTFOLIO default to 0 shares.
    """
    result = {}
    for ticker in QQQ_TOP10:
        price  = quotes.get(ticker, {}).get("price", 0.0)
        # Use shares from config.PORTFOLIO if this ticker is held, else 0
        from config import PORTFOLIO
        shares = PORTFOLIO.get(ticker, {}).get("shares", 0)
        result[ticker] = {"shares": shares, "price": price, "value": shares * price}
    return result


# ---------------------------------------------------------------------------
# Rebalance order generation
# ---------------------------------------------------------------------------

def build_orders(targets: dict, current: dict, quotes: dict) -> list[dict]:
    orders = []
    for ticker, target_val in targets.items():
        price = quotes.get(ticker, {}).get("price", 0.0)
        if price <= 0:
            continue
        curr_val = current.get(ticker, {}).get("value", 0.0)
        drift    = target_val - curr_val

        if abs(drift) < MIN_TRADE_THRESHOLD:
            continue

        shares = int(abs(drift) / price)
        if shares < 1:
            continue

        orders.append({
            "ticker":     ticker,
            "action":     "BUY" if drift > 0 else "SELL",
            "shares":     shares,
            "est_value":  round(shares * price, 2),
            "target":     round(target_val, 2),
            "current":    round(curr_val, 2),
        })
    return orders


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def _bar(title: str) -> None:
    print(f"\n{'='*64}")
    print(f"  {title}")
    print('='*64)


def print_regime(regime: str, closes: list[float]) -> None:
    price = closes[-1]
    ma50  = calc_ma(closes, 50)
    ma200 = calc_ma(closes, min(200, len(closes)))
    rsi   = calc_rsi(closes)
    eq_pct = REGIME_EQUITY_PCT[regime] * 100
    print(f"  QQQ   ${price:.2f}   MA50 ${ma50:.2f} ({'↑' if price > ma50 else '↓'})   "
          f"MA200 ${ma200:.2f} ({'↑' if price > ma200 else '↓'})   RSI {rsi:.1f}")
    print(f"  Regime: {regime}  →  equity target {eq_pct:.0f}%")


def print_allocation(targets: dict, current: dict, total_account: float) -> None:
    print(f"\n  {'Ticker':<7} {'Target $':>12} {'Current $':>12} {'Drift $':>12}  Target%")
    print(f"  {'-'*56}")
    for ticker in QQQ_TOP10:
        tgt  = targets.get(ticker, 0)
        curr = current.get(ticker, {}).get("value", 0.0)
        drift = tgt - curr
        pct  = tgt / total_account * 100 if total_account else 0
        flag = "+" if drift >= 0 else ""
        print(f"  {ticker:<7} ${tgt:>11,.0f} ${curr:>11,.0f} {flag}${drift:>10,.0f}  {pct:>5.1f}%")


def print_orders(orders: list[dict]) -> None:
    if not orders:
        print("  All positions within rebalance band — no trades needed.")
        return
    print(f"\n  {'Action':<5} {'Ticker':<7} {'Shares':>8} {'Est. $':>12}  {'Target $':>12}  {'Current $':>12}")
    print(f"  {'-'*66}")
    for o in orders:
        print(f"  {o['action']:<5} {o['ticker']:<7} {o['shares']:>8} "
              f"${o['est_value']:>11,.2f}  ${o['target']:>11,.2f}  ${o['current']:>11,.2f}")
    total_buy  = sum(o["est_value"] for o in orders if o["action"] == "BUY")
    total_sell = sum(o["est_value"] for o in orders if o["action"] == "SELL")
    print(f"\n  Buys : ${total_buy:>12,.2f}")
    print(f"  Sells: ${total_sell:>12,.2f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_qqq_rebalance() -> None:
    all_tickers = list(QQQ_TOP10.keys()) + ["QQQ"]

    _bar("Fetching market data …")
    quotes     = fetch_quotes_yahoo(all_tickers) or {}
    qqq_closes = fetch_history_yahoo("QQQ")

    if not qqq_closes:
        print("  ERROR: could not fetch QQQ history. Aborting.")
        return

    regime  = classify_qqq_regime(qqq_closes)
    targets = build_targets(regime, ACCOUNT_SIZE)
    current = current_values(quotes)
    equity  = sum(v["value"] for v in current.values())

    _bar("QQQ Regime")
    print_regime(regime, qqq_closes)

    _bar("QQQ Top-10 Allocation  (account = $" + f"{ACCOUNT_SIZE:,.0f})")
    print_allocation(targets, current, ACCOUNT_SIZE)

    orders = build_orders(targets, current, quotes)

    _bar("Rebalance Orders")
    print_orders(orders)

    logger.info(
        "QQQ top-10 rebalance | regime=%s | equity=$%.0f | orders=%d",
        regime, equity, len(orders),
    )


if __name__ == "__main__":
    run_qqq_rebalance()
