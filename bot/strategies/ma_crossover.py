from .base import Signal, Strategy


class MaCrossover(Strategy):
    """Trend-following: go long when fast SMA crosses above slow SMA, short on the reverse."""

    def on_candles(self, df) -> Signal:
        fast = int(self.params.get("fast", 20))
        slow = int(self.params.get("slow", 50))
        sl = self.params.get("sl_pips", 20)
        tp = self.params.get("tp_pips", 40)

        if len(df) < slow + 2:
            return Signal("none", "warming up")

        f = df["close"].rolling(fast).mean()
        s = df["close"].rolling(slow).mean()
        prev = f.iloc[-2] - s.iloc[-2]
        now = f.iloc[-1] - s.iloc[-1]

        if prev <= 0 < now:
            return Signal("buy", f"MA{fast} crossed above MA{slow}", sl, tp)
        if prev >= 0 > now:
            return Signal("sell", f"MA{fast} crossed below MA{slow}", sl, tp)
        return Signal("none", "no cross")
