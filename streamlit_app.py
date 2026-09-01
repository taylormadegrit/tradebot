"""ScrapWealthLab tradebot — backtest & analysis playground.

A Streamlit front-end over the bot's own modules. No live trading, no Discord,
no always-on engine — just: pull data, run the backtester, read the chart the
way the bot reads it, and check the news / economic-calendar context.

Educational only. Nothing here is financial advice.

Run locally:   streamlit run streamlit_app.py
Deploy:        push to GitHub -> share.streamlit.io -> main file streamlit_app.py
"""
from __future__ import annotations

import datetime as dt
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="tradebot playground", page_icon="📈", layout="wide")

# --- optional secrets -> env, before importing bot modules -------------------
for _k in ("OANDA_TOKEN", "OANDA_ENV", "ANTHROPIC_API_KEY"):
    try:
        if _k in st.secrets and _k not in os.environ:
            os.environ[_k] = str(st.secrets[_k])
    except Exception:  # noqa: BLE001  -- no secrets.toml is fine
        pass

from bot.backtest import run as backtest_run          # noqa: E402
from bot.chart import render as render_chart           # noqa: E402
from bot.commentary import describe                    # noqa: E402
from bot.config import load_config                     # noqa: E402
from bot.instruments import spec                       # noqa: E402
from bot.news import NewsWatch                         # noqa: E402
from bot.news_impact import impact_line                # noqa: E402
from bot.scanner import scan_patterns                  # noqa: E402
from bot.strategies import REGISTRY                     # noqa: E402

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "sample_data"

YAHOO = {"XAUUSD": "GC=F", "US30": "^DJI", "US100": "^NDX",
         "MU": "MU", "AMD": "AMD", "BE": "BE"}
OANDA = {"XAUUSD": "XAU_USD", "US30": "US30_USD", "US100": "NAS100_USD"}

try:
    CFG = load_config()
    INSTRUMENT_CFG = {i["symbol"]: i for i in CFG.get("instruments", [])}
except Exception:  # noqa: BLE001
    INSTRUMENT_CFG = {}

SYMBOLS = sorted(p.stem for p in SAMPLE.glob("*.csv")) or list(YAHOO)


# --- data -------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def load_sample(symbol: str) -> pd.DataFrame:
    return pd.read_csv(SAMPLE / f"{symbol}.csv", parse_dates=["time"])


@st.cache_data(show_spinner="Fetching from Yahoo…", ttl=900)
def fetch_yahoo(symbol: str, interval: str, rng: str) -> pd.DataFrame:
    from bot.fetch_yahoo import fetch
    df = fetch(YAHOO.get(symbol, symbol), interval, rng)
    df["time"] = pd.to_datetime(df["time"])
    return df


@st.cache_data(show_spinner="Fetching from OANDA…", ttl=900)
def fetch_oanda(symbol: str, granularity: str, count: int) -> pd.DataFrame:
    from bot.fetch_oanda import fetch
    df = fetch(OANDA[symbol], granularity, count)
    df["time"] = pd.to_datetime(df["time"])
    return df


def get_data(symbol: str, source: str, **kw) -> pd.DataFrame:
    if source == "Yahoo (live)":
        return fetch_yahoo(symbol, kw.get("interval", "15m"), kw.get("range", "1mo"))
    if source == "OANDA (live)":
        return fetch_oanda(symbol, kw.get("granularity", "M15"), kw.get("count", 5000))
    return load_sample(symbol)


# --- sidebar --------------------------------------------------------------
st.sidebar.title("📈 tradebot playground")
symbol = st.sidebar.selectbox("Instrument", SYMBOLS,
                              index=SYMBOLS.index("XAUUSD") if "XAUUSD" in SYMBOLS else 0)

sources = ["Sample data (bundled)", "Yahoo (live)"]
if os.environ.get("OANDA_TOKEN") and symbol in OANDA:
    sources.append("OANDA (live)")
source = st.sidebar.radio("Data source", sources)

