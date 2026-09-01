"""A one-line "what could this headline do to the price" read.

Two backends, tried in order:

  1. llm       -- a single Claude call over raw HTTPS (no SDK, same style as the
                  rest of the bot). Used only when ANTHROPIC_API_KEY is set in
                  .env. Best quality; falls back on any error.
  2. heuristic -- keyword + asset-class rules. No network, always available,
                  crude but honest.

Output is one plain line for the Discord post, e.g.
  "Impact: likely down for MU -- a guidance cut points to lower revenue; the
   open will show how much is priced in."
It is commentary, not a trade instruction, and never reaches order logic.
"""
from __future__ import annotations

import json
import os
import urllib.request

_METALS = {"XAUUSD", "XAGUSD", "GOLD", "SILVER", "XPTUSD", "XAU", "XAG"}
_INDICES = {"US30", "US100", "US500", "NAS100", "NDX100", "DJ30", "SPX500", "GER40", "UK100"}

_BULL = [
    "beats", "beat estimates", "tops estimates", "record high", "record revenue",
    "raises guidance", "raised outlook", "upgrade", "upgraded", "buyback",
    "surge", "surges", "soars", "jumps", "jump", "rally", "rallies", "rises",
    "gains", "climbs", "rebound", "wins contract", "approval", "approved",
    "breakthrough", "all-time high", "outperform", "strong demand", "blowout",
    "expands", "new deal", "partnership",
]
_BEAR = [
    "misses", "miss estimates", "cuts guidance", "cut outlook", "lowered guidance",
    "downgrade", "downgraded", "probe", "investigation", "lawsuit", "sues",
    "sec charges", "recall", "layoffs", "job cuts", "plunge", "plunges", "sinks",
    "warns", "warning", "halts", "fraud", "short seller", "short-seller",
    "bankruptcy", "data breach", "denies allegations", "allegations", "delay",
    "delays", "guidance cut", "weak demand", "slump", "slumps", "falls", "fall",
    "drops", "tumble", "tumbles", "slides", "selloff", "sell-off", "recession",
    "tariff", "tariffs",
]
# macro cues -- flip meaning for metals vs risk assets
_DOVISH = ["rate cut", "rate cuts", "dovish", "cooling inflation", "soft cpi",
           "weaker dollar", "dollar falls", "easing", "soft landing"]
_HAWKISH = ["rate hike", "rate hikes", "hawkish", "hot inflation", "hot cpi",
            "sticky inflation", "stronger dollar", "dollar rises", "tightening",
            "strong jobs", "hot jobs report"]
_HAVEN = ["war", "strike", "attack", "geopolitical", "sanctions", "escalation",
          "safe haven", "flight to safety", "crisis"]


def asset_class(symbol: str) -> str:
    s = symbol.upper()
    if s in _METALS:
        return "metal"
    if s in _INDICES or s.startswith(("US", "NAS", "SPX", "GER", "UK", "JP")):
        return "index"
    if len(s) == 6 and s.isalpha():
        return "currency"
    return "stock"


# --------------------------------------------------------------------------
def _count(text: str, words: list[str]) -> list[str]:
    return [w for w in words if w in text]


def heuristic(symbol: str, ac: str, headline: str) -> str:
    t = headline.lower()
    bull = _count(t, _BULL)
    bear = _count(t, _BEAR)
    dov = _count(t, _DOVISH)
    hawk = _count(t, _HAWKISH)
    haven = _count(t, _HAVEN)

    score = len(bull) - len(bear)
    if ac == "metal":
        score += len(dov) - len(hawk) + len(haven)     # gold likes cuts + fear
    elif ac in ("index", "stock"):
        score += len(dov) - len(hawk)
    elif ac == "currency":
        score += len(hawk) - len(dov)                    # USD-quoted: hawkish USD up

    cue = (bull + bear + dov + hawk + haven)
    why = f' ("{cue[0]}")' if cue else ""

    noun = {"metal": "the metal", "index": "the index",
            "currency": "the pair", "stock": symbol}.get(ac, symbol)

    if score > 0:
        return f"likely UP for {noun}{why} -- headline reads bullish; watch for follow-through, much may already be priced in."
    if score < 0:
        return f"likely DOWN for {noun}{why} -- headline reads bearish; the next session shows how much the market cares."
    return f"unclear for {noun} from the headline alone -- read the article; no obvious directional cue."


# --------------------------------------------------------------------------
def _llm(symbol: str, ac: str, headline: str, model: str, timeout: int) -> str | None:
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    system = (
        "You are a markets-desk assistant. Given ONE news headline and a ticker, "
        "reply with 1-2 sentences, under 45 words: the likely NEAR-TERM price "
        "direction for that specific instrument (up / down / little effect), the "
        "mechanism, and a short uncertainty note. No trade advice, no preamble, "
        "no disclaimer, plain text only."
    )
    user = f'Ticker: {symbol} ({ac}). Headline: "{headline}"'
    payload = json.dumps({
        "model": model,
        "max_tokens": 400,
        "output_config": {"effort": "low"},
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=payload,
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read())
    if data.get("stop_reason") == "refusal":
        return None
    text = " ".join(
        b.get("text", "").strip()
        for b in data.get("content", []) if b.get("type") == "text"
    ).strip()
    return text or None


# --------------------------------------------------------------------------
def impact_line(symbol: str, headline: str, *, model: str = "claude-opus-5",
                timeout: int = 15) -> str:
    ac = asset_class(symbol)
    try:
        got = _llm(symbol, ac, headline, model, timeout)
        if got:
            return f"**Impact:** {got}"
    except Exception:  # noqa: BLE001  -- never let this break a news post
        pass
    return f"**Impact:** {heuristic(symbol, ac, headline)}  _(rule-based)_"
