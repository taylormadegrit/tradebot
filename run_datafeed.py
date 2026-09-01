"""Entry point pm2 runs for the OANDA data refresh loop."""
from bot.refresh_data import loop

if __name__ == "__main__":
    loop()
