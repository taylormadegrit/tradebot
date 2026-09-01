"""Alerts: a sound on the PC and/or a push to your phone.

Phone push works over any internet connection (wifi or cellular). The bot POSTs
to a relay and the relay pushes to an app on your phone.

config.yaml:

  alerts:
    sound: true
    sound_file: "F:/temp/alert.mp3"      # optional .wav or .mp3; empty = plain beep
    ntfy_topic: "taylor-tradebot-8f3k"    # install the "ntfy" app, subscribe to this name
    telegram_token: ""                    # optional: from @BotFather
    telegram_chat_id: ""                  # optional: your numeric chat id
    cooldown_seconds: 1800                # don't repeat the same alert within this
    discord_threads: true                 # per-ticker Discord thread so alerts don't mix

Every alert is stamped with the local date and time.
Test it:  python -m bot.notify
"""
from __future__ import annotations

import ctypes
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .config import ROOT
from .timez import stamp as _tz_stamp


def _beep(times: int = 2) -> None:
    try:
        import winsound

        for _ in range(times):
            winsound.Beep(880, 180)
            time.sleep(0.08)
    except Exception:  # noqa: BLE001  -- non-Windows / no audio
        print("\a", end="", flush=True)


def _play_file(path: str) -> None:
    """Play a .wav or .mp3. Runs in its own thread so it never blocks the engine."""
    p = Path(path)
    if not p.exists():
        _beep()
        return
    if p.suffix.lower() == ".wav":
        try:
            import winsound

            winsound.PlaySound(str(p), winsound.SND_FILENAME)
            return
        except Exception:  # noqa: BLE001  -- fall through to MCI
            pass
    try:
        # mp3 / m4a / anything (and wav as a fallback) via the Windows MCI layer
        alias = "tbsnd"
        mci = ctypes.windll.winmm.mciSendStringW
        mci(f'close {alias}', None, 0, None)
        if mci(f'open "{p}" type mpegvideo alias {alias}', None, 0, None) != 0:
            mci(f'open "{p}" alias {alias}', None, 0, None)  # let MCI infer the type
        mci(f'play {alias} wait', None, 0, None)
        mci(f'close {alias}', None, 0, None)
    except Exception:  # noqa: BLE001
        _beep()


def stamp() -> str:
    """UTC + US Eastern (EST/EDT) + US Pacific (PST/PDT), one line."""
    return _tz_stamp()


