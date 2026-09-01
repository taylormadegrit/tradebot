# tradebot -- team install guide

A self-hosted market-analysis bot for gold (XAU/USD), US30, and NAS100. It pulls
live candles from OANDA, runs continuous pattern analysis, shows a live dashboard,
and fires alerts (sound + Discord + optional phone push).

You are installing your **own local copy**. It runs entirely on your machine.

---

## Already done for you (do NOT redo these)

These are built into the code you received -- no setup needed:

- OANDA data integration, auto-refresh loop
- All strategies and the pattern scanner (breakout, consolidation, double
  top/bottom, triangles, S/R, opening-range breakout, MA crossover, RSI)
- The backtester and the hour-of-day analyzer
- The alert sound file `assets/kaching.wav` (already cleaned/encoded -- you do
  **not** need ffmpeg)
- The Discord bot itself (one shared bot -- you just need the token from the owner)
- The dashboard and the 3-process supervised setup

## What you DO need to do

1. Install Python 3.11, Node.js 20+, and pm2
2. Unzip the project
3. Create the Python venv + install deps
4. Install the dashboard deps
5. Get your OWN free OANDA practice account + API token
6. Fill in `.env`
7. Start it with pm2

About 15 minutes.

---

## Step 1 -- Prerequisites

Install if you don't have them:

- **Python 3.11** -- https://www.python.org/downloads/release/python-3119/
  (tick "Add python.exe to PATH" in the installer)
- **Node.js 20 LTS or newer** -- https://nodejs.org/
- **pm2** -- after Node is installed, open PowerShell and run:
  ```powershell
  npm install -g pm2
  ```

Check they work:
```powershell
python --version      # 3.11.x
node --version         # v20+ 
pm2 --version
```

## Step 2 -- Unzip

Put the folder somewhere stable, e.g. `D:\tradebot` or `C:\Users\<you>\tradebot`.
All commands below assume you are **inside that folder** in PowerShell:
```powershell
cd D:\tradebot
```

## Step 3 -- Python environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Step 4 -- Dashboard dependencies

```powershell
cd dashboard
npm install
cd ..
```

## Step 5 -- Your OANDA practice account (free)

1. Go to https://www.oanda.com/ -> **open a free account** -> choose
   **"Practice"** (demo, fake money). No deposit.
2. Log in -> **Hub** (top nav) -> **Manage funds** area -> **API Access** /
   **"OANDA API"** -> **Generate** a personal access token.
3. Copy that token. That's your `OANDA_TOKEN`.
4. You do NOT need to find your account id -- the bot discovers it. (If you want
   to set it anyway: it's shown in the Hub, format `101-001-XXXXXXXX-001`.)

## Step 6 -- Fill in `.env`

```powershell
copy .env.example .env
notepad .env
```

Fill in:
- `OANDA_TOKEN=` -> the token from step 5
- `OANDA_ENV=practice` -> leave as-is
- `OANDA_ACCOUNT_ID=` -> leave blank (auto) or paste it

Discord (optional -- for alerts in a channel):
- `DISCORD_BOT_TOKEN=` -> ask the bot owner for this (shared)
- `DISCORD_CHANNEL_ID=` -> the channel YOU want alerts in. In Discord: User
  Settings -> Advanced -> enable **Developer Mode**, then right-click your
  channel -> **Copy Channel ID**.
- `DISCORD_APP_ID` / `DISCORD_PUBLIC_KEY` -> owner can share these; not required
  for alerts.

Leave the `TL_*` lines blank unless you personally trade through TradeLocker.

Save and close.

Quick check that OANDA works:
```powershell
.\.venv\Scripts\python.exe -m bot.fetch_oanda M15 500
```
You should see `XAUUSD.csv`, `US30.csv`, `US100.csv` written with bar counts.

## Step 7 -- Start it

```powershell
pm2 start ecosystem.config.js
pm2 save
pm2 logs                 # watch all 3 processes; Ctrl+C to stop watching
```

Open the dashboard: **http://localhost:4000**

You should see three processes online:
- `tradebot-bot` -- the analysis engine (port 8787)
- `tradebot-dashboard` -- the web UI (port 4000)
- `tradebot-datafeed` -- refreshes OANDA data every 2 minutes

Test the alert sound + Discord:
```powershell
.\.venv\Scripts\python.exe -m bot.notify
```

## Step 8 -- Auto-start on login (optional)

```powershell
npm install -g pm2-windows-startup
pm2-startup install
pm2 save
```
Now pm2 relaunches the bot when you sign in. Undo with `pm2-startup uninstall`.

---

## Daily controls

```powershell
pm2 list                 # status
pm2 logs tradebot-bot     # engine output
pm2 restart all           # after editing config.yaml or code
pm2 stop all              # pause
pm2 delete all            # remove from pm2
```

## Layout

```
tradebot\
  config.yaml            <- your settings (instruments, strategy params, risk, alerts)
  .env                   <- your secrets (never share)
  bot\                   <- Python: engine, strategies, scanner, backtester
  dashboard\             <- Node web UI
  data\                  <- generated CSVs, SQLite db, logs (safe to delete)
  assets\kaching.wav     <- alert sound
  INSTALL.md  TUNING.md   <- this file, and the tuning guide
```

Next: read **TUNING.md** for how to adjust and test the analysis.
