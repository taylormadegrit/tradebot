"""Minimal backtester with spread cost. Not a substitute for walk-forward analysis.

    python -m bot.backtest EURUSD ma_crossover

`run()` takes a symbol + strategy and returns a stats dict. Pass `df=` to
backtest an in-memory frame instead of data/<SYM>.csv (the Streamlit app does
this), and `detail=True` to also get the equity curve and per-trade log.
"""
from __future__ import annotations

import sys

import pandas as pd

from .config import ROOT
from .data import load_csv
from .instruments import spec
from .strategies import build as build_strategy


def run(symbol: str, strategy: str, params: dict | None = None,
        start_equity: float = 200.0, risk_pct: float = 0.5,
        spread_pips: float = 1.0, lookback: int = 1500,
        df: pd.DataFrame | None = None, detail: bool = False) -> dict:
    df = (load_csv(ROOT, symbol) if df is None else df).copy()
    df["_t_utc"] = pd.to_datetime(df["time"], utc=True)  # parse once, not per bar
    sp = spec(symbol)
    pip = sp["pip"]
    pv = sp["pip_value_per_lot"]
    strat = build_strategy(strategy, params)

    equity = start_equity
    peak = equity
    max_dd = 0.0
    pos = None  # dict: side, entry, sl, tp, lots
    wins = losses = 0
    gross_win = gross_loss = 0.0
    trades = 0
    curve: list[dict] = []
    log: list[dict] = []

    for i in range(60, len(df)):
        # bounded trailing window: enough for the opening range + any MA lookback
        window = df.iloc[max(0, i - lookback): i + 1]
        price = float(window["close"].iloc[-1])
        ts = window["_t_utc"].iloc[-1]

        if pos:
            hit_sl = price <= pos["sl"] if pos["side"] == "buy" else price >= pos["sl"]
            hit_tp = price >= pos["tp"] if pos["side"] == "buy" else price <= pos["tp"]
            if hit_sl or hit_tp:
                exit_px = pos["sl"] if hit_sl else pos["tp"]
                direction = 1 if pos["side"] == "buy" else -1
                pnl_pips = (exit_px - pos["entry"]) * direction / pip - spread_pips
                pnl = pnl_pips * pv * pos["lots"]
                equity += pnl
                trades += 1
                if pnl >= 0:
                    wins += 1
                    gross_win += pnl
                else:
                    losses += 1
                    gross_loss -= pnl
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - equity) / peak * 100)
                if detail:
                    log.append({
                        "time": ts, "side": pos["side"], "lots": pos["lots"],
                        "entry": round(pos["entry"], 5), "exit": round(exit_px, 5),
                        "result": "tp" if hit_tp else "sl", "pnl": round(pnl, 2),
                        "equity": round(equity, 2),
                    })
                pos = None

        if pos is None:
            sig = strat.on_candles(window)
            if sig.action in ("buy", "sell"):
                sl_pips = sig.sl_pips or 20
                tp_pips = sig.tp_pips or 40
                if sig.action == "buy":
                    sl = sig.sl_price if sig.sl_price is not None else price - sl_pips * pip
                    tp = sig.tp_price if sig.tp_price is not None else price + tp_pips * pip
                else:
                    sl = sig.sl_price if sig.sl_price is not None else price + sl_pips * pip
                    tp = sig.tp_price if sig.tp_price is not None else price - tp_pips * pip
                stop_pips = abs(price - sl) / pip
                raw_lots = (equity * risk_pct / 100) / max(stop_pips, 1e-9) / pv
                lots = round(min(raw_lots, 0.50), 3)   # 3dp so micro-sizes don't vanish
                if lots > 0 and stop_pips > 0:
                    pos = {"side": sig.action, "entry": price, "sl": sl, "tp": tp,
                           "lots": lots, "raw_lots": raw_lots}

        if detail:
            curve.append({"time": ts, "equity": round(equity, 2)})

    pf = (gross_win / gross_loss) if gross_loss else float("inf")
    out = {
        "symbol": symbol,
        "strategy": strategy,
        "bars": len(df),
        "trades": trades,
        "win_rate_pct": round(wins / trades * 100, 1) if trades else 0.0,
        "profit_factor": round(pf, 2),
        "return_pct": round((equity - start_equity) / start_equity * 100, 1),
        "max_drawdown_pct": round(max_dd, 1),
        "end_equity": round(equity, 2),
    }
    if detail:
        out["equity_curve"] = pd.DataFrame(curve)
        out["trades_log"] = pd.DataFrame(log)
    return out


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "EURUSD"
    strat = sys.argv[2] if len(sys.argv) > 2 else "ma_crossover"
    for k, v in run(sym, strat).items():
        print(f"{k:>18}: {v}")
