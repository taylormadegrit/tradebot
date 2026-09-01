"""Triangle breakouts -- descending and ascending.

descending triangle : flat support (equal swing lows) + falling swing highs
                      -> classic break is DOWN through support
ascending triangle  : flat resistance (equal swing highs) + rising swing lows
                      -> classic break is UP through resistance

Trendline slopes come from a least-squares fit to the swing points, normalised
to "fraction of price per bar" so the flat/sloping test is scale-free.

params: window=120, pivot=3, flat_slope=0.0004, trend_slope=0.0010, rr=1.5,
        want="descending"|"ascending"|"both"
"""
from __future__ import annotations

import numpy as np

from .base import Signal, Strategy
from .double_top import _swings


class TriangleBreakout(Strategy):
    def on_candles(self, df) -> Signal:
        window = int(self.params.get("window", 120))
        pivot = int(self.params.get("pivot", 3))
        flat = float(self.params.get("flat_slope", 0.0004))
        trend = float(self.params.get("trend_slope", 0.0010))
        rr = float(self.params.get("rr", 1.5))
        want = str(self.params.get("want", "descending"))

        if len(df) < window + 2 * pivot + 3:
            return Signal("none", "warming up")

        w = df.iloc[-(window + 2 * pivot):]
        highs = w["high"].to_numpy()
        lows = w["low"].to_numpy()
        px = float(w["close"].iloc[-1])
        prev = float(w["close"].iloc[-2])

        hi_idx = _swings(highs, pivot, want_high=True)
        lo_idx = _swings(lows, pivot, want_high=False)
        if len(hi_idx) < 2 or len(lo_idx) < 2:
            return Signal("none", "not enough pivots")

        def slope(idx, arr):
            x = np.array(idx, dtype=float)
            y = arr[idx]
            m = np.polyfit(x, y, 1)[0]
            return m / max(px, 1e-9)  # fraction of price per bar

        sh, slp = slope(hi_idx, highs), slope(lo_idx, lows)
        res_level = float(np.mean(highs[hi_idx]))
        sup_level = float(np.mean(lows[lo_idx]))

        if want in ("descending", "both") and abs(slp) < flat and sh < -trend:
            height = float(highs[hi_idx].max()) - sup_level
            if height > 0 and prev >= sup_level and px < sup_level:
                return Signal("sell",
                              f"descending triangle, support {sup_level:.2f} broke",
                              sl_price=res_level, tp_price=sup_level - rr * height)

        if want in ("ascending", "both") and abs(sh) < flat and slp > trend:
            height = res_level - float(lows[lo_idx].min())
            if height > 0 and prev <= res_level and px > res_level:
                return Signal("buy",
                              f"ascending triangle, resistance {res_level:.2f} broke",
                              sl_price=sup_level, tp_price=res_level + rr * height)

        return Signal("none", "no triangle break")
