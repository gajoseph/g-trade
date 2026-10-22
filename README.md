# g-trade

George's Trading Dashboard — a desktop app (Python + tkinter + matplotlib) for tracking a
covered-call income portfolio, scanning for options spread setups, and watching momentum
and pattern signals across a watchlist.

## Setup

```
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in values as needed (Schwab API credentials are only
required if you set `DATA_SOURCE=schwab`; the default `DATA_SOURCE=yahoo` needs no keys).

## Run

```
python reading_app.py
```

## What's in it

- **Dashboard** — live quotes, RSI, moving averages, and covered-call premium/income for each
  position in `PORTFOLIO`.
- **Charts** — price history with indicators.
- **Income Tracker** — weekly/monthly covered-call premium vs. the monthly income goal.
- **Backtester** — historical performance of the strategy logic.
- **Pattern Detector**, **Movers**, **SPMO Strategy**, **Spread Scanner**, **Alerts**,
  **AI Themes** — see `signals.py` / `indicators.py` for the underlying logic.
- **Setup** — data source and Schwab OAuth configuration.

## Options pricing: real quotes vs. model estimates

Covered-call premiums shown in the Dashboard, Income Tracker, and the Spread Scanner's
covered-call column use a **real options-chain quote** (bid/ask mid-price) when one is
available:

- `DATA_SOURCE=schwab` → Schwab's `marketdata/v1/chains` endpoint (also returns IV, open
  interest, volume, and greeks).
- `DATA_SOURCE=yahoo` (default) → Yahoo's option chain via `yfinance`.

If no liquid quote is found for a strike (illiquid name, or no options data available), the
app falls back to a **Black-Scholes estimate** (`est_premium` / `bs_call` / `bs_put` in
`reading_app.py`) using an implied volatility guessed from recent price swings (ATR). That
estimate is a rough proxy — it can diverge meaningfully from real market pricing, especially
around earnings when actual IV moves faster than historical volatility does.

The Income Tracker's premium column is colored to show which one you're looking at: green
means a live chain quote, dim means a model estimate. See the `OPTIONS CHAIN` section near
the top of `reading_app.py` (`fetch_option_chain`, `nearest_chain_quote`,
`real_or_estimated_premium`) for the implementation. Chain lookups are cached in memory for
`OPTION_CHAIN_TTL_SECONDS` (default 300s) since a single scanner pass can touch 20+ tickers.

Only the covered-call leg currently prefers live quotes — the bull/bear call and put spread
suggestions in the Spread Scanner still use the Black-Scholes model for all their legs.
