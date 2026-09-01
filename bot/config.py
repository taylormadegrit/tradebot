import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    cfg["_root"] = ROOT

    b = cfg.setdefault("broker", {})
    b["username"] = os.getenv("TL_USERNAME", "")
    b["password"] = os.getenv("TL_PASSWORD", "")
    b["server"] = os.getenv("TL_SERVER", b.get("server", "") or "")
    b["environment"] = os.getenv("TL_ENVIRONMENT", b.get("environment", "https://demo.tradelocker.com"))

    if cfg.get("mode") == "live" and not (ROOT / "I_UNDERSTAND_LIVE_RISK").exists():
        raise RuntimeError(
            "mode=live requires a file named 'I_UNDERSTAND_LIVE_RISK' in the project root. "
            "Create it deliberately when you accept the risk."
        )
    return cfg