class Notifier:
    def __init__(self, cfg: dict | None):
        cfg = cfg or {}
        self.sound = bool(cfg.get("sound", True))
        sf = str(cfg.get("sound_file", "") or "")
        if sf and not os.path.isabs(sf):
            sf = str(ROOT / sf)          # relative paths resolve against the project root
        self.sound_file = sf
        self.ntfy_topic = str(cfg.get("ntfy_topic", "") or "")
        self.tg_token = str(cfg.get("telegram_token", "") or "")
        self.tg_chat = str(cfg.get("telegram_chat_id", "") or "")
        self.discord_on = bool(cfg.get("discord", True))
        self.discord_token = os.getenv("DISCORD_BOT_TOKEN", "")
        self.discord_channel = os.getenv("DISCORD_CHANNEL_ID", "")
        self.discord_threads = bool(cfg.get("discord_threads", True))
        self.cooldown = int(cfg.get("cooldown_seconds", 1800))
        self._last: dict[str, float] = {}
        self._thread_lock = threading.Lock()
        self._threads: dict[str, str] = self._load_threads()  # symbol -> thread id

    def _fresh(self, key: str) -> bool:
        now = time.time()
        if now - self._last.get(key, 0) < self.cooldown:
            return False
        self._last[key] = now
        return True

    def _sound(self) -> None:
        if not self.sound:
            return
        if self.sound_file:
            threading.Thread(target=_play_file, args=(self.sound_file,), daemon=True).start()
        else:
            _beep()

    def _ntfy(self, title: str, msg: str) -> None:
        if not self.ntfy_topic:
            return
        try:
            req = urllib.request.Request(
                f"https://ntfy.sh/{self.ntfy_topic}",
                data=msg.encode("utf-8"),
                headers={"Title": title},
            )
            urllib.request.urlopen(req, timeout=8)
        except Exception:  # noqa: BLE001
            pass

    def _telegram(self, title: str, msg: str) -> None:
        if not (self.tg_token and self.tg_chat):
            return
        try:
            data = json.dumps({"chat_id": self.tg_chat, "text": f"{title}\n{msg}"}).encode()
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{self.tg_token}/sendMessage",
                data=data, headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=8)
        except Exception:  # noqa: BLE001
            pass

    # -- Discord plumbing ------------------------------------------------
    @property
    def _discord_auth(self) -> dict:
        return {"Authorization": f"Bot {self.discord_token}", "User-Agent": "tradebot/0.1"}

    @staticmethod
    def _http(method: str, url: str, headers: dict, data: bytes | None = None,
              timeout: int = 15) -> tuple[int | None, dict | None]:
        """Returns (http_status, parsed_json). status is None on a network error."""
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:  # 4xx/5xx -- keep the code
            try:
                return e.code, json.loads(e.read() or b"null")
            except Exception:  # noqa: BLE001
                return e.code, None
        except Exception:  # noqa: BLE001  -- DNS/timeout/offline
            return None, None

    def _thread_store(self) -> Path:
        return ROOT / "data" / "discord_threads.json"

    def _load_threads(self) -> dict[str, str]:
        try:
            return json.loads(self._thread_store().read_text("utf-8"))
        except Exception:  # noqa: BLE001
            return {}

    def _save_threads(self) -> None:
        try:
            p = self._thread_store()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self._threads, indent=2), "utf-8")
        except Exception:  # noqa: BLE001
            pass

    def _create_thread(self, name: str) -> str | None:
        status, data = self._http(
            "POST",
            f"https://discord.com/api/v10/channels/{self.discord_channel}/threads",
            {**self._discord_auth, "Content-Type": "application/json"},
            json.dumps({"name": name, "type": 11,          # 11 = public thread
                        "auto_archive_duration": 10080}).encode(),
        )
        if status in (200, 201) and isinstance(data, dict) and data.get("id"):
            return str(data["id"])
        return None

    def _ensure_thread(self, symbol: str) -> str | None:
        """Thread id for this ticker, created + remembered on first use."""
        tid = self._threads.get(symbol)
        if tid:
            return tid
        with self._thread_lock:
            tid = self._threads.get(symbol)
            if not tid:
                tid = self._create_thread(f"{symbol} alerts")
                if tid:
                    self._threads[symbol] = tid
                    self._save_threads()
        return tid

    def _discord_send(self, channel_id: str, content: str,
                      image_path: str | None) -> tuple[int | None, dict | None]:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        img = Path(image_path) if image_path else None
        if img and img.exists():
            boundary = "----tradebot" + uuid.uuid4().hex
            blob = img.read_bytes()
            payload = json.dumps({
                "content": content,
                "attachments": [{"id": 0, "filename": img.name}],
            }).encode()
            body = b"".join([
                f"--{boundary}\r\n".encode(),
                b'Content-Disposition: form-data; name="payload_json"\r\n',
                b"Content-Type: application/json\r\n\r\n", payload, b"\r\n",
                f"--{boundary}\r\n".encode(),
                (f'Content-Disposition: form-data; name="files[0]"; '
                 f'filename="{img.name}"\r\n').encode(),
                b"Content-Type: image/png\r\n\r\n", blob, b"\r\n",
                f"--{boundary}--\r\n".encode(),
            ])
            return self._http("POST", url, {
                **self._discord_auth,
                "Content-Type": f"multipart/form-data; boundary={boundary}"},
                body, timeout=20)
        return self._http("POST", url, {
            **self._discord_auth, "Content-Type": "application/json"},
            json.dumps({"content": content}).encode(), timeout=8)

    def _discord(self, title: str, msg: str, image_path: str | None = None,
                 symbol: str | None = None) -> None:
        if not (self.discord_on and self.discord_token and self.discord_channel):
            return
        content = f"**{title}**\n{msg}"
        threaded = bool(symbol) and self.discord_threads
        target = self.discord_channel
        if threaded:
            target = self._ensure_thread(symbol) or self.discord_channel

        status, _ = self._discord_send(target, content, image_path)

        # thread was deleted / archived-away -> forget it, remake once, retry
        if threaded and target != self.discord_channel and status in (403, 404):
            self._threads.pop(symbol, None)
            self._save_threads()
            target = self._ensure_thread(symbol) or self.discord_channel
            status, _ = self._discord_send(target, content, image_path)

        # thread still unreachable -> don't lose the alert, post to the channel
        if threaded and target != self.discord_channel and (status is None or status >= 400):
            self._discord_send(self.discord_channel, content, image_path)

    def fire(self, key: str, title: str, msg: str,
             image_path: str | None = None, symbol: str | None = None) -> bool:
        """Alert unless the same key fired within cooldown. Returns True if sent.

        image_path, if given, is attached to the Discord message (the
        annotated "what the bot sees" chart). symbol, if given, routes the
        Discord post into that ticker's own thread so alerts don't mix.
        """
        if not self._fresh(key):
            return False
        body = f"[{stamp()}] {msg}"
        self._sound()
        self._ntfy(title, body)
        self._telegram(title, body)
        self._discord(title, body, image_path, symbol)
        return True


if __name__ == "__main__":
    from .config import load_config

    cfg = load_config()
    n = Notifier(cfg.get("alerts"))

    # Build a real annotated chart from whatever history is on disk, so this
    # test exercises the Discord image path end to end.
    img, sym = None, None
    try:
        import pandas as pd

        from .chart import render as _render
        from .commentary import describe as _describe
        from .scanner import scan_patterns as _scan

        for inst in cfg["instruments"]:
            s = inst["symbol"]
            csv = cfg["_root"] / "data" / f"{s}.csv"
            if not csv.exists():
                continue
            d = pd.read_csv(csv, parse_dates=["time"])
            v = {"read": _describe(s, d), "patterns": _scan(d)}
            img = _render(s, d, v, out_dir=cfg["_root"] / "data" / "charts")
            if img:
                sym = s
                break
    except Exception as e:  # noqa: BLE001
        print("chart skipped:", repr(e))

    if sym:
        text = ("Alerts are working. Sound + phone + Discord. The timestamp above shows "
                "UTC / Eastern (EST-EDT) / Pacific (PST-PDT); the attached image is what "
                f"the bot sees. This post should land in the '{sym} alerts' thread.")
    else:
        text = "Alerts are working (no ticker CSV found for a thread test)."

    sent = n.fire(f"test:{time.time()}", f"{sym or 'tradebot'} test", text,
                  image_path=str(img) if img else None, symbol=sym)
    print("fired at", stamp() if sent else "-- cooldown blocked, wait and retry",
          "| chart:", img or "none", "| thread:", n._threads.get(sym or "", "-"))
