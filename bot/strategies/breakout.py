"""Consolidation breakout with EMA/MA trend filter.

Covers what you asked for in one rule set:
- support / resistance  -> the top and bottom of the recent range (the "box")
- consolidation period  -> box range must be tighter than the wider recent range
- breakout entry        -> close pushes through the box edge
- trend filter          -> only long above a rising MA(ma_slow) with EMA(ema_fast)
                           on side; only short in the mirror case

params: ema_fast=8, ma_slow=66, lookback=20, squeeze_ratio=0.6, rr=2.0, buffer_pct=0.0
"""
from __future__ import annotations

from .base import Signal, Strategy


class ConsolidationBreakout(Strategy):
    def on_candles(self, df) -> Signal:
        ef = int(self.params.get("ema_fast", 8))
        ms = int(self.params.get("ma_slow", 66))
        lb = int(self.params.get("lookback", 20))
        squeeze_ratio = float(self.params.get("squeeze_ratio", 0.6))
        rr = float(self.params.get("rr", 2.0))
        buf = float(self.params.get("buffer_pct", 0.0)) / 100.0

        if len(df) < ms + 3 * lb + 5:
            return Signal("none", "warming up")

        close = df["close"]
        ema = close.ewm(span=ef, adjust=False).mean()
        ma = close.rolling(ms).mean()

        px = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])
        ma_now, ma_prev = float(ma.iloc[-1]), float(ma.iloc[-6])
        up = px > ma_now and ma_now > ma_prev and ema.iloc[-1] > ma_now
        dn = px < ma_now and ma_now < ma_prev and ema.iloc[-1] < ma_now
        if not (up or dn):
            return Signal("none", "no trend")

        box = df.iloc[-(lb + 1):-1]                 # range before the current bar
        hi, lo = float(box["high"].max()), float(box["low"].min())
        box_range = hi - lo
        wide = df.iloc[-(3 * lb + 1):-1]
        wide_range = float(wide["high"].max() - wide["low"].min())
        if wide_range <= 0 or box_range / wide_range > squeeze_ratio:
            return Signal("none", "not consolidating")

        if up and prev_close <= hi and px > hi * (1 + buf):
            return Signal("buy", f"breakout > {hi:.2f} (box {lo:.2f}-{hi:.2f})",
                          sl_price=lo, tp_price=px + rr * box_range)
        if dn and prev_close >= lo and px < lo * (1 - buf):
            return Signal("sell", f"breakdown < {lo:.2f} (box {lo:.2f}-{hi:.2f})",
                          sl_price=hi, tp_price=px - rr * box_range)
        return Signal("none", "no breakout")
