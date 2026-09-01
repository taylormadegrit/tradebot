"""Pull a structured economic calendar into data/calendar.json.

Source: ForexFactory's free weekly JSON (the feed most EAs use) -- no key, no
scraping of the editorial site. This file is what bot/calendar_gate.py reads to
decide the event-risk blackout windows.

    python -m bot.fetch_calendar
    python -m bot.fetch_calendar https://other.host/ff_calendar_thisweek.json
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.request

from .config import ROOT, load_config

DEFAULT_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"


def _to_utc(raw_when: str) -> dt.datetime | None:
    try:
        ts = dt.datetime.fromisoformat(raw_when)
    except ValueError:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def fetch(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = json.load(r)

    out: list[dict] = []
    for e in raw:
        ts = _to_utc(str(e.get("date", "")))
        if ts is None:
            continue
        out.append({
            "when_utc": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "epoch": ts.timestamp(),
            "country": (e.get("country") or "").upper(),        # e.g. USD, EUR
            "impact": (e.get("impact") or "").title(),          # High/Medium/Low/Holiday
            "title": e.get("title") or "",
            "forecast": e.get("forecast") or "",
            "previous": e.get("previous") or "",
        })
    out.sort(key=lambda x: x["epoch"])
    return out


def main(argv: list[str]) -> None:
    cfg = load_config().get("calendar") or {}
    url = (argv[0] if argv else cfg.get("url")) or DEFAULT_URL
    events = fetch(url)

    payload = {
        "fetched_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": url,
        "events": events,
    }
    path = ROOT / "data" / "calendar.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), "utf-8")

    hi = sum(1 for e in events if e["impact"] == "High")
    span = f"{events[0]['when_utc']} .. {events[-1]['when_utc']}" if events else "(empty)"
    print(f"calendar -> {path.name}  {len(events)} events, {hi} High  {span}")


if __name__ == "__main__":
    main(sys.argv[1:])
