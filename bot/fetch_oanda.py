"""Pull candles from OANDA v20 into data/<SYM>.csv.

Accurate, free, ~24/5 intraday data for gold and index CFDs. Needs OANDA_TOKEN in
.env (a v20 personal access token) and OANDA_ENV=practice|live.

  python -m bot.fetch_oanda                 # default map below, M15, 5000 bars
  python -m bot.fetch_oanda M5 2000
  python -m bot.fetch_oanda M15 5000 XAU_USD:XAUUSD,US30_USD:US30

granularity: S5 S30 M1 M5 M15 M30 H1 H4 D W  (OANDA caps count at 5000 per call)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

import pandas as pd

from .config import ROOT

DEFAULTS = [("XAU_USD", "XAUUSD"), ("US30_USD", "US30"), ("NAS100_USD", "US100")]
HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}


def _host() -> str:
    return HOSTS.get(os.getenv("OANDA_ENV", "practice").lower(), HOSTS["practice"])


def _token() -> str:
    t = os.getenv("OANDA_TOKEN", "")
    if not t:
        raise RuntimeError("OANDA_TOKEN not set in .env")
    return t


def fetch(instrument: str, granularity: str = "M15", count: int = 5000) -> pd.DataFrame:
    count = max(1, min(int(count), 5000))
    qs = urllib.parse.urlencode({"granularity": granularity, "count": count, "price": "M"})
    url = f"{_host()}/v3/instruments/{urllib.parse.quote(instrument)}/candles?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_token()}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.load(r)

    rows = []
    for c in data.get("candles", []):
        if not c.get("complete", True):
            continue
        m = c["mid"]
        rows.append({
            "time": c["time"][:19] + "Z",
            "open": float(m["o"]), "high": float(m["h"]),
            "low": float(m["l"]), "close": float(m["c"]),
            "volume": int(c.get("volume", 0)),
        })
    return pd.DataFrame(rows)


def main(argv: list[str]) -> None:
    granularity = argv[0] if len(argv) > 0 else "M15"
    count = int(argv[1]) if len(argv) > 1 else 5000
    pairs = (
        [tuple(a.split(":")) for a in argv[2].split(",")]
        if len(argv) > 2 else DEFAULTS
    )
    (ROOT / "data").mkdir(exist_ok=True)
    for inst, out in pairs:
        try:
            df = fetch(inst, granularity, count)
        except Exception as e:  # noqa: BLE001
            print(f"  {inst:>10} -> FAILED: {e}")
            continue
        if df.empty:
            print(f"  {inst:>10} -> no candles returned")
            continue
        path = ROOT / "data" / f"{out}.csv"
        df.to_csv(path, index=False)
        print(f"  {inst:>10} -> {out + '.csv':13} {len(df):>5} bars  "
              f"{df['time'].iloc[0]} .. {df['time'].iloc[-1]}")


if __name__ == "__main__":
    main(sys.argv[1:])
