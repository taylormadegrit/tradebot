"""Keeps data/<SYM>.csv fresh so the scanner, commentary and watchlist run on
live prices instead of a static file. Runs as its own pm2 process.

  * traded instruments  -> OANDA          (config.yaml: data.*)
  * watchlist tickers   -> Yahoo          (config.yaml: watchlist.*)
  * economic calendar   -> ForexFactory   (config.yaml: calendar.*)
"""
from __future__ import annotations

import time

from .config import load_config
from .fetch_calendar import main as calendar_fetch
from .fetch_oanda import main as oanda_fetch
from .fetch_yahoo import main as yahoo_fetch


def loop() -> None:
    cfg = load_config()
    data = cfg.get("data", {}) or {}
    every = int(data.get("refresh_seconds", 120))
    gran = str(data.get("granularity", "M15"))
    bars = str(int(data.get("bars", 5000)))

    wl = cfg.get("watchlist") or {}
    wl_tickers = [t for t in wl.get("tickers", []) if t.get("symbol")]
    wl_on = bool(wl.get("enabled", True)) and bool(wl_tickers)
    wl_every = int(wl.get("refresh_seconds", 300))
    wl_interval = str(wl.get("interval", "15m"))
    wl_range = str(wl.get("range", "1mo"))
    wl_pairs = ",".join(f"{t.get('yahoo', t['symbol'])}:{t['symbol']}" for t in wl_tickers)

    cal = cfg.get("calendar") or {}
    cal_on = bool(cal.get("enabled", True))
    cal_every = int(cal.get("refresh_hours", 6)) * 3600

    print(f"datafeed: OANDA {gran} x{bars} every {every}s", flush=True)
    if wl_on:
        print(f"datafeed: watchlist {wl_pairs} ({wl_interval}/{wl_range}) every {wl_every}s",
              flush=True)
    if cal_on:
        print(f"datafeed: economic calendar every {cal_every // 3600}h", flush=True)

    wl_next = cal_next = 0.0
    while True:
        try:
            print("refresh", time.strftime("%H:%M:%S"), flush=True)
            oanda_fetch([gran, bars])
        except Exception as e:  # noqa: BLE001
            print("refresh error:", repr(e), flush=True)

        if wl_on and time.time() >= wl_next:
            try:
                print("watchlist refresh", time.strftime("%H:%M:%S"), flush=True)
                yahoo_fetch([wl_interval, wl_range, wl_pairs])
            except Exception as e:  # noqa: BLE001
                print("watchlist refresh error:", repr(e), flush=True)
            wl_next = time.time() + wl_every

        if cal_on and time.time() >= cal_next:
            try:
                print("calendar refresh", time.strftime("%H:%M:%S"), flush=True)
                calendar_fetch([])
            except Exception as e:  # noqa: BLE001
                print("calendar refresh error:", repr(e), flush=True)
            cal_next = time.time() + cal_every

        time.sleep(every)


if __name__ == "__main__":
    loop()
