"""Pre-trade risk gate. Nothing reaches the broker without passing every check here."""
import datetime as dt
from pathlib import Path


class RiskManager:
    def __init__(self, cfg: dict, root: Path):
        r = cfg["risk"]
        self.risk_pct = float(r["risk_per_trade_pct"])
        self.max_lots = float(r["max_position_lots"])
        self.max_open = int(r["max_open_positions"])
        self.daily_loss_pct = float(r["daily_loss_halt_pct"])
        self.root = root
        self._day: dt.date | None = None
        self._day_start_equity: float | None = None
        self.halted_reason: str | None = None

    # --- kill switch -------------------------------------------------------
    def halt_file(self) -> bool:
        return (self.root / "HALT").exists()

    # --- daily loss ------------------------------------------------------
    def new_day_rollover(self, equity: float) -> None:
        today = dt.date.today()
        if self._day != today:
            self._day = today
            self._day_start_equity = equity
            self.halted_reason = None

    def check_daily_loss(self, equity: float) -> bool:
        if not self._day_start_equity:
            return True
        change = (equity - self._day_start_equity) / self._day_start_equity * 100
        if change <= -self.daily_loss_pct:
            self.halted_reason = f"daily loss {change:.2f}% <= -{self.daily_loss_pct}%"
            return False
        return True

    # --- sizing --------------------------------------------------------
    def size_lots(self, equity: float, entry: float, sl_price: float, pip_value_per_lot: float, pip: float) -> float:
        risk_cash = equity * self.risk_pct / 100
        stop_pips = abs(entry - sl_price) / pip
        if stop_pips <= 0 or pip_value_per_lot <= 0:
            return 0.0
        lots = risk_cash / (stop_pips * pip_value_per_lot)
        return round(min(lots, self.max_lots), 2)

    # --- gate --------------------------------------------------------
    def gate(self, *, equity: float, open_count: int) -> tuple[bool, str]:
        if self.halt_file():
            return False, "HALT file present"
        if self.halted_reason:
            return False, self.halted_reason
        if not self.check_daily_loss(equity):
            return False, self.halted_reason or "daily loss halt"
        if open_count >= self.max_open:
            return False, f"max_open_positions ({self.max_open}) reached"
        return True, "ok"
