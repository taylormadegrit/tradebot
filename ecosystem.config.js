// pm2 supervises the processes. Run: pm2 start ecosystem.config.js
const path = require("path");
const fs = require("fs");

// Prefer the offline bundle's Python, then a dev virtualenv, then system python.
const pyCandidates = [
  path.join(__dirname, "runtime", "python", "python.exe"), // offline bundle
  path.join(__dirname, ".venv", "Scripts", "python.exe"),  // dev (Windows)
  path.join(__dirname, ".venv", "bin", "python"),          // dev (Unix)
];
const venvPython = pyCandidates.find((p) => fs.existsSync(p)) || "python";

module.exports = {
  apps: [
    {
      name: "tradebot-bot",
      script: "run_bot.py",
      interpreter: venvPython,
      cwd: __dirname,
      autorestart: true,
      max_restarts: 20,
      restart_delay: 3000,
      out_file: path.join(__dirname, "data", "bot.out.log"),
      error_file: path.join(__dirname, "data", "bot.err.log"),
    },
    {
      name: "tradebot-dashboard",
      script: "dashboard/server.js",
      cwd: __dirname,
      autorestart: true,
      restart_delay: 2000,
      env: { PORT: "4000", BOT_URL: "http://127.0.0.1:8787" },
      out_file: path.join(__dirname, "data", "dash.out.log"),
      error_file: path.join(__dirname, "data", "dash.err.log"),
    },
    {
      name: "tradebot-datafeed",
      script: "run_datafeed.py",
      interpreter: venvPython,
      cwd: __dirname,
      autorestart: true,
      max_restarts: 20,
      restart_delay: 5000,
      out_file: path.join(__dirname, "data", "feed.out.log"),
      error_file: path.join(__dirname, "data", "feed.err.log"),
    },
  ],
};
