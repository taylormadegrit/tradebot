"""Plain-language read of the current chart state.

Computed from the candle numbers, not from a screenshot: cheap, deterministic,
safe to run every cycle. The engine attaches the result to each instrument so
the dashboard can show "what the bot sees" per symbol.
"""
from __future__ import annotations

import pandas as pd


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    pc = c.shift(1)
    tr = pd.concat([(h - l), (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def describe(symbol: str, df: pd.DataFrame, ema_fast: int = 8, ma_slow: int = 66,
             box: int = 20) -> str:
    if len(df) < ma_slow + 3 * box + 2:
        return f"{symbol}: warming up ({len(df)} bars)"

    close = df["close"]
    px = float(close.iloc[-1])
    ema = close.ewm(span=ema_fast, adjust=False).mean()
    ma = close.rolling(ma_slow).mean()
    ma_now, ma_prev = float(ma.iloc[-1]), float(ma.iloc[-6])

    if ema.iloc[-1] > ma_now and ma_now > ma_prev:
        trend = f"uptrend (EMA{ema_fast} above rising MA{ma_slow})"
    elif ema.iloc[-1] < ma_now and ma_now < ma_prev:
        trend = f"downtrend (EMA{ema_fast} below falling MA{ma_slow})"
    else:
        trend = "no clear trend (EMA/MA mixed)"

    hi = float(df["high"].iloc[-(box + 1):-1].max())
    lo = float(df["low"].iloc[-(box + 1):-1].min())
    rng = hi - lo
    pct = (px - lo) / rng * 100 if rng > 0 else 50.0
    where = ("near resistance" if pct > 75 else
             "near support" if pct < 25 else "mid-range")

    wide = df.iloc[-(3 * box + 1):-1]
    wide_rng = float(wide["high"].max() - wide["low"].min())
    squeeze = rng / wide_rng if wide_rng > 0 else 1.0
    box_state = "consolidating (tight range)" if squeeze < 0.5 else "range normal"

    atr = _atr(df)
    atr_now, atr_avg = float(atr.iloc[-1]), float(atr.iloc[-50:].mean())
    vol = ("volatility high" if atr_now > atr_avg * 1.3 else
           "volatility low" if atr_now < atr_avg * 0.7 else "volatility normal")

    brk = ""
    if px > hi:
        brk = f" -- BREAKOUT above {hi:.2f}"
    elif px < lo:
        brk = f" -- BREAKDOWN below {lo:.2f}"

    return (f"{px:.2f}: {trend}. Range {lo:.2f}-{hi:.2f} last {box} bars, "
            f"price {where} ({pct:.0f}%). {box_state}. {vol}.{brk}")
