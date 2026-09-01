"""Render "what the bot sees" as an annotated PNG for the Discord alert.

This is a picture of the exact numbers the engine already computed this
cycle -- candles, EMA/MA, the 20-bar range box, the last price, and any
fresh breakout -- NOT a screen capture and NOT a vision input. It exists
so an alert can *show* the setup instead of only describing it.

Degrades safely: if matplotlib is missing (e.g. the zero-install bundle
hasn't been rebuilt yet) render() returns None and the alert goes out as
text only.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .timez import stamp

_LEVEL = re.compile(r"(-?\d[\d,]*\.?\d*)")


def _keep_recent(folder: Path, keep: int = 40) -> None:
    pngs = sorted(folder.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in pngs[keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def render(symbol: str, df, view: dict, out_dir: Path, *,
           ema_fast: int = 8, ma_slow: int = 66, box: int = 20,
           bars: int = 140) -> Path | None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001  -- plotting stack not installed
        return None
    if df is None or len(df) < max(30, ma_slow // 2):
        return None

    full = df.reset_index(drop=True)
    d = full.tail(bars).reset_index(drop=True)
    ema = full["close"].ewm(span=ema_fast, adjust=False).mean().tail(bars).to_numpy()
    ma = full["close"].rolling(ma_slow).mean().tail(bars).to_numpy()

    has_time = "time" in d.columns
    x = mdates.date2num(d["time"]) if has_time else list(range(len(d)))
    step = (x[-1] - x[0]) / max(len(x) - 1, 1) if has_time else 1.0
    w = step * 0.6

    fig, ax = plt.subplots(figsize=(11, 5.6), dpi=110)
    fig.patch.set_facecolor("#0e1116")
    ax.set_facecolor("#0e1116")
    for s in ax.spines.values():
        s.set_color("#263041")
    ax.tick_params(colors="#8b98a9", labelsize=8)
    ax.grid(color="#263041", linewidth=0.4, alpha=0.5)

    o = d["open"].to_numpy(); h = d["high"].to_numpy()
    lo_ = d["low"].to_numpy(); c = d["close"].to_numpy()
    for i in range(len(d)):
        up = c[i] >= o[i]
        col = "#3fb950" if up else "#f85149"
        ax.plot([x[i], x[i]], [lo_[i], h[i]], color=col, linewidth=0.8, zorder=2)
        ax.add_patch(plt.Rectangle((x[i] - w / 2, min(o[i], c[i])), w,
                                   max(abs(c[i] - o[i]), 1e-6),
                                   facecolor=col, edgecolor=col, zorder=3))

    ax.plot(x, ema, color="#f0a020", linewidth=1.3, label=f"EMA{ema_fast}", zorder=4)
    ax.plot(x, ma, color="#58a6ff", linewidth=1.3, label=f"MA{ma_slow}", zorder=4)

    # 20-bar range box -- identical slice to bot/commentary.describe()
    rhi = float(full["high"].iloc[-(box + 1):-1].max())
    rlo = float(full["low"].iloc[-(box + 1):-1].min())
    ax.axhline(rhi, color="#8b98a9", linestyle="--", linewidth=0.9, zorder=1)
    ax.axhline(rlo, color="#8b98a9", linestyle="--", linewidth=0.9, zorder=1)
    ax.axhspan(rlo, rhi, color="#ffffff", alpha=0.04, zorder=0)
    ax.text(x[0], rhi, f" range high {rhi:.2f}", color="#8b98a9",
            va="bottom", ha="left", fontsize=8)
    ax.text(x[0], rlo, f" range low {rlo:.2f}", color="#8b98a9",
            va="top", ha="left", fontsize=8)

    # support / resistance lines lifted straight from the scanner output
    for line in view.get("patterns", []):
        low = line.lower()
        if low.startswith(("support", "resistance")):
            m = _LEVEL.search(line.split("(")[0])
            if not m:
                continue
            lvl = float(m.group(1).replace(",", ""))
            colr = "#f85149" if low.startswith("resist") else "#3fb950"
            ax.axhline(lvl, color=colr, linestyle=":", linewidth=1.0, alpha=0.8, zorder=1)
            ax.text(x[-1] + step, lvl, f" {line.split('(')[0].strip()}", color=colr,
                    va="center", ha="left", fontsize=8, clip_on=False)

    px = float(c[-1])
    ax.scatter([x[-1]], [px], color="#ffffff", s=30, zorder=6)
    ax.annotate(f" {px:.2f}", (x[-1], px), color="#ffffff", fontsize=9,
                va="center", ha="left", zorder=6, annotation_clip=False)

    read = view.get("read", "")
    brk = ""
    up_read = read.upper()
    if "BREAKOUT" in up_read:
        brk = "BREAKOUT"
    elif "BREAKDOWN" in up_read:
        brk = "BREAKDOWN"
    if brk:
        ax.annotate(brk, (x[-1], px),
                    xytext=(x[-1], rhi if brk == "BREAKOUT" else rlo),
                    color="#f0a020", fontsize=11, fontweight="bold",
                    ha="right", va="bottom" if brk == "BREAKOUT" else "top",
                    arrowprops=dict(arrowstyle="->", color="#f0a020"))

    ax.set_xlim(x[0] - step, x[-1] + step * 2)
    if has_time:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate(rotation=0, ha="center")

    ax.set_title(f"{symbol}  —  what the bot sees", color="#d7dde5",
                 fontsize=12, loc="left")
    leg = ax.legend(loc="upper left", fontsize=8, facecolor="#161b22",
                    edgecolor="#263041")
    for t in leg.get_texts():
        t.set_color("#d7dde5")

    caption = read if read else "(read unavailable)"
    fig.text(0.008, 0.02, caption, color="#8b98a9", fontsize=8, wrap=True)
    fig.text(0.008, 0.965, stamp(), color="#8b98a9", fontsize=8)
    fig.subplots_adjust(left=0.06, right=0.88, top=0.9, bottom=0.16)

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_{int(time.time())}.png"
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    _keep_recent(out_dir)
    return path
