from dataclasses import dataclass
from typing import Optional


@dataclass
class Signal:
    action: str  # "buy" | "sell" | "none"
    reason: str = ""
    sl_pips: Optional[float] = None
    tp_pips: Optional[float] = None
    sl_price: Optional[float] = None  # absolute; wins over sl_pips when set
    tp_price: Optional[float] = None


class Strategy:
    """Stateless: given a candle DataFrame, return a Signal for the latest bar."""

    def __init__(self, **params):
        self.params = params

    def on_candles(self, df) -> Signal:  # df columns: time, open, high, low, close, volume
        raise NotImplementedError
