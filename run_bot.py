"""Entry point pm2 runs. Starts the FastAPI app that hosts the engine loop."""
import uvicorn

from bot.config import load_config

if __name__ == "__main__":
    cfg = load_config()
    uvicorn.run(
        "bot.main:app",
        host=cfg["api"]["host"],
        port=int(cfg["api"]["port"]),
        reload=False,
        log_level="info",
    )
