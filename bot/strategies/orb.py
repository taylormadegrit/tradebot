"""Opening-range breakout -- the classic structure for US index cash opens.

Take the high/low of the first `range_minutes` after the session open. Go long on
a close above the range, short on a close below it. Stop at the opposite edge of
the range; target is `rr` times the range width. Only the first breakout of the
day is taken.

params: tz, open ("HH:MM" local), range_minutes, rr
Assumes CSV timestamps are UTC. Uses a precomputed `_t_utc` column when the
caller supplies one (the backtester does), else parses `time` itself.
"""
from __future__ import annotations

import pandas as pd

from .base import Signal, Strategy


class OpeningRangeBreakout(Strategy):
    def on_candles(self, df) -> Signal:
        tz = self.params.get("tz", "America/New_York")
        open_hhmm = str(self.params.get("open", "09:30"))
        range_min = int(self.params.get("range_minutes", 15))
        rr = float(self.params.get("rr", 2.0))

        if len(df) < 5:
            return Signal("none", "warming up")

        t_utc = df["_t_utc"] if "_t_utc" in df.columns else pd.to_datetime(df["time"], utc=True)
        # only the last ~24h matters for one day's opening range -- keeps this O(1)
        cutoff = t_utc.iloc[-1] - pd.Timedelta(hours=24)
        keep = t_utc >= cutoff
        d = df.loc[keep]
        local = t_utc.loc[keep].dt.tz_convert(tz)

        last_day = local.iloc[-1].date()
        oh, om = map(int, open_hhmm.split(":"))
        sess_start = pd.Timestamp(
            year=last_day.year, month=last_day.month, day=last_day.day,
            hour=oh, minute=om, tz=tz,
        )
        range_end = sess_start + pd.Timedelta(minutes=range_min)

        same_day = local.dt.date.values == last_day
        in_range = same_day & (local.values >= sess_start.to_datetime64()) & (local.values < range_end.to_datetime64())
        after = same_day & (local.values >= range_end.to_datetime64())
        if not in_range.any() or not after.any():
            return Signal("none", "opening range not formed yet")

        hi = float(d.loc[in_range, "high"].max())
        lo = float(d.loc[in_range, "low"].min())
        rng = hi - lo
        if rng <= 0:
            return Signal("none", "flat opening range")

        after_df = d.loc[after]
        prior = after_df.iloc[:-1]
        if (prior["close"] > hi).any() or (prior["close"] < lo).any():
            return Signal("none", "breakout already taken today")

        price = float(d["close"].iloc[-1])
        if price > hi:
            return Signal("buy", f"ORB break > {hi:.2f}", sl_price=lo, tp_price=price + rr * rng)
        if price < lo:
            return Signal("sell", f"ORB break < {lo:.2f}", sl_price=hi, tp_price=price - rr * rng)
        return Signal("none", "inside opening range")
