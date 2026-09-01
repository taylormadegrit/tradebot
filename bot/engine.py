"""Main trading loop: poll -> candles -> strategy signal -> risk gate -> order."""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from . import db as dbmod
from .calendar_gate import CalendarGate
from .chart import render as render_chart
from .commentary import describe
from .news import NewsWatch
from .instruments import spec
from .notify import Notifier
from .scanner import scan_patterns
from .sessions import Windows
from .timez import parts as tz_parts
from .watchlist import Watchlist
from .strategies import build as build_strategy
from .strategies.base import Signal


class Engine:
    def __init__(self, cfg: dict, broker, risk, con):
        self.cfg = cfg
        self.broker = broker
        self.risk = risk
        self.con = con
        self.running = True
        self.last: dict = {}  # per-symbol view for the dashboard
        self.notifier = Notifier(cfg.get("alerts"))
        self.watchlist = Watchlist(cfg, cfg["_root"], self.notifier)
        self.calendar = CalendarGate(cfg, cfg["_root"])
        self.news = NewsWatch(cfg, cfg["_root"], self.notifier)
        self._plan = {
            i["symbol"]: {
                "cfg": i,
                "strat": build_strategy(i["strategy"], i.get("params")),
                "windows": Windows(i.get("windows")),
            }
            for i in cfg["instruments"]
        }

        # Paper sandbox: let closed sims land in the DB + Discord, and optionally
        # trade outside session windows so theories actually get exercised.
        paper = cfg.get("paper") or {}
        self.paper_any_time = (cfg["mode"] == "offline"
                               and bool(paper.get("ignore_windows", False)))
        if hasattr(self.broker, "on_close"):
            self.broker.on_close = self._on_trade_closed

    def _on_trade_closed(self, t: dict) -> None:
        try:
            dbmod.log_trade(self.con, t)
            dbmod.log_event(self.con, "trade_closed", t["symbol"], t)
        except Exception as e:  # noqa: BLE001
            dbmod.log_event(self.con, "trade_log_error", detail=repr(e))
        pnl = t["pnl"]
        self.notifier.fire(
            f"close:{t['symbol']}:{t['closed']:.0f}",
            f"{t['symbol']} {t['reason'].upper()} — paper close  {pnl:+.2f}",
            f"{t['side']} {t['lots']} @ {t['entry']} -> {t['exit']}   P&L {pnl:+.2f}",
            symbol=t["symbol"],
        )

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        try:
            acct = self.broker.account()
        except Exception as e:  # noqa: BLE001
            acct = {"balance": None, "equity": None, "error": repr(e)}
        try:
            positions = [p.__dict__ for p in self.broker.positions()]
        except Exception as e:  # noqa: BLE001
            positions = [{"error": repr(e)}]
        halted_reason = self.risk.halted_reason or (
            "HALT file" if self.risk.halt_file() else None
        )
        return {
            "ts": time.time(),
            "now": tz_parts(),
            "mode": self.cfg["mode"],
            "running": self.running and not halted_reason,
            "halted_reason": halted_reason,
            "account": acct,
            "positions": positions,
            "trades": dbmod.recent_trades(self.con, 25),
            "trade_stats": dbmod.trade_stats(self.con),
            "instruments": self.last,
            "watchlist": self.watchlist.last,
            "news": self.news.last,
            "calendar": {
                **self.calendar.status(),
                "blackout": {s: (self.calendar.blackout(s)[1] or None) for s in self._plan},
            },
            "events": dbmod.recent_events(self.con, 40),
        }

    # ------------------------------------------------------------------
    async def run(self):
        try:
            self.broker.connect()
            dbmod.log_event(self.con, "engine_start", detail={"mode": self.cfg["mode"]})
        except Exception as e:  # noqa: BLE001
            dbmod.log_event(self.con, "connect_error", detail=repr(e))
            self.last["_error"] = repr(e)

        poll = int(self.cfg.get("poll_seconds", 15))
        while True:
            try:
                await self._tick()
                self.last.pop("_error", None)
            except Exception as e:  # noqa: BLE001  -- keep the loop alive
                dbmod.log_event(self.con, "tick_error", detail=repr(e))
                self.last["_error"] = repr(e)
            await asyncio.sleep(poll)

    # ------------------------------------------------------------------
    async def _tick(self):
        # Monitor-only watchlist: runs every poll, independent of trading state.
        try:
            self.watchlist.check()
        except Exception as e:  # noqa: BLE001
            dbmod.log_event(self.con, "watchlist_error", detail=repr(e))

        # Per-ticker news: self-throttled, fetches in the background.
        try:
            self.news.check()
        except Exception as e:  # noqa: BLE001
            dbmod.log_event(self.con, "news_error", detail=repr(e))

        acct = self.broker.account()
        equity = float(acct["equity"] or 0)
        self.risk.new_day_rollover(equity)

        self.con.execute(
            "INSERT INTO equity(ts,balance,equity) VALUES(?,?,?)",
            (time.time(), acct.get("balance"), equity),
        )
        self.con.commit()

        # Global daily-loss halt: flatten once, then idle until tomorrow.
        if not self.risk.check_daily_loss(equity):
            if self.broker.positions():
                self.broker.close_all()
                dbmod.log_event(self.con, "daily_halt_flatten", detail=self.risk.halted_reason)
                self.notifier.fire(f"dailyhalt:{time.time()}", "tradebot HALTED",
                                   f"Daily loss limit hit. Flattened. {self.risk.halted_reason}")
            self.running = False
            return

        if self.risk.halt_file():
            self.running = False
            return
        self.running = True

        open_positions = self.broker.positions()
        open_symbols = {p.symbol for p in open_positions}
        open_count = len(open_positions)

        for symbol, plan in self._plan.items():
            strat = plan["strat"]
            candles = self._candles(symbol)
            sig: Signal = strat.on_candles(candles)
            q = self.broker.quote(symbol)
            open_ok, window = plan["windows"].open_now()
            params = plan["cfg"].get("params", {}) or {}
            try:
                read = describe(symbol, candles,
                                ema_fast=int(params.get("ema_fast", 8)),
                                ma_slow=int(params.get("ma_slow", 66)))
            except Exception as e:  # noqa: BLE001
                read = f"read unavailable: {e!r}"
            try:
                patterns = scan_patterns(candles)
            except Exception as e:  # noqa: BLE001
                patterns = [f"scan unavailable: {e!r}"]

            view = {
                "bid": round(q.bid, 5),
                "ask": round(q.ask, 5),
                "signal": sig.action,
                "reason": sig.reason,
                "window": window,
                "read": read,
                "patterns": patterns,
                "has_position": symbol in open_symbols,
            }
            self.last[symbol] = view

            # Rendered once per symbol per tick, only if an alert actually goes
            # out. It's a picture of the numbers above -- not a screen capture.
            _chart: list = []

            def chart_path() -> str | None:
                if not _chart:
                    try:
                        p = render_chart(
                            symbol, candles, view,
                            ema_fast=int(params.get("ema_fast", 8)),
                            ma_slow=int(params.get("ma_slow", 66)),
                            out_dir=self.cfg["_root"] / "data" / "charts",
                        )
                    except Exception:  # noqa: BLE001  -- never block an alert
                        p = None
                    _chart.append(str(p) if p else None)
                return _chart[0]

            # phone / sound alert on fresh breakouts and confirmed patterns
            for line in patterns:
                up = line.upper()
                if "BREAKOUT" in up or "BREAKDOWN" in up or "CONFIRMED" in up:
                    self.notifier.fire(f"{symbol}:{line[:48]}", f"{symbol} pattern",
                                       line, image_path=chart_path(), symbol=symbol)

            if sig.action not in ("buy", "sell") or symbol in open_symbols:
                continue

            if not open_ok and not self.paper_any_time:
                view["blocked"] = f"outside trading window ({window})"
                continue
            if not open_ok:
                view["window"] = f"{window} (paper: trading anyway)"

            blk, why = self.calendar.blackout(symbol)
            if blk:
                view["blocked"] = f"event blackout -- {why}"
                self.notifier.fire(f"{symbol}:blackout:{why[:40]}",
                                   f"{symbol} entry held", f"Skipping entry: {why}",
                                   symbol=symbol)
                dbmod.log_event(self.con, "calendar_blackout", symbol, {"reason": why})
                continue

            ok, reason = self.risk.gate(equity=equity, open_count=open_count)
            if not ok:
                view["blocked"] = reason
                continue

            sp = spec(symbol)
            pip = sp["pip"]
            entry = q.ask if sig.action == "buy" else q.bid
            sl_pips = sig.sl_pips or 20
            tp_pips = sig.tp_pips or 40
            if sig.action == "buy":
                sl, tp = entry - sl_pips * pip, entry + tp_pips * pip
            else:
                sl, tp = entry + sl_pips * pip, entry - tp_pips * pip
            # strategy-supplied absolute levels win (e.g. opening-range breakout)
            if sig.sl_price is not None:
                sl = sig.sl_price
            if sig.tp_price is not None:
                tp = sig.tp_price

            lots = self.risk.size_lots(equity, entry, sl, sp["pip_value_per_lot"], pip)
            if lots <= 0:
                view["blocked"] = "computed size = 0"
                continue

            res = self.broker.market_order(symbol, sig.action, lots, sl=sl, tp=tp)
            self.con.execute(
                "INSERT INTO orders(ts,symbol,side,lots,price,sl,tp,mode,broker_id,status) "
                "VALUES(?,?,?,?,?,?,?,?,?,?)",
                (time.time(), symbol, sig.action, lots, entry, sl, tp,
                 self.cfg["mode"], str(res.get("id", "")), res.get("status", "")),
            )
            self.con.commit()
            dbmod.log_event(
                self.con, "order", symbol,
                {"side": sig.action, "lots": lots, "entry": round(entry, 5), "reason": sig.reason},
            )
            self.notifier.fire(
                f"order:{time.time()}", f"tradebot {sig.action.upper()} {symbol}",
                f"{sig.action} {lots} lots @ {entry:.2f}  SL {sl:.2f}  TP {tp:.2f}  ({sig.reason})",
                image_path=chart_path(), symbol=symbol,
            )
            open_symbols.add(symbol)
            open_count += 1

    # ------------------------------------------------------------------
    def _candles(self, symbol: str):
        """CSV history if present, else a 1-row frame so strategies just warm up."""
        from .data import load_csv

        try:
            return load_csv(self.cfg["_root"], symbol)
        except (FileNotFoundError, ValueError):
            import pandas as pd

            q = self.broker.quote(symbol)
            mid = (q.bid + q.ask) / 2
            return pd.DataFrame(
                [{"time": dt.datetime.utcnow(), "open": mid, "high": mid,
                  "low": mid, "close": mid, "volume": 0}]
            )