kw: dict = {}
if source == "Yahoo (live)":
    kw["interval"] = st.sidebar.selectbox("Bar size", ["5m", "15m", "30m", "1h", "1d"], index=1)
    kw["range"] = st.sidebar.selectbox("History", ["5d", "1mo", "3mo", "6mo", "1y", "2y"], index=1)
elif source == "OANDA (live)":
    kw["granularity"] = st.sidebar.selectbox("Granularity", ["M5", "M15", "M30", "H1", "H4"], index=1)
    kw["count"] = st.sidebar.slider("Bars", 500, 5000, 3000, 500)

try:
    df = get_data(symbol, source, **kw)
except Exception as e:  # noqa: BLE001
    st.sidebar.error(f"data load failed: {e}")
    df = load_sample(symbol) if (SAMPLE / f"{symbol}.csv").exists() else pd.DataFrame()

if not df.empty:
    st.sidebar.caption(f"{len(df):,} bars · {df['time'].iloc[0]:%Y-%m-%d} → {df['time'].iloc[-1]:%Y-%m-%d}")

st.sidebar.divider()
st.sidebar.caption("Educational only. Not financial advice. "
                   "Backtests ignore slippage, funding and real fills.")

tab_bt, tab_chart, tab_news, tab_cal = st.tabs(
    ["Backtest", "What the bot sees", "News", "Calendar"])

# ===================================================================== BACKTEST
with tab_bt:
    st.subheader(f"Backtest — {symbol}")
    c1, c2, c3 = st.columns(3)
    default_strat = INSTRUMENT_CFG.get(symbol, {}).get("strategy", "ma_crossover")
    strat = c1.selectbox("Strategy", list(REGISTRY),
                         index=list(REGISTRY).index(default_strat)
                         if default_strat in REGISTRY else 0)
    start_equity = c2.number_input("Start equity ($)", 100, 1_000_000, 100_000, step=1000)
    risk_pct = c3.number_input("Risk per trade (%)", 0.1, 5.0, 0.5, step=0.1)

    c4, c5 = st.columns(2)
    sp = spec(symbol)
    spread = c4.number_input("Spread (pips)", 0.0, 20.0, 2.0, step=0.5)
    lookback = c5.slider("Strategy window (bars)", 200, 3000, 1500, 100)

    default_params = INSTRUMENT_CFG.get(symbol, {}).get("params", {}) or {}
    params_txt = st.text_area(
        "Strategy params (YAML/JSON-ish, one per line: `key: value`)",
        "\n".join(f"{k}: {v}" for k, v in default_params.items()),
        height=110)

    def parse_params(txt: str) -> dict:
        out: dict = {}
        for line in txt.splitlines():
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            k, v = k.strip(), v.strip()
            if not k:
                continue
            try:
                out[k] = int(v)
            except ValueError:
                try:
                    out[k] = float(v)
                except ValueError:
                    out[k] = v
        return out

    if st.button("Run backtest", type="primary", disabled=df.empty):
        try:
            res = backtest_run(symbol, strat, parse_params(params_txt),
                               start_equity=float(start_equity), risk_pct=float(risk_pct),
                               spread_pips=float(spread), lookback=int(lookback),
                               df=df, detail=True)
        except Exception as e:  # noqa: BLE001
            st.error(f"backtest error: {e}")
            res = None

        if res:
            m = st.columns(5)
            m[0].metric("Trades", res["trades"])
            m[1].metric("Win rate", f"{res['win_rate_pct']}%")
            pf = res["profit_factor"]
            m[2].metric("Profit factor", "∞" if pf == float("inf") else pf)
            m[3].metric("Return", f"{res['return_pct']}%")
            m[4].metric("Max drawdown", f"{res['max_drawdown_pct']}%")

            curve = res.get("equity_curve")
            if curve is not None and not curve.empty:
                st.line_chart(curve.set_index("time")["equity"], height=280)
            log = res.get("trades_log")
            if log is not None and not log.empty:
                st.dataframe(log, use_container_width=True, height=320)
            else:
                st.info("No trades were taken with these settings.")

            st.caption("One historical window, no walk-forward. Profit factor > 1 on a "
                       "single sample is not an edge — re-test across regimes before "
                       "trusting it.")

