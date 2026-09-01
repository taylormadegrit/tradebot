"""Candle data.

For backtests and (for now) the live loop, history comes from CSV files at
data/<SYMBOL>.csv with columns: time,open,high,low,close,volume

TODO: pull rolling candles straight from the broker for true live operation.
"""
from pathlib import Path

import pandas as pd

TF_MINUTES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}


def load_csv(root: Path, symbol: str) -> pd.DataFrame:
    p = root / "data" / f"{symbol}.csv"
    if not p.exists():
        raise FileNotFoundError(
            f"no history at {p} -- add an OHLCV csv (time,open,high,low,close,volume)"
        )
    df = pd.read_csv(p, parse_dates=["time"])
    need = {"time", "open", "high", "low", "close"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"{p} missing columns: {missing}")
    if "volume" not in df.columns:
        df["volume"] = 0
    return df.sort_values("time").reset_index(drop=True)
