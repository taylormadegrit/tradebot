"""Double top / double bottom reversal.

Finds the last two swing highs (or lows) of similar level within `max_gap` bars,
takes the neckline as the extreme between them, and signals on a neckline break.
Target is the measured move (pattern height) projected from the neckline.

params: pivot=4, tol_pct=0.6, max_gap=60, rr=1.5
"""
from __future__ import annotations

import numpy as np

from .base import Signal, Strategy


def _swings(arr: np.ndarray, pivot: int, want_high: bool) -> list[int]:
    out = []
    for i in range(pivot, len(arr) - pivot):
        seg = arr[i - pivot:i + pivot + 1]
        if (want_high and arr[i] == seg.max() and seg.argmax() == pivot) or (
            not want_high and arr[i] == seg.min() and seg.argmin() == pivot
        ):
            out.append(i)
    return out


class DoubleTopBottom(Strategy):
    def on_candles(self, df) -> Signal:
        pivot = int(self.params.get("pivot", 4))
        tol = float(self.params.get("tol_pct", 0.6)) / 100.0
        max_gap = int(self.params.get("max_gap", 60))
        rr = float(self.params.get("rr", 1.5))

        need = max_gap + 4 * pivot + 6
        if len(df) < need:
            return Signal("none", "warming up")

        w = df.iloc[-need:]
        highs = w["high"].to_numpy()
        lows = w["low"].to_numpy()
        close = float(w["close"].iloc[-1])
        prev = float(w["close"].iloc[-2])

        sh = _swings(highs, pivot, want_high=True)
        if len(sh) >= 2:
            a, b = sh[-2], sh[-1]
            pa, pb = highs[a], highs[b]
            if 0 < b - a <= max_gap and abs(pa - pb) / max(pa, pb) <= tol:
                neck = lows[a:b + 1].min()
                height = max(pa, pb) - neck
                if height > 0 and prev >= neck and close < neck:
                    return Signal("sell",
                                  f"double top ~{max(pa, pb):.2f}, neckline {neck:.2f}",
                                  sl_price=max(pa, pb), tp_price=neck - rr * height)

        sl_ = _swings(lows, pivot, want_high=False)
        if len(sl_) >= 2:
            a, b = sl_[-2], sl_[-1]
            la, lb = lows[a], lows[b]
            if 0 < b - a <= max_gap and abs(la - lb) / max(la, lb) <= tol:
                neck = highs[a:b + 1].max()
                height = neck - min(la, lb)
                if height > 0 and prev <= neck and close > neck:
                    return Signal("buy",
                                  f"double bottom ~{min(la, lb):.2f}, neckline {neck:.2f}",
                                  sl_price=min(la, lb), tp_price=neck + rr * height)

        return Signal("none", "no pattern")
