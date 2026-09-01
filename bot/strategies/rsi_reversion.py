from .base import Signal, Strategy


def rsi(series, period: int = 14):
    delta = series.diff()
    up = delta.clip(lower=0).rolling(period).mean()
    down = (-delta.clip(upper=0)).rolling(period).mean()
    rs = up / down.replace(0, 1e-9)
    return 100 - 100 / (1 + rs)


class RsiReversion(Strategy):
    """Mean reversion: buy when RSI climbs back above oversold, sell on the mirror."""

    def on_candles(self, df) -> Signal:
        period = int(self.params.get("period", 14))
        lo = float(self.params.get("oversold", 30))
        hi = float(self.params.get("overbought", 70))
        sl = self.params.get("sl_pips", 25)
        tp = self.params.get("tp_pips", 25)

        if len(df) < period + 2:
            return Signal("none", "warming up")

        r = rsi(df["close"], period)
        if r.iloc[-2] < lo <= r.iloc[-1]:
            return Signal("buy", f"RSI back above {lo:.0f}", sl, tp)
        if r.iloc[-2] > hi >= r.iloc[-1]:
            return Signal("sell", f"RSI back below {hi:.0f}", sl, tp)
        return Signal("none", "no signal")
