"""Per-ticker headlines -> the ticker's own Discord thread, always labelled NEWS.

Covers every symbol the bot knows about: the traded instruments AND the
watchlist tickers (and anything added later -- the list is derived, not hand
maintained). Source is Yahoo Finance's per-symbol RSS feed. This is context
only: it never touches order logic, it just posts a clearly-tagged headline.

config.yaml:

  news:
    enabled: true
    refresh_minutes: 20
    lookback_hours: 24        # first sight of a ticker: seed to now, post nothing older
    max_per_cycle: 3          # cap headlines per ticker per refresh
    label: "NEWS"
    map:                      # symbol -> Yahoo symbol for its news feed
      XAUUSD: "GC=F"
      US30: "^DJI"
      US100: "^NDX"
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

from .news_impact import impact_line
from .timez import stamp as tz_stamp

_FEED = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US"
_BUILTIN_MAP = {"XAUUSD": "GC=F", "US30": "^DJI", "US100": "^NDX",
                "NAS100": "^NDX", "GOLD": "GC=F", "US500": "^GSPC"}
_SEEN_KEEP = 60


def _publisher(link: str, fallback: str) -> str:
    try:
        host = urllib.parse.urlparse(link).netloc.lower()
        return host[4:] if host.startswith("www.") else host or fallback
    except Exception:  # noqa: BLE001
        return fallback


class NewsWatch:
    def __init__(self, cfg: dict, root: Path, notifier):
        n = cfg.get("news") or {}
        self.root = root
        self.notifier = notifier
        self.enabled = bool(n.get("enabled", True))
        self.every = int(n.get("refresh_minutes", 20)) * 60
        self.lookback = int(n.get("lookback_hours", 24)) * 3600
        self.max_per_cycle = int(n.get("max_per_cycle", 3))
        self.label = str(n.get("label", "NEWS")).strip() or "NEWS"
        self.impact = bool(n.get("impact", True))
        self.impact_model = str(n.get("impact_model", "claude-opus-5"))

        override = {k.upper(): str(v) for k, v in (n.get("map") or {}).items()}
        feeds: dict[str, str] = {}
        for i in cfg.get("instruments", []):
            s = str(i["symbol"]).upper()
            feeds[s] = override.get(s) or _BUILTIN_MAP.get(s, s)
        for t in (cfg.get("watchlist") or {}).get("tickers", []):
            s = str(t["symbol"]).upper()
            feeds[s] = override.get(s) or t.get("yahoo") or _BUILTIN_MAP.get(s, s)
        feeds.update(override)  # explicit map wins / can add extras
        self.feeds = feeds

        self._state_path = root / "data" / "news_state.json"
        self._state: dict[str, dict] = self._load_state()
        self.last: dict[str, dict] = {}
        self._busy = False
        self._next = 0.0

    # -- state -------------------------------------------------------------
    def _load_state(self) -> dict[str, dict]:
        try:
            return json.loads(self._state_path.read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(self._state, indent=2), "utf-8")
        except Exception:  # noqa: BLE001
            pass

    # -- fetch ------------------------------------------------------------
    @staticmethod
    def _fetch(yahoo_sym: str) -> list[dict]:
        url = _FEED.format(sym=urllib.parse.quote(yahoo_sym))
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            root = ET.fromstring(r.read())
        items: list[dict] = []
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            link = (it.findtext("link") or "").strip()
            guid = (it.findtext("guid") or link).strip()
            if not title or not guid:
                continue
            raw = (it.findtext("pubDate") or "").strip()
            try:
                epoch = parsedate_to_datetime(raw).timestamp()
            except Exception:  # noqa: BLE001
                epoch = time.time()
            items.append({"id": guid, "title": title, "link": link, "epoch": epoch})
        items.sort(key=lambda x: x["epoch"])
        return items

    # -- run ------------------------------------------------------------
    def check(self) -> None:
        """Cheap: kicks a background refresh only when one is due."""
        if not self.enabled or self._busy or time.time() < self._next:
            return
        self._busy = True
        self._next = time.time() + self.every
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            for sym, ysym in self.feeds.items():
                try:
                    self._run_one(sym, ysym)
                except Exception as e:  # noqa: BLE001
                    self.last.setdefault(sym, {})["error"] = repr(e)
        finally:
            self._busy = False

    def _run_one(self, sym: str, ysym: str) -> None:
        items = self._fetch(ysym)
        st = self._state.setdefault(sym, {})
        seen: list[str] = st.get("seen", [])
        seed = "seeded" not in st
        cutoff = time.time() - self.lookback

        fresh = [it for it in items if it["id"] not in seen and it["epoch"] >= cutoff]

        if seed:
            st["seen"] = [it["id"] for it in items][-_SEEN_KEEP:]
            st["seeded"] = True
            self._state[sym] = st
            self._save_state()
            newest = items[-1] if items else None
            self.last[sym] = {
                "sym": sym, "feed": ysym, "count_new": 0, "status": "seeded",
                "latest": newest["title"] if newest else None,
                "latest_epoch": newest["epoch"] if newest else None,
            }
            return

        posted = 0
        for it in fresh[-self.max_per_cycle:]:
            when = tz_stamp(it["epoch"])
            src = _publisher(it["link"], ysym)
            body = f"{it['title']}\n{it['link']}\n_{src} · {when}_"
            if self.impact:
                try:
                    body += "\n" + impact_line(sym, it["title"], model=self.impact_model)
                except Exception:  # noqa: BLE001  -- impact read must never block the post
                    pass
            self.notifier.fire(f"news:{sym}:{it['id']}",
                               f"[{self.label}] {sym}", body, symbol=sym)
            posted += 1

        for it in fresh:
            seen.append(it["id"])
        st["seen"] = seen[-_SEEN_KEEP:]
        self._state[sym] = st
        if fresh:
            self._save_state()

        newest = items[-1] if items else None
        self.last[sym] = {
            "sym": sym, "feed": ysym,
            "count_new": len(fresh),
            "posted": posted,
            "skipped": max(0, len(fresh) - posted),
            "status": f"{posted} posted" if posted else "no new headlines",
            "latest": newest["title"] if newest else None,
            "latest_epoch": newest["epoch"] if newest else None,
        }
