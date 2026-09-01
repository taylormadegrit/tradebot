"""Per-symbol contract details.

pip: the price increment treated as "1 pip / 1 point"
pip_value_per_lot: approx USD value of 1 pip for 1.0 lot (USD account)

!! The index and metal values below are PLACEHOLDERS based on common CFD conventions.
   Before trading them for real, open the instrument in TradeLocker and read its
   contract spec (contract size / tick value / min lot) and correct these numbers.
   HeroFX may also name the symbols differently (e.g. GOLD, DJ30, NDX100) -- add
   aliases as needed.
"""

DEFAULT = {"pip": 0.0001, "pip_value_per_lot": 10.0}

TABLE = {
    # --- FX majors (well established) ---
    "EURUSD": {"pip": 0.0001, "pip_value_per_lot": 10.0},
    "GBPUSD": {"pip": 0.0001, "pip_value_per_lot": 10.0},
    "AUDUSD": {"pip": 0.0001, "pip_value_per_lot": 10.0},
    "USDJPY": {"pip": 0.01, "pip_value_per_lot": 9.1},
    "USDCHF": {"pip": 0.0001, "pip_value_per_lot": 11.0},

    # --- metal: PLACEHOLDER (assumes 1 lot = 100 oz -> $10 per 0.1 move) ---
    "XAUUSD": {"pip": 0.1, "pip_value_per_lot": 10.0},
    "GOLD":   {"pip": 0.1, "pip_value_per_lot": 10.0},

    # --- US index CFDs: PLACEHOLDER (assumes $1 per index point per 1.0 lot) ---
    "US30":   {"pip": 1.0, "pip_value_per_lot": 1.0},
    "DJ30":   {"pip": 1.0, "pip_value_per_lot": 1.0},
    "US100":  {"pip": 1.0, "pip_value_per_lot": 1.0},
    "NAS100": {"pip": 1.0, "pip_value_per_lot": 1.0},
    "NDX100": {"pip": 1.0, "pip_value_per_lot": 1.0},
    "US500":  {"pip": 0.1, "pip_value_per_lot": 1.0},
}


def spec(symbol: str) -> dict:
    return TABLE.get(symbol.upper(), DEFAULT)
