"""Event-risk blackout filter.

No new entries in the window around high-impact economic releases (CPI, PCE,
NFP, FOMC, GDP, ISM ...). This is pure risk control: it can only ever BLOCK a
trade the strategy wanted to take, never open one. Data comes from
data/calendar.json (bot/fetch_calendar.py, refreshed by the datafeed process).

config.yaml:

  calendar:
    enabled: true
    impacts: [High]            # impact levels that trigger a blackout
    currencies: [USD]          # events in these currencies black out every instrument
    by_instrument:             # optional per-symbol override of `currencies`
      XAUUSD: [USD]
    before_minutes: 30
    after_minutes: 30
    on_missing: allow          # allow | block  -- when calendar.json is absent/stale
    stale_hours: 48
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

UTC = dt.timezone.utc


class CalendarGate:
    def __init__(self, cfg: dict, root: Path):
        c = cfg.get("calendar") or {}
        self.enabled = bool(c.get("enabled", True))
        self.impacts = {str(x).title() for x in (c.get("impacts") or ["High"])}
        self.currencies = {str(x).upper() for x in (c.get("currencies") or ["USD"])}
        self.by_instrument = {
            k.upper(): {str(x).upper() for x in v}
            for k, v in (c.get("by_instrument") or {}).items()
        }
        self.before = dt.timedelta(minutes=int(c.get("before_minutes", 30)))
        self.after = dt.timedelta(minutes=int(c.get("after_minutes", 30)))
        self.on_missing = str(c.get("on_missing", "allow")).lower()
        self.stale = dt.timedelta(hours=int(c.get("stale_hours", 48)))

        self._path = root / "data" / "calendar.json"
        self._mtime = 0.0
        self._events: list[dict] = []
        self._fetched: dt.datetime | None = None

    # -- data -----------------------------------------------------------------
    def _refresh(self) -> None:
        try:
            m = self._path.stat().st_mtime
        except OSError:
            self._events, self._fetched = [], None
            return
        if m == self._mtime:
            return
        try:
            data = json.loads(self._path.read_text("utf-8"))
            self._events = data.get("events", [])
            self._fetched = dt.datetime.fromisoformat(
                data["fetched_utc"].replace("Z", "+00:00"))
            self._mtime = m
        except Exception:  # noqa: BLE001
            self._events, self._fetched = [], None

    def _data_ok(self, now: dt.datetime) -> bool:
        return bool(self._events) and self._fetched is not None \
            and (now - self._fetched) <= self.stale

    def currencies_for(self, symbol: str | None) -> set[str]:
        if symbol and symbol.upper() in self.by_instrument:
            return self.by_instrument[symbol.upper()]
        return self.currencies

    # -- queries ------------------------------------------------------------
    def blackout(self, symbol: str | None = None,
                 now: dt.datetime | None = None) -> tuple[bool, str]:
        """(True, reason) if entries should be held right now."""
        if not self.enabled:
            return False, ""
        now = now or dt.datetime.now(UTC)
        self._refresh()
        if not self._data_ok(now):
            if self.on_missing == "block":
                return True, "calendar data missing/stale (on_missing=block)"
            return False, ""

        ccy = self.currencies_for(symbol)
        for ev in self._events:
            if ev.get("impact") not in self.impacts or ev.get("country") not in ccy:
                continue
            when = dt.datetime.fromtimestamp(ev["epoch"], UTC)
            if (when - self.before) <= now <= (when + self.after):
                mins = round((when - now).total_seconds() / 60)
                rel = f"in {mins}m" if mins > 0 else f"{-mins}m ago"
                return True, f"{ev['country']} {ev['impact']}: {ev['title']} ({rel})"
        return False, ""

    def status(self, now: dt.datetime | None = None) -> dict:
        """Dashboard view: freshness flag + the next few in-scope events."""
        now = now or dt.datetime.now(UTC)
        self._refresh()
        in_scope = set(self.currencies).union(*self.by_instrument.values()) \
            if self.by_instrument else set(self.currencies)
        nxt: list[dict] = []
        for ev in self._events:
            if ev.get("impact") not in self.impacts:
                continue
            when = dt.datetime.fromtimestamp(ev["epoch"], UTC)
            if when < now - self.after:
                continue
            nxt.append({**ev,
                        "in_minutes": round((when - now).total_seconds() / 60),
                        "blackout": ev.get("country") in in_scope})
            if len(nxt) >= 6:
                break
        return {
            "ok": self._data_ok(now),
            "fetched_utc": self._fetched.strftime("%Y-%m-%dT%H:%M:%SZ") if self._fetched else None,
            "window": f"-{int(self.before.total_seconds() // 60)}m / "
                      f"+{int(self.after.total_seconds() // 60)}m",
            "next": nxt,
        }