# ============================================================ WHAT THE BOT SEES
with tab_chart:
    st.subheader(f"What the bot sees — {symbol}")
    if df.empty:
        st.warning("No data loaded.")
    else:
        p = INSTRUMENT_CFG.get(symbol, {}).get("params", {}) or {}
        ema_fast = int(p.get("ema_fast", 8))
        ma_slow = int(p.get("ma_slow", 66))
        try:
            read = describe(symbol, df, ema_fast=ema_fast, ma_slow=ma_slow)
        except Exception as e:  # noqa: BLE001
            read = f"read unavailable: {e}"
        try:
            patterns = scan_patterns(df)
        except Exception as e:  # noqa: BLE001
            patterns = [f"scan unavailable: {e}"]

        st.markdown(f"**Read:** {read}")
        st.markdown("**Patterns forming:**")
        for line in patterns:
            st.markdown(f"- {line}")

        try:
            out_dir = Path(tempfile.mkdtemp())
            img = render_chart(symbol, df, {"read": read, "patterns": patterns},
                               ema_fast=ema_fast, ma_slow=ma_slow, out_dir=out_dir)
            if img:
                st.image(str(img), use_container_width=True)
        except Exception as e:  # noqa: BLE001
            st.error(f"chart render failed: {e}")

# ===================================================================== NEWS
with tab_news:
    st.subheader(f"Headlines — {symbol}")
    st.caption("Yahoo Finance RSS. The **Impact** line is a rule-based read unless "
               "`ANTHROPIC_API_KEY` is set in the app's secrets.")
    if st.button("Load headlines"):
        try:
            items = NewsWatch._fetch(YAHOO.get(symbol, symbol))[-8:][::-1]
        except Exception as e:  # noqa: BLE001
            items = []
            st.error(f"news fetch failed: {e}")
        for it in items:
            when = dt.datetime.fromtimestamp(it["epoch"], dt.timezone.utc)
            st.markdown(f"**[{it['title']}]({it['link']})**  \n"
                        f"<sub>{when:%Y-%m-%d %H:%M} UTC</sub>", unsafe_allow_html=True)
            try:
                st.markdown(impact_line(symbol, it["title"]))
            except Exception:  # noqa: BLE001
                pass
            st.divider()

# ===================================================================== CALENDAR
with tab_cal:
    st.subheader("Economic calendar — event-risk windows")
    st.caption("High-impact releases the bot's blackout filter would gate entries "
               "around (±30 min). Source: ForexFactory weekly JSON.")
    before = st.slider("Blackout window before/after (min)", 0, 120, 30, 5)
    if st.button("Load calendar"):
        try:
            from bot.fetch_calendar import fetch as fetch_cal, DEFAULT_URL
            events = fetch_cal(DEFAULT_URL)
        except Exception as e:  # noqa: BLE001
            events = []
            st.error(f"calendar fetch failed: {e}")
        now = dt.datetime.now(dt.timezone.utc)
        rows = []
        for e in events:
            when = dt.datetime.fromtimestamp(e["epoch"], dt.timezone.utc)
            if when < now - dt.timedelta(hours=6):
                continue
            mins = round((when - now).total_seconds() / 60)
            in_window = abs(mins) <= before
            rows.append({
                "when (UTC)": when.strftime("%m-%d %H:%M"),
                "in": f"{mins}m" if mins >= 0 else f"{-mins}m ago",
                "ccy": e["country"], "impact": e["impact"], "event": e["title"],
                "forecast": e.get("forecast", ""), "previous": e.get("previous", ""),
                "blackout now": "🚫" if (in_window and e["impact"] == "High") else "",
            })
        if rows:
            st.dataframe(pd.DataFrame(rows[:60]), use_container_width=True, height=460)
        else:
            st.info("No upcoming events in the feed.")
