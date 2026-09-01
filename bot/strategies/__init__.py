from .breakout import ConsolidationBreakout
from .double_top import DoubleTopBottom
from .fib_retracement import FibRetracement
from .ma_crossover import MaCrossover
from .orb import OpeningRangeBreakout
from .rsi_reversion import RsiReversion
from .triangle import TriangleBreakout

REGISTRY = {
    "ma_crossover": MaCrossover,
    "rsi_reversion": RsiReversion,
    "orb": OpeningRangeBreakout,
    "breakout": ConsolidationBreakout,
    "double_top": DoubleTopBottom,
    "triangle": TriangleBreakout,
    "fib_retracement": FibRetracement,
}


def build(name: str, params: dict | None):
    if name not in REGISTRY:
        raise KeyError(f"unknown strategy '{name}'. known: {list(REGISTRY)}")
    return REGISTRY[name](**(params or {}))
