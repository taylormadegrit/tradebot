"""Time-of-day gating -- real, researched intraday windows for gold and US indices.

This is the legitimate version of "best hours to trade": session liquidity and
volatility, not numerology. Windows are defined in their local exchange timezone
and compared using the tz database, so daylight-saving shifts are automatic.
Engine logic stays in UTC.

Presets:
  london_ny_overlap   FX/gold deepest liquidity -- London and New York both open
  london_am           London morning session
  london_pm_fix       around the 3pm London gold fix
  ny_equity_open_60m  US index cash open, first 60 minutes
  ny_equity_open_90m  US index cash open, first 90 minutes  (default for US30/US100)
  ny_1000_reversal    the well-known ~10:00 ET turn window
  ny_equity_cash      full US cash session 09:30-16:00 ET
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

_WEEK = range(0, 5)  # Mon..Fri

PRESETS: dict[str, dict] = {
    "london_ny_overlap":  {"tz": "America/New_York", "start": "08:00", "end": "11:30", "days": _WEEK},
    "london_am":          {"tz": "Europe/London",    "start": "08:00", "end": "11:00", "days": _WEEK},
    "london_pm_fix":      {"tz": "Europe/London",    "start": "14:45", "end": "15:30", "days": _WEEK},
    "ny_equity_open_60m": {"tz": "America/New_York", "start": "09:30", "end": "10:30", "days": _WEEK},
    "ny_equity_open_90m": {"tz": "America/New_York", "start": "09:30", "end": "11:00", "days": _WEEK},
    "ny_1000_reversal":   {"tz": "America/New_York", "start": "09:55", "end": "10:30", "days": _WEEK},
    "ny_equity_cash":     {"tz": "America/New_York", "start": "09:30", "end": "16:00", "days": _WEEK},
}


def _in_window(now_utc: dt.datetime, spec: dict) -> bool:
    local = now_utc.astimezone(ZoneInfo(spec["tz"]))
    if local.weekday() not in spec["days"]:
        return False
    sh, sm = map(int, spec["start"].split(":"))
    eh, em = map(int, spec["end"].split(":"))
    start = local.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = local.replace(hour=eh, minute=em, second=0, microsecond=0)
    return start <= local < end


class Windows:
    """Holds the allowed windows for one instrument."""

    def __init__(self, names: list[str] | None):
        self.specs: list[tuple[str, dict]] = []
        for n in names or []:
            if n not in PRESETS:
                raise KeyError(f"unknown trading window '{n}'. known: {list(PRESETS)}")
            self.specs.append((n, PRESETS[n]))

    def open_now(self, now_utc: dt.datetime | None = None) -> tuple[bool, str]:
        if not self.specs:
            return True, "always"
        now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
        for name, spec in self.specs:
            if _in_window(now_utc, spec):
                return True, name
        return False, "closed"
