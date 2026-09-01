import json
import sqlite3
import time
from pathlib import Path


def connect(root: Path) -> sqlite3.Connection:
    dbdir = root / "data"
    dbdir.mkdir(exist_ok=True)
    con = sqlite3.connect(dbdir / "bot.db", check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    _migrate(con)
    return con


def _migrate(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, kind TEXT, symbol TEXT, detail TEXT
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, symbol TEXT, side TEXT, lots REAL, price REAL,
            sl REAL, tp REAL, mode TEXT, broker_id TEXT, status TEXT
        );
        CREATE TABLE IF NOT EXISTS equity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, balance REAL, equity REAL
        );
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, symbol TEXT, side TEXT, lots REAL,
            entry REAL, exit REAL, pnl REAL, reason TEXT, opened REAL
        );
        """
    )
    con.commit()


def log_event(con: sqlite3.Connection, kind: str, symbol: str = "", detail=None) -> None:
    con.execute(
        "INSERT INTO events(ts,kind,symbol,detail) VALUES(?,?,?,?)",
        (time.time(), kind, symbol, json.dumps(detail) if detail is not None else None),
    )
    con.commit()


def recent_events(con: sqlite3.Connection, limit: int = 50):
    rows = con.execute(
        "SELECT ts,kind,symbol,detail FROM events ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        {"ts": r[0], "kind": r[1], "symbol": r[2], "detail": json.loads(r[3]) if r[3] else None}
        for r in rows
    ]


def log_trade(con: sqlite3.Connection, t: dict) -> None:
    con.execute(
        "INSERT INTO trades(ts,symbol,side,lots,entry,exit,pnl,reason,opened) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (t.get("closed", time.time()), t["symbol"], t["side"], t["lots"],
         t["entry"], t["exit"], t["pnl"], t.get("reason", ""), t.get("opened", 0.0)),
    )
    con.commit()


def recent_trades(con: sqlite3.Connection, limit: int = 30):
    rows = con.execute(
        "SELECT ts,symbol,side,lots,entry,exit,pnl,reason FROM trades "
        "ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        {"ts": r[0], "symbol": r[1], "side": r[2], "lots": r[3], "entry": r[4],
         "exit": r[5], "pnl": r[6], "reason": r[7]}
        for r in rows
    ]


def trade_stats(con: sqlite3.Connection):
    row = con.execute(
        "SELECT COUNT(*), COALESCE(SUM(pnl),0), "
        "COALESCE(SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END),0), "
        "COALESCE(SUM(CASE WHEN pnl>0 THEN pnl ELSE 0 END),0), "
        "COALESCE(SUM(CASE WHEN pnl<0 THEN -pnl ELSE 0 END),0) FROM trades"
    ).fetchone()
    n, net, wins, gross_win, gross_loss = row
    return {
        "n": n,
        "net_pnl": round(net, 2),
        "win_rate_pct": round(wins / n * 100, 1) if n else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
    }
