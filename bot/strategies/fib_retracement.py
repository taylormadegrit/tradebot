"""Fibonacci retracement -- golden-pocket trend continuation.

Find the most recent impulse leg (a swing between two pivots), draw the fib from
its start (0.0) to its end (1.0) using the TradingView convention, then trade the
pullback into the 0.5-0.618 "golden pocket" in the direction of the impulse.

Levels available (the set from the chart config screenshot):
    retracement : 0  0.236  0.382  0.5  0.618  0.786  0.886  1.0
    extensions  : 1.1  1.2  1.618
    negative    : -0.27  -0.618
Any param that names a level (`entry_near`, `entry_far`, `invalidate`,
`stop_x`, `tp_x`) accepts one of those numbers.

params (defaults):
    pivot=5            pivot strength for swing detection
    lookback=150       bars scanned for the impulse leg
    min_leg_atr=2.0    leg must span at least this many ATR(14) to count
    max_age=40         leg end must be within this many bars of now
    entry_near=0.618   shallow edge of the entry band
    entry_far=0.5      deep edge of the entry band
    invalidate=0.382   a close beyond this (deeper) kills the setup
    stop_x=0.0         stop at this fib line (0.0 = swing origin)
    stop_buf_atr=0.25  extra ATR beyond the stop line
    tp_x=1.618         target at this extension line
    trend_ma=50        0/None disables the SMA trend filter
"""
from __future__ import annotations

import numpy as np

from .base import Signal, Strategy
from .double_top import _swings

FIB_LEVELS = (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 0.886, 1.0,
              1.1, 1.2, 1.618, -0.27, -0.618)


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, n: int = 14) -> float:
    pc = close[:-1]
    tr = np.maximum.reduce([high[1:] - low[1:],
                            np.abs(high[1:] - pc),
                            np.abs(low[1:] - pc)])
    if len(tr) < n:
        return float(tr.mean()) if len(tr) else 0.0
    return float(tr[-n:].mean())


class FibRetracement(Strategy):
    def on_candles(self, df) -> Signal:
        p = self.params
        pivot = int(p.get("pivot", 5))
        lookback = int(p.get("lookback", 150))
        min_leg_atr = float(p.get("min_leg_atr", 2.0))
        max_age = int(p.get("max_age", 40))
        entry_near = float(p.get("entry_near", 0.618))
        entry_far = float(p.get("entry_far", 0.5))
        invalidate = float(p.get("invalidate", 0.382))
        stop_x = float(p.get("stop_x", 0.0))
        stop_buf_atr = float(p.get("stop_buf_atr", 0.25))
        tp_x = float(p.get("tp_x", 1.618))
        trend_ma = int(p.get("trend_ma", 50) or 0)

        need = max(lookback, trend_ma + 2, 4 * pivot + 6)
        if len(df) < need:
            return Signal("none", "warming up")

        w = df.iloc[-lookback:]
        high = w["high"].to_numpy(float)
        low = w["low"].to_numpy(float)
        close = w["close"].to_numpy(float)
        px = float(close[-1])
        prev = float(close[-2])
        atr = _atr(high, low, close)
        if atr <= 0:
            return Signal("none", "no volatility")

        sh = _swings(high, pivot, want_high=True)
        sl = _swings(low, pivot, want_high=False)
        if not sh or not sl:
            return Signal("none", "no swings yet")

        last_hi, last_lo = sh[-1], sl[-1]
        n = len(close)

        # The impulse leg = the most recent pivot and the latest opposite pivot
        # that precedes it. Direction of the leg = direction we trade the pullback.
        if last_hi > last_lo:                      # up-impulse -> long the dip
            prior = [i for i in sl if i < last_hi]
            if not prior:
                return Signal("none", "no leg start")
            start_i, end_i = prior[-1], last_hi
            start, end = low[start_i], high[end_i]
            direction = "buy"
        else:                                      # down-impulse -> short the bounce
            prior = [i for i in sh if i < last_lo]
            if not prior:
                return Signal("none", "no leg start")
            start_i, end_i = prior[-1], last_lo
            start, end = high[start_i], low[end_i]
            direction = "sell"

        rng = end - start                          # signed
        if abs(rng) < min_leg_atr * atr:
            return Signal("none", f"leg too small ({abs(rng) / atr:.1f} ATR)")
        if n - 1 - end_i > max_age:
            return Signal("none", f"leg stale ({n - 1 - end_i} bars old)")

        def line(x: float) -> float:
            return start + x * rng

        if trend_ma:
            ma = float(close[-trend_ma:].mean())
            if direction == "buy" and px < ma:
                return Signal("none", f"below MA{trend_ma} -- trend filter")
            if direction == "sell" and px > ma:
                return Signal("none", f"above MA{trend_ma} -- trend filter")

        near, far = line(entry_near), line(entry_far)
        zone_lo, zone_hi = min(near, far), max(near, far)
        stop = line(stop_x) - stop_buf_atr * atr * (1 if direction == "buy" else -1)
        target = line(tp_x)
        bad = line(invalidate)

        # setup already resolved?
        if direction == "buy":
            if px >= target:
                return Signal("none", "move already reached target")
            if px < bad:
                return Signal("none", f"retraced past {invalidate:g} -- setup dead")
            in_zone = zone_lo <= px <= zone_hi
            resuming = px > prev
            if in_zone and resuming:
                return Signal("buy",
                              f"fib golden-pocket long: leg {start:.2f}->{end:.2f}, "
                              f"pull to {entry_far:g}-{entry_near:g}",
                              sl_price=stop, tp_price=target)
            return Signal("none",
                          f"waiting: price {px:.2f}, zone {zone_lo:.2f}-{zone_hi:.2f}")
        else:
            if px <= target:
                return Signal("none", "move already reached target")
            if px > bad:
                return Signal("none", f"retraced past {invalidate:g} -- setup dead")
            in_zone = zone_lo <= px <= zone_hi
            resuming = px < prev
            if in_zone and resuming:
                return Signal("sell",
                              f"fib golden-pocket short: leg {start:.2f}->{end:.2f}, "
                              f"pull to {entry_far:g}-{entry_near:g}",
                              sl_price=stop, tp_price=target)
            return Signal("none",
                          f"waiting: price {px:.2f}, zone {zone_lo:.2f}-{zone_hi:.2f}")
