"""One place that formats a moment in the timezones we care about:
UTC (the engine's own clock), US Eastern, and US Pacific.

The zone abbreviation is resolved from the tz database for that exact
instant, so it prints EDT / PDT through the summer and EST / PST through
the winter -- the "est/pdt" shown in Discord and on the dashboard is
always the correct one for the date, with no manual DST bookkeeping.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")     # EST / EDT
PT = ZoneInfo("America/Los_Angeles")  # PST / PDT


def _moment(ts: float | None) -> dt.datetime:
    if ts is None:
        return dt.datetime.now(UTC)
    return dt.datetime.fromtimestamp(ts, UTC)


def parts(ts: float | None = None) -> dict[str, str]:
    """Structured strings for the dashboard / JSON state."""
    now = _moment(ts)
    et, pt = now.astimezone(ET), now.astimezone(PT)
    return {
        "utc": now.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "et": et.strftime("%Y-%m-%d %H:%M:%S ") + et.tzname(),
        "pt": pt.strftime("%Y-%m-%d %H:%M:%S ") + pt.tzname(),
        "et_abbr": et.tzname(),   # "EST" or "EDT"
        "pt_abbr": pt.tzname(),   # "PST" or "PDT"
        "line": stamp(ts),
    }


def stamp(ts: float | None = None) -> str:
    """Single line used inside alert text: all three zones at once."""
    now = _moment(ts)
    et, pt = now.astimezone(ET), now.astimezone(PT)
    return (
        f"{now:%Y-%m-%d %H:%M:%S} UTC  |  "
        f"{et:%H:%M:%S} {et.tzname()} (New York)  |  "
        f"{pt:%H:%M:%S} {pt.tzname()} (Los Angeles)"
    )
