"""FastAPI wrapper: hosts the engine loop, exposes state + controls to the dashboard."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from . import db as dbmod
from .broker import PaperBroker, TradeLockerBroker
from .config import load_config
from .engine import Engine
from .risk import RiskManager

STATE: dict = {}


def make_broker(cfg: dict):
    if cfg["mode"] == "offline":
        p = cfg.get("paper") or {}
        return PaperBroker(
            cfg["_root"],
            start_balance=float(p.get("start_balance", 100_000.0)),
            spread_pips=p.get("spread_pips") or {},
            persist=bool(p.get("persist", True)),
        )
    b = cfg["broker"]
    return TradeLockerBroker(b["environment"], b["username"], b["password"], b["server"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    root: Path = cfg["_root"]
    con = dbmod.connect(root)
    engine = Engine(cfg, make_broker(cfg), RiskManager(cfg, root), con)
    STATE["engine"] = engine
    STATE["con"] = con
    task = asyncio.create_task(engine.run())
    try:
        yield
    finally:
        task.cancel()
        con.close()


app = FastAPI(lifespan=lifespan, title="tradebot")


@app.get("/state")
def state():
    eng = STATE.get("engine")
    return eng.snapshot() if eng else {"error": "starting"}


@app.post("/halt")
def halt():
    eng = STATE["engine"]
    (eng.cfg["_root"] / "HALT").write_text("halted via api\n", encoding="utf-8")
    result = {"ok": True, "halted": True}
    try:
        eng.broker.close_all()
        result["flattened"] = True
    except Exception as e:  # noqa: BLE001
        result.update(ok=False, error=repr(e))
    dbmod.log_event(STATE["con"], "halt", detail=result)
    return result


@app.post("/resume")
def resume():
    eng = STATE["engine"]
    f = eng.cfg["_root"] / "HALT"
    if f.exists():
        f.unlink()
    eng.risk.halted_reason = None
    dbmod.log_event(STATE["con"], "resume")
    return {"ok": True}
