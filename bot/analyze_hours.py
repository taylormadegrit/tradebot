"""Which hours actually move? The evidence-based answer to "best hours to trade".

Reads data/<SYMBOL>.csv and reports, per UTC hour:
    bars         sample size
    bias_bps     mean return  -- near zero means no directional edge that hour
    activity_bps mean |return| -- higher means more range to work with
    stdev_bps    dispersion

    python -m bot.analyze_hours XAUUSD

Cross-check the busy hours against bot/sessions.py windows before trusting them.
"""
from __future__ import annotations

import sys

import pandas as pd

from .config import ROOT
from .data import load_csv


def run(symbol: str) -> pd.DataFrame:
    df = load_csv(ROOT, symbol).copy()
    df["ret_bps"] = df["close"].pct_change() * 1e4
    df["hour_utc"] = pd.to_datetime(df["time"], utc=True).dt.hour
    g = (
        df.groupby("hour_utc")["ret_bps"]
        .agg(
            bars="count",
            bias_bps="mean",
            activity_bps=lambda s: s.abs().mean(),
            stdev_bps="std",
        )
        .round(2)
        .sort_values("activity_bps", ascending=False)
    )
    print(f"\n{symbol} -- return stats by UTC hour (bps), most active first\n")
    print(g.to_string())
    print("\nbias near 0 = no directional edge; high activity = tradeable range\n")
    return g


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "XAUUSD")
