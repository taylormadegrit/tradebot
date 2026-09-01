# tradebot

**Two ways to run this:**

1. **Streamlit playground** (`streamlit_app.py`) — a hosted backtest & analysis
   app: pick an instrument + strategy, run the backtester, read the chart the way
   the bot reads it, check news / economic-calendar context. No live trading, no
   secrets. `pip install -r requirements.txt && streamlit run streamlit_app.py`.
   Deploy to Streamlit Community Cloud — see **[DEPLOY.md](DEPLOY.md)**.
2. **The live engine** (below) — the always-on paper/demo trading bot. Needs a
   real machine/VPS and `requirements-engine.txt`.

---

Two background processes:

| Process | Language | Job |
|---|---|---|
| `bot/` (via `run_bot.py`) | Python + FastAPI | data -> strategy signal -> **risk gate** -> order. Talks to TradeLocker. |
| `dashboard/` (`server.js`) | Node + Express | live view of P&L / positions / logs, **KILL button**, alerts. |

Both are supervised by **pm2** so they restart on crash and relaunch on reboot.

## Modes (set in `config.yaml` -> `mode:`)

| mode | broker | needs credentials | use it for |
|---|---|---|---|
| `offline` | simulated `PaperBroker`, no network | no | first run, dev, seeing the loop work |
| `demo`   | HeroFX TradeLocker **demo** account | yes (`.env`) | weeks of paper trading before anything live |
| `live`   | HeroFX **live** account | yes + `I_UNDERSTAND_LIVE_RISK` file | only after demo holds up; tiny size |

`live` mode will refuse to start unless a file named `I_UNDERSTAND_LIVE_RISK` exists in this folder. That is deliberate.

## One-time setup

```powershell
cd D:\tradebot

# Python env
D:\Python311\python.exe -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Node deps
cd dashboard
npm install
cd ..

# pm2
npm i -g pm2
```

## Run (offline mode, safe)

```powershell
cd D:\tradebot
pm2 start ecosystem.config.js
pm2 logs                 # watch both processes
```

Dashboard: http://localhost:4000

```powershell
pm2 save                 # remember the current process list
pm2 stop all             # stop
```

Auto-start on login (Windows) is already set up via `pm2-windows-startup`:
a registry Run key (`HKCU\...\CurrentVersion\Run\PM2`) runs `pm2 resurrect` on
login, which restores whatever `pm2 save` last recorded. After changing the
running set, run `pm2 save` again. To remove: `pm2-startup uninstall`.
Note: this is login-triggered, not a boot service -- it starts when you sign in.

## Going to demo mode

1. Confirm the `tradelocker` Python package can log into your HeroFX **demo** account:

   ```python
   from tradelocker import TLAPI
   tl = TLAPI(environment="https://demo.tradelocker.com",
              username="<demo email>", password="<demo pw>", server="<server from login screen>")
   print(tl.get_all_accounts())
   ```

2. Copy `.env.example` to `.env` and fill in `TL_USERNAME` / `TL_PASSWORD` / `TL_SERVER`.
3. Set `mode: demo` in `config.yaml`.
4. `pm2 restart all`.

If step 1 fails, HeroFX blocks API trading and `broker.py` needs the Chrome-extension fallback instead.

## History data for backtests

Fastest path -- free proxy data from Yahoo Finance (gold future, Dow, Nasdaq-100):

```powershell
.\.venv\Scripts\python.exe -m bot.fetch_yahoo 1h 2y
# any tickers, incl. stocks:  interval  range  YSYM:OUT,YSYM:OUT
.\.venv\Scripts\python.exe -m bot.fetch_yahoo 1d 2y AAPL:AAPL,MSFT:MSFT,NVDA:NVDA
```

These are PROXIES, not HeroFX CFD prices (no broker spread/financing, index feed
only covers cash hours). Replace with real broker exports before trusting demo
numbers. Or hand-make CSVs at `data/<SYMBOL>.csv` with columns
`time,open,high,low,close,volume` (`time` ISO-8601, UTC).

Then:

```powershell
.\.venv\Scripts\python.exe -m bot.analyze_hours XAUUSD
.\.venv\Scripts\python.exe -m bot.backtest XAUUSD ma_crossover
.\.venv\Scripts\python.exe -m bot.backtest US30 orb
```

## Trading hours (the real "best hours")

"Best hours to trade" here means **session liquidity and volatility**, which is a
genuine, measurable effect for gold and US indices -- not numerology (see below).

- `bot/sessions.py` -- named windows in exchange-local time (DST handled via tz
  database). Each instrument in `config.yaml` lists `windows: [...]`; the engine
  will not open a new trade outside them. Presets: `london_ny_overlap`,
  `london_am`, `london_pm_fix`, `ny_equity_open_60m`, `ny_equity_open_90m`,
  `ny_1000_reversal`, `ny_equity_cash`.
- `bot/analyze_hours.py` -- measures which UTC hours actually move in your data:

  ```powershell
  .\.venv\Scripts\python.exe -m bot.analyze_hours XAUUSD
  ```

  `activity` (mean absolute return) clusters in specific hours; `bias` (mean
  return) usually does not -- i.e. you can predict *when* there's range, not
  reliably *which direction*.

Default config: **XAUUSD** on London/NY overlap + PM fix (MA crossover),
**US30** and **US100** on the first 90 min of the NY cash open (opening-range
breakout).

## About numerology

Not implemented, and won't be, as a signal source. Backtested, "wealth numbers"
and numerologically chosen hours produce noise -- there's no measurable edge, and
on a leveraged sub-$200 account that's a fast way to lose it. The time-of-day
logic above is the evidence-based version of the same idea. If you ever want a
purely personal, non-trading notes panel, that would live entirely outside the
order path and never gate a trade.

## Known stubs (wire to reality before trusting demo results)

- `bot/broker.py` TradeLocker method names follow the community package's current API; verify against your installed version.
- `bot/instruments.py` -- FX majors are solid; **XAUUSD / US30 / US100 values are
  placeholders**. Open each instrument in TradeLocker, read its contract spec
  (contract size / tick value), and correct them. HeroFX may also use different
  symbol names (GOLD, DJ30, NDX100) -- add aliases.
- Live candle aggregation is minimal; `bot/data.py` currently prefers CSV history. Add real candle pulls from the broker.
- `bot/backtest.py` is deliberately simple (bounded-window loop, one position at a
  time). For serious walk-forward / parameter work use `vectorbt` or `backtesting.py`.
