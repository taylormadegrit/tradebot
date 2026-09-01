"""Pull free historical OHLC bars from Yahoo Finance into data/<SYMBOL>.csv.

These are PROXIES for the HeroFX CFDs -- close enough for strategy research and
hour analysis, not identical (no broker spread/financing, slightly different
sessions). Replace with real broker exports before trusting demo numbers.

    python -m bot.fetch_yahoo                 # default set below (1h, 2y)
    python -m bot.fetch_yahoo GC=F:XAUUSD 15m 1mo

range token must be one of: 1d 5d 1mo 3mo 6mo 1y 2y 5y 10y ytd max
1h works out to 2y; 5m/15m only back ~1mo.
"""
from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

import pandas as pd

from .config import ROOT

DEFAULTS = [("GC=F", "XAUUSD"), ("^DJI", "US30"), ("^NDX", "US100")]
BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"

# Yahoo only accepts these range tokens. Intraday (<1d) is capped near 60d;
# 1h stretches to 2y. Pick the widest token your interval supports.
RANGE_TOKENS = {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}


def fetch(yahoo_symbol: str, interval: str = "1h", rng: str = "2y") -> pd.DataFrame:
    if rng not in RANGE_TOKENS:
        raise ValueError(f"range must be one of {sorted(RANGE_TOKENS)}")
    qs = urllib.parse.urlencode({"range": rng, "interval": interval, "includePrePost": "false"})
    url = f"{BASE}{urllib.parse.quote(yahoo_symbol)}?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)

    res = payload["chart"]["result"][0]
    ts = res["timestamp"]
    q = res["indicators"]["quote"][0]
    df = pd.DataFrame(
        {
            "time": pd.to_datetime(ts, unit="s", utc=True),
            "open": q["open"],
            "high": q["high"],
            "low": q["low"],
            "close": q["close"],
            "volume": q.get("volume", [0] * len(ts)),
        }
    )
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    df["time"] = df["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return df


def main(argv: list[str]) -> None:
    # usage: [interval] [range] [pairs]
    #   pairs = "YSYM:OUT,YSYM:OUT"  e.g. "GC=F:XAUUSD,AAPL:AAPL"
    interval = argv[0] if len(argv) > 0 else "1h"
    rng = argv[1] if len(argv) > 1 else "2y"
    pairs = (
        [tuple(a.split(":")) for a in argv[2].split(",")]
        if len(argv) > 2
        else DEFAULTS
    )
    (ROOT / "data").mkdir(exist_ok=True)
    for ysym, out in pairs:
        try:
            df = fetch(ysym, interval, rng)
        except Exception as e:  # noqa: BLE001
            print(f"  {ysym:>6} -> FAILED: {e}")
            continue
        path = ROOT / "data" / f"{out}.csv"
        df.to_csv(path, index=False)
        print(f"  {ysym:>6} -> {path.name:12} {len(df):>6} bars  {df['time'].iloc[0]} .. {df['time'].iloc[-1]}")


if __name__ == "__main__":
    main(sys.argv[1:])
