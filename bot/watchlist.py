"""Watchlist -- monitor-only tickers that alert every time they print a NEW HIGH.

No trading, no broker. Just OHLC from data/<SYMBOL>.csv (kept fresh by the
datafeed process from Yahoo), a rolling-high test, and the normal alert path:
sound + phone + the ticker's own Discord thread + the annotated chart.

config.yaml:

  watchlist:
    enabled: true
    lookback: 60          # "new high" = a high above the prior <lookback> bars
    tickers:
      - { symbol: MU,  yahoo: MU }     # Micron
      - { symbol: AMD, yahoo: AMD }    # AMD
      - { symbol: BE,  yahoo: BE }     # Bloom Energy

State (the per-ticker high we last alerted on) is persisted to
data/watchlist_state.json so a restart doesn't replay old highs.
"""
from __future__ import annotations

import json
from pathlib import Path

from .chart import render as render_chart
from .data import load_csv


class Watchlist:
    def __init__(self, cfg: dict, root: Path, notifier):
        wl = cfg.get("watchlist") or {}
        self.root = root
        self.notifier = notifier
        self.tickers = [t["symbol"] for t in wl.get("tickers", []) if t.get("symbol")]
        self.enabled = bool(wl.get("enabled", True)) and bool(self.tickers)
        self.lookback = int(wl.get("lookback", 60))
        self._state_path = root / "data" / "watchlist_state.json"
        self._hwm: dict[str, float] = self._load_state()   # symbol -> highest high alerted
        self.last: dict[str, dict] = {}                     # for the dashboard

    # -- state ---------------------------------------------------------------
    def _load_state(self) -> dict[str, float]:
        try:
            raw = json.loads(self._state_path.read_text("utf-8"))
            return {k: float(v) for k, v in raw.items()}
        except Exception:  # noqa: BLE001
            return {}

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(self._hwm, indent=2), "utf-8")
        except Exception:  # noqa: BLE001
            pass

    # -- checks ------------------------------------------------------------
    def check(self) -> None:
        if not self.enabled:
            return
        for sym in self.tickers:
            try:
                self._check_one(sym)
            except FileNotFoundError:
                self.last[sym] = {"sym": sym, "status": "no data yet"}
            except Exception as e:  # noqa: BLE001
                self.last[sym] = {"sym": sym, "error": repr(e)}

    def _check_one(self, sym: str) -> None:
        df = load_csv(self.root, sym)
        if len(df) < self.lookback + 2:
            self.last[sym] = {"sym": sym, "status": f"warming up ({len(df)} bars)"}
            return

        high = df["high"]
        prior = float(high.iloc[-(self.lookback + 1):-1].max())   # excludes current bar
        cur = float(high.iloc[-1])
        px = float(df["close"].iloc[-1])
        seen = self._hwm.get(sym)

        view = {
            "sym": sym,
            "price": round(px, 4),
            "bar_high": round(cur, 4),
            "prior_high": round(prior, 4),
            "to_high_pct": round((cur / prior - 1) * 100, 2) if prior else None,
            "new_high": False,
            "status": "watching",
        }

        # First time we ever see this ticker: record where it is, stay quiet.
        if seen is None:
            self._hwm[sym] = max(prior, cur)
            self._save_state()
            view["status"] = "seeded"
            self.last[sym] = view
            return

        ref = max(prior, seen)
        if cur > ref * (1 + 1e-6):
            self._hwm[sym] = cur
            self._save_state()
            read = (f"{px:.2f}: NEW HIGH {cur:.2f} -- cleared the prior "
                    f"{self.lookback}-bar high {prior:.2f} ({(cur / prior - 1) * 100:+.2f}%).")
            patterns = [f"resistance ~{prior:.2f} (prior high, broken)",
                        f"NEW HIGH {cur:.2f} just now"]
            img = None
            try:
                img = render_chart(sym, df, {"read": read, "patterns": patterns},
                                   out_dir=self.root / "data" / "charts")
            except Exception:  # noqa: BLE001
                img = None
            self.notifier.fire(f"{sym}:newhigh:{cur:.4f}", f"{sym} NEW HIGH", read,
                               image_path=str(img) if img else None, symbol=sym)
            view.update(new_high=True, status="NEW HIGH")

        self.last[sym] = view
