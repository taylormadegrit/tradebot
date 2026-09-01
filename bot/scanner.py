"""Continuous pattern scan -- reports what's FORMING, not just what triggered.

Covers the full list: support/resistance levels, consolidation squeezes, double
tops/bottoms, ascending/descending triangles, and fresh breakouts. Runs on the
candle numbers every cycle -- no screenshots. Output is a list of short strings
the engine attaches to each instrument for the dashboard.
"""
from __future__ import annotations

import numpy as np

from .strategies.double_top import _swings


def scan_patterns(df, pivot: int = 4, tol_pct: float = 0.6,
                  box: int = 20, max_gap: int = 60) -> list[str]:
    need = max(box * 3, max_gap) + 4 * pivot + 6
    if len(df) < need:
        return ["scanning... (warming up)"]

    w = df.iloc[-need:]
    high = w["high"].to_numpy()
    low = w["low"].to_numpy()
    close = w["close"].to_numpy()
    px, prev = float(close[-1]), float(close[-2])
    tol = tol_pct / 100.0
    out: list[str] = []

    sh = _swings(high, pivot, want_high=True)
    sl = _swings(low, pivot, want_high=False)

    # support / resistance from nearest swings
    res = [high[i] for i in sh if high[i] > px]
    sup = [low[i] for i in sl if low[i] < px]
    if res:
        r = min(res)
        out.append(f"resistance ~{r:.2f} ({(r / px - 1) * 100:+.2f}%)")
    if sup:
        s = max(sup)
        out.append(f"support ~{s:.2f} ({(s / px - 1) * 100:+.2f}%)")

    # consolidation squeeze + fresh breakout
    bx = w.iloc[-(box + 1):-1]
    hi, lo = float(bx["high"].max()), float(bx["low"].min())
    wide = w.iloc[-(3 * box + 1):-1]
    wr = float(wide["high"].max() - wide["low"].min())
    if wr > 0 and (hi - lo) / wr < 0.5:
        out.append(f"CONSOLIDATION {lo:.2f}-{hi:.2f} (tight) -- breakout watch")
    if px > hi:
        out.append(f"BREAKOUT above {hi:.2f} just now")
    elif px < lo:
        out.append(f"BREAKDOWN below {lo:.2f} just now")

    # double top / bottom -- forming vs confirmed
    if len(sh) >= 2:
        a, b = sh[-2], sh[-1]
        pa, pb = high[a], high[b]
        if 0 < b - a <= max_gap and abs(pa - pb) / max(pa, pb) <= tol:
            neck = float(low[a:b + 1].min())
            st = "CONFIRMED (neckline broke)" if prev >= neck > px else "forming"
            out.append(f"double top ~{max(pa, pb):.2f}, neckline {neck:.2f} [{st}]")
    if len(sl) >= 2:
        a, b = sl[-2], sl[-1]
        la, lb = low[a], low[b]
        if 0 < b - a <= max_gap and abs(la - lb) / max(la, lb) <= tol:
            neck = float(high[a:b + 1].max())
            st = "CONFIRMED (neckline broke)" if prev <= neck < px else "forming"
            out.append(f"double bottom ~{min(la, lb):.2f}, neckline {neck:.2f} [{st}]")

    # triangles
    if len(sh) >= 2 and len(sl) >= 2:
        def slope(idx, arr):
            x = np.array(idx, dtype=float)
            return np.polyfit(x, arr[idx], 1)[0] / max(px, 1e-9)

        s_hi, s_lo = slope(sh, high), slope(sl, low)
        res_lvl, sup_lvl = float(np.mean(high[sh])), float(np.mean(low[sl]))
        if abs(s_lo) < 0.0008 and s_hi < -0.0006:
            out.append(f"DESCENDING TRIANGLE: support {sup_lvl:.2f} flat, highs falling "
                       f"-- bearish break watch")
        elif abs(s_hi) < 0.0008 and s_lo > 0.0006:
            out.append(f"ASCENDING TRIANGLE: resistance {res_lvl:.2f} flat, lows rising "
                       f"-- bullish break watch")

    return out or ["no notable pattern"]
