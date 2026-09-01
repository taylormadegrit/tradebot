# Deploying the playground to Streamlit Community Cloud

The Streamlit app (`streamlit_app.py`) is the **backtest & analysis playground** —
it reuses the bot's modules for on-demand analysis. It does **not** run the live
trading engine, the OANDA feed, or the Discord bot (Streamlit Cloud has no
always-on process and wipes its filesystem on restart). Those stay on your own
machine / a VPS — see `requirements-engine.txt` and `ecosystem.config.js`.

## What ships to the repo

Tracked: `bot/`, `streamlit_app.py`, `sample_data/`, `config.yaml`,
`requirements.txt`, `.streamlit/config.toml`, `.python-version`, docs.

Ignored (see `.gitignore`): `.env`, `.streamlit/secrets.toml`, `data/`, `*.db`,
`*.log`, `bundle/`, `dist/`, `dashboard/node_modules/`, `.venv/`.

**Nothing secret is committed.** Broker/Discord tokens live only in `.env`
(gitignored) and are not needed by the playground.

## Steps

1. **Create a GitHub repo** and push:
   ```bash
   cd D:\tradebot
   git init
   git add .
   git commit -m "tradebot playground"
   git branch -M main
   git remote add origin https://github.com/<you>/<repo>.git
   git push -u origin main
   ```
   (or `gh repo create <repo> --public --source=. --push`)

2. **Verify no secrets slipped in:**
   ```bash
   git ls-files | grep -Ei "\.env$|secrets\.toml$|token" || echo "clean"
   ```
   Should print `clean`.

3. **Deploy:** go to <https://share.streamlit.io> → *New app* → pick the repo,
   branch `main`, main file **`streamlit_app.py`** → *Deploy*.

4. **(Optional) Secrets:** in the app's *Settings → Secrets*, paste any of the
   keys from `.streamlit/secrets.toml.example`. All optional — without them the
   app uses the bundled sample data and a rule-based news read.

## Local run

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Updating

`git push` to `main` — Streamlit Cloud redeploys automatically.
