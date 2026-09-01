"""Broker interface + TradeLocker implementation + offline paper fallback.

All three expose the same methods:
    connect() -> bool
    account() -> {"balance": float, "equity": float}
    quote(symbol) -> Quote
    positions() -> list[Position]
    market_order(symbol, side, lots, sl=None, tp=None) -> dict
    close_all(symbol=None) -> None
"""
from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

from .instruments import spec


@dataclass
class Quote:
    symbol: str
    bid: float
    ask: float


@dataclass
class Position:
    symbol: str
    side: str  # "buy" | "sell"
    lots: float
    entry: float
    pnl: float
    id: str = ""
    sl: float | None = None
    tp: float | None = None
    opened: float = 0.0


class BrokerError(RuntimeError):
    pass


# --------------------------------------------------------------------------
class PaperBroker:
    """Offline simulator. No network.

    Prices come from the SAME candle files the strategies read (data/<SYM>.csv,
    last close), so fills, stops and targets line up with the signal. Positions
    are marked to market every tick; a bar whose high/low pierces the SL or TP
    closes the position and books the P&L. Balance, open positions and the
    closed-trade log persist to data/paper_state.json across restarts.

    The point: in `mode: offline` the bot really does place trades and build a
    demo track record with no broker attached.
    """

    def __init__(self, root, start_balance: float = 100_000.0,
                 spread_pips: dict | None = None, persist: bool = True):
        self.root = Path(root)
        self.start_balance = float(start_balance)
        self.spread_pips = {k.upper(): float(v) for k, v in (spread_pips or {}).items()}
        self.default_spread_pips = 1.0
        self.persist = bool(persist)
        self._state_path = self.root / "data" / "paper_state.json"

        self.balance = self.start_balance
        self.realized = 0.0
        self.n_closed = 0
        self._positions: list[Position] = []
        self.closed: list[dict] = []          # most-recent-first, capped
        self._price_cache: dict[str, tuple[float, dict]] = {}
        self._t = 0.0
        self.on_close = None                  # engine sets: callback(trade dict)
        self._load()

    # -- persistence ----------------------------------------------------
    def _load(self) -> None:
        if not self.persist:
            return
        try:
            s = json.loads(self._state_path.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return
        self.balance = float(s.get("balance", self.start_balance))
        self.realized = float(s.get("realized", 0.0))
        self.n_closed = int(s.get("n_closed", 0))
        self.closed = list(s.get("closed", []))[:50]
        for d in s.get("positions", []):
            self._positions.append(Position(
                d["symbol"], d["side"], float(d["lots"]), float(d["entry"]), 0.0,
                id=str(d.get("id", "")), sl=d.get("sl"), tp=d.get("tp"),
                opened=float(d.get("opened", 0.0))))

    def _save(self) -> None:
        if not self.persist:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps({
                "updated": time.time(),
                "balance": round(self.balance, 2),
                "realized": round(self.realized, 2),
                "n_closed": self.n_closed,
                "positions": [
                    {"symbol": p.symbol, "side": p.side, "lots": p.lots, "entry": p.entry,
                     "id": p.id, "sl": p.sl, "tp": p.tp, "opened": p.opened}
                    for p in self._positions
                ],
                "closed": self.closed[:50],
            }, indent=2), "utf-8")
        except Exception:  # noqa: BLE001
            pass

    # -- pricing --------------------------------------------------------
    def _bar(self, symbol: str) -> dict | None:
        """Last row of data/<SYM>.csv, cached by mtime."""
        p = self.root / "data" / f"{symbol}.csv"
        try:
            mtime = p.stat().st_mtime
        except OSError:
            return None
        hit = self._price_cache.get(symbol)
        if hit and hit[0] == mtime:
            return hit[1]
        last = None
        try:
            with p.open("r", newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    last = row
        except Exception:  # noqa: BLE001
            return None
        if not last:
            return None
        try:
            bar = {k: float(last[k]) for k in ("open", "high", "low", "close")}
        except (KeyError, ValueError):
            return None
        self._price_cache[symbol] = (mtime, bar)
        return bar

    def _mid(self, symbol: str) -> float:
        bar = self._bar(symbol)
        if bar:
            return bar["close"]
        # no data file yet -> gentle synthetic wander so the loop still runs
        self._t += 0.1
        return 100.0 + math.sin(self._t / 7.0)

    def _spread(self, symbol: str) -> float:
        pips = self.spread_pips.get(symbol.upper(), self.default_spread_pips)
        return pips * spec(symbol)["pip"]

    @staticmethod
    def _pnl(p: Position, mark: float) -> float:
        sp = spec(p.symbol)
        direction = 1.0 if p.side == "buy" else -1.0
        return (mark - p.entry) * direction / sp["pip"] * sp["pip_value_per_lot"] * p.lots

    # -- exits --------------------------------------------------------
    def _check_exits(self, symbol: str) -> None:
        bar = self._bar(symbol)
        if not bar:
            return
        hi, lo = bar["high"], bar["low"]
        for p in list(self._positions):
            if p.symbol != symbol:
                continue
            hit = None
            if p.side == "buy":
                if p.sl is not None and lo <= p.sl:
                    hit = ("sl", p.sl)
                elif p.tp is not None and hi >= p.tp:
                    hit = ("tp", p.tp)
            else:
                if p.sl is not None and hi >= p.sl:
                    hit = ("sl", p.sl)
                elif p.tp is not None and lo <= p.tp:
                    hit = ("tp", p.tp)
            if hit:
                self._close(p, hit[1], hit[0])

    def _close(self, p: Position, price: float, reason: str) -> None:
        pnl = round(self._pnl(p, price), 2)
        self.balance += pnl
        self.realized += pnl
        self.n_closed += 1
        try:
            self._positions.remove(p)
        except ValueError:
            return
        trade = {
            "symbol": p.symbol, "side": p.side, "lots": p.lots,
            "entry": round(p.entry, 5), "exit": round(price, 5), "pnl": pnl,
            "reason": reason, "opened": p.opened, "closed": time.time(),
        }
        self.closed = ([trade] + self.closed)[:50]
        self._save()
        if self.on_close:
            try:
                self.on_close(trade)
            except Exception:  # noqa: BLE001
                pass

    # -- broker surface ------------------------------------------------
    def connect(self) -> bool:
        return True

    def account(self) -> dict:
        floating = sum(self._pnl(p, self._mid(p.symbol)) for p in self._positions)
        return {
            "balance": round(self.balance, 2),
            "equity": round(self.balance + floating, 2),
            "realized": round(self.realized, 2),
            "closed_trades": self.n_closed,
            "open_trades": len(self._positions),
        }

    def quote(self, symbol: str) -> Quote:
        self._check_exits(symbol)                 # SL/TP before anything else
        mid = self._mid(symbol)
        half = self._spread(symbol) / 2
        for p in self._positions:
            if p.symbol == symbol:
                p.pnl = round(self._pnl(p, mid), 2)
        return Quote(symbol, mid - half, mid + half)

    def positions(self) -> list[Position]:
        return list(self._positions)

    def market_order(self, symbol: str, side: str, lots: float, sl=None, tp=None) -> dict:
        q = self.quote(symbol)
        entry = q.ask if side == "buy" else q.bid
        p = Position(symbol, side, float(lots), entry, 0.0,
                     id=str(int(time.time() * 1000)),
                     sl=(float(sl) if sl is not None else None),
                     tp=(float(tp) if tp is not None else None),
                     opened=time.time())
        self._positions.append(p)
        self._save()
        return {"id": p.id, "price": entry, "status": "filled"}

    def close_all(self, symbol: str | None = None) -> None:
        for p in list(self._positions):
            if symbol and p.symbol != symbol:
                continue
            self._close(p, self._mid(p.symbol), "manual")


# --------------------------------------------------------------------------
class TradeLockerBroker:
    """Wraps the community `tradelocker` package. Defaults to the demo environment.

    Method names below match that package's current public API. If your installed
    version differs, adjust the calls in the private helpers -- the class surface
    stays the same.
    """

    def __init__(self, environment: str, username: str, password: str, server: str):
        self._cfg = dict(environment=environment, username=username, password=password, server=server)
        self._tl = None

    def connect(self) -> bool:
        try:
            from tradelocker import TLAPI
        except ImportError as e:
            raise BrokerError("pip install tradelocker") from e
        if not self._cfg["username"] or not self._cfg["password"]:
            raise BrokerError("TL_USERNAME / TL_PASSWORD not set in .env")
        try:
            self._tl = TLAPI(**self._cfg)
        except Exception as e:  # noqa: BLE001
            raise BrokerError(f"TradeLocker auth failed: {e}") from e
        return True

    def _api(self):
        if self._tl is None:
            raise BrokerError("call connect() first")
        return self._tl

    def account(self) -> dict:
        st = self._api().get_account_state()
        bal = st.get("balance") or st.get("accountBalance") or 0
        eq = st.get("equity") or st.get("projectedBalance") or bal
        return {"balance": float(bal), "equity": float(eq)}

    def quote(self, symbol: str) -> Quote:
        iid = self._api().get_instrument_id_from_symbol_name(symbol)
        q = self._api().get_quotes(iid)
        return Quote(symbol, float(q["bid"]), float(q["ask"]))

    def positions(self) -> list[Position]:
        out: list[Position] = []
        df = self._api().get_all_positions()
        records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
        for p in records:
            side = str(p.get("side", "")).lower()
            out.append(
                Position(
                    symbol=str(p.get("symbol") or p.get("tradableInstrumentId")),
                    side="buy" if side in ("buy", "1", "b") else "sell",
                    lots=float(p.get("qty", 0) or 0),
                    entry=float(p.get("avgPrice", 0) or 0),
                    pnl=float(p.get("unrealizedPl", 0) or 0),
                    id=str(p.get("id", "")),
                )
            )
        return out

    def market_order(self, symbol: str, side: str, lots: float, sl=None, tp=None) -> dict:
        iid = self._api().get_instrument_id_from_symbol_name(symbol)
        oid = self._api().create_order(
            iid, quantity=lots, side=side, type_="market", stop_loss=sl, take_profit=tp
        )
        return {"id": str(oid), "status": "sent"}

    def close_all(self, symbol: str | None = None) -> None:
        for p in self.positions():
            if symbol and p.symbol != symbol:
                continue
            try:
                self._api().close_position(p.id)
            except Exception:  # noqa: BLE001
                pass
