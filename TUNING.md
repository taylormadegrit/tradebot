# tradebot -- tuning & analysis guide

There is no neural network to "train" here. Improving the bot means:

1. adjusting **parameters** in `config.yaml`
2. **backtesting** the change over history
3. keeping it only if it holds up **out-of-sample**
4. optionally adding new **detectors / strategies** in code

Work through it in that order. Most parameter changes make things worse -- the
backtest is there to catch that before it costs anyone money.

---

## 1. The knobs -- `config.yaml`

```yaml
instruments:
  - symbol: XAUUSD
    timeframe: 5m
    strategy: breakout           # ma_crossover | rsi_reversion | orb | breakout | double_top | triangle
    params: { fast: 20, slow: 50, sl_pips: 120, tp_pips: 240 }
    windows: [london_ny_overlap, london_pm_fix]
```

| Field | What it does |
|---|---|
| `strategy` | which rule set generates buy/sell signals for this instrument |
| `params` | strategy inputs -- see each strategy file in `bot/strategies/` for its names |
| `windows` | only trade during these sessions (names in `bot/sessions.py`) |
| `risk.risk_per_trade_pct` | % of equity risked per trade |
| `risk.max_position_lots` | hard ceiling on size, always enforced |
| `risk.daily_loss_halt_pct` | at this daily loss the bot flattens and stops |
| `data.granularity` | candle size the datafeed pulls (`M5` `M15` `M30` `H1`) |
| `data.refresh_seconds` | how often the datafeed re-pulls |
| `alerts.sound_file` | path to a `.wav`/`.mp3` (relative to the project folder) |
| `alerts.cooldown_seconds` | minimum gap before the same alert repeats |

Common strategy params:
- **breakout**: `ema_fast` (default 8), `ma_slow` (66), `lookback` (20),
  `squeeze_ratio` (0.6 -- lower = only tighter consolidations), `rr` (2.0)
- **orb**: `open` ("09:30"), `range_minutes` (15), `rr` (2.0), `tz`
- **double_top**: `pivot` (4), `tol_pct` (0.6), `max_gap` (60), `rr` (1.5)
- **triangle**: `window` (120), `flat_slope`, `trend_slope`, `rr`
- **ma_crossover**: `fast`, `slow`, `sl_pips`, `tp_pips`
- **rsi_reversion**: `period`, `oversold`, `overbought`, `sl_pips`, `tp_pips`

After any edit: `pm2 restart tradebot-bot`

---

## 2. Backtest a change

Get history, then run:

```powershell
.\.venv\Scripts\python.exe -m bot.fetch_oanda M15 5000
.\.venv\Scripts\python.exe -m bot.backtest XAUUSD breakout
```

Output:

```
            trades: 86
      win_rate_pct: 39.5
     profit_factor: 1.11     <- the number that matters
        return_pct: 5.9
  max_drawdown_pct: 8.2
```

Reading it:
- **profit factor** -- gross wins / gross losses. Below 1.0 = loses money.
  1.0-1.2 = noise. Want 1.3+ and expect real spread to knock ~0.1-0.2 off.
- **trades** -- under ~40 the result is luck, not signal.
- **max drawdown** -- the worst peak-to-valley drop. Small account = keep it low.
- **win rate** -- on its own it means nothing. A 35% win rate can be profitable;
  a 70% win rate can blow up. Judge by profit factor + drawdown.

---

## 3. Parameter sweep

Try a range and compare, instead of guessing one value:

```powershell
.\.venv\Scripts\python.exe -c "from bot.backtest import run; [print(sr, run('XAUUSD','breakout',{'squeeze_ratio':sr})) for sr in (0.4,0.5,0.6,0.7,0.8)]"
```

Then -- and this is the part people skip -- **re-test the best setting on a
different date range** (edit the CSV, or pull a different window with
`fetch_oanda`). If it only looks good on the data you tuned it on, it's
overfit. Throw it out.

---

## 4. Hour-of-day analysis

Which hours actually move a market:

```powershell
.\.venv\Scripts\python.exe -m bot.analyze_hours XAUUSD
```

Use the busy hours to pick `windows` in `config.yaml`. `bias` near zero means no
directional edge that hour -- only trade the hours with real range.

---

## 5. Add a new strategy

1. Copy `bot/strategies/breakout.py` to `bot/strategies/mything.py`
2. Rename the class, rewrite `on_candles(self, df) -> Signal`
3. Register it in `bot/strategies/__init__.py`:
   ```python
   from .mything import MyThing
   REGISTRY["mything"] = MyThing
   ```
4. Backtest: `python -m bot.backtest XAUUSD mything`
5. If it holds up out-of-sample, set `strategy: mything` in `config.yaml`

A `Signal` is: `Signal(action="buy"|"sell"|"none", reason=..., sl_price=..., tp_price=...)`
(or `sl_pips` / `tp_pips` for a fixed-distance stop).

---

## 6. Add a new detector to the live scan

`bot/scanner.py` -> `scan_patterns()` returns a list of short strings shown on
the dashboard and used for alerts. Add your check, append a string like
`"WEDGE forming, apex ~4520"`. If the string contains `BREAKOUT`, `BREAKDOWN`,
or `CONFIRMED`, it also fires a sound/Discord alert.

---

## 7. Tracking whether alerts were any good

The engine logs every event to `data/bot.db` (SQLite). Over time, compare what
the scanner flagged against what price did next. This is the honest feedback
loop -- weight the detectors that actually preceded moves, drop the ones that
didn't. (Not automated yet; query the `events` and `equity` tables.)

---

## Guardrails when tuning

- Never raise `risk_per_trade_pct` above ~1% or `max_position_lots` without a
  reason you can defend from a backtest.
- Keep `mode: offline` (or `demo`) while tuning. `live` needs a deliberate
  `I_UNDERSTAND_LIVE_RISK` file.
- A backtest with no spread/cost is a lie -- the built-in one models a small
  spread; don't remove it.
- More parameters = easier to overfit. Prefer simple rules that work okay
  across many settings over a fragile rule that's perfect at one.
