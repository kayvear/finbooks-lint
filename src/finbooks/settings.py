from datetime import date
from pathlib import Path
from typing import Final

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="FINBOOKS_", extra="ignore")

    project_root: Path = Path(__file__).parent.parent.parent
    data_dir: Path = Path(__file__).parent.parent.parent / "data"

    num_customers: int = 10
    statement_start: date = date(2024, 10, 1)
    statement_end: date = date(2024, 12, 31)
    random_seed: int = 42

    # Phase 3 — agent models
    orchestrator_model: str = "claude-opus-4-6"
    specialist_model: str = "claude-sonnet-4-6"


settings = Settings()

# ── Asset universe ────────────────────────────────────────────────────────────

EQUITY_TICKERS: Final[list[str]] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "V",
    "UNH",  "XOM",  "JNJ",   "PG",   "MA",   "HD",   "ABBV", "PFE",
    "MRK",  "BAC",  "WMT",   "KO",   "DIS",  "NFLX", "ADBE", "CRM",
    "PYPL",
]

ETF_TICKERS: Final[list[str]] = [
    "SPY", "QQQ", "IWM", "VTI", "GLD",
]

ALL_EQUITY_TICKERS: Final[list[str]] = EQUITY_TICKERS + ETF_TICKERS

# Approximate seed prices for GBM simulation (USD)
SEED_PRICES: Final[dict[str, float]] = {
    "AAPL": 225.0, "MSFT": 425.0, "GOOGL": 165.0, "AMZN": 195.0, "NVDA": 120.0,
    "META": 560.0, "TSLA": 250.0, "V": 275.0,    "UNH": 580.0,  "XOM":  115.0,
    "JNJ":  155.0, "PG":   170.0, "MA":   490.0,  "HD":   380.0, "ABBV": 195.0,
    "PFE":   28.0, "MRK":  105.0, "BAC":   42.0,  "WMT":   85.0, "KO":    63.0,
    "DIS":   95.0, "NFLX": 760.0, "ADBE": 480.0,  "CRM":  310.0, "PYPL":  85.0,
    "SPY":  575.0, "QQQ":  490.0, "IWM":  220.0,  "VTI":  270.0, "GLD":  245.0,
}

# Annual volatility (sigma) per ticker for GBM
VOLATILITY: Final[dict[str, float]] = {
    "AAPL": 0.28, "MSFT": 0.26, "GOOGL": 0.30, "AMZN": 0.32, "NVDA": 0.55,
    "META": 0.38, "TSLA": 0.65, "V":     0.20, "UNH":  0.22, "XOM":  0.25,
    "JNJ":  0.18, "PG":   0.16, "MA":    0.22, "HD":   0.24, "ABBV": 0.28,
    "PFE":  0.22, "MRK":  0.20, "BAC":   0.32, "WMT":  0.18, "KO":   0.15,
    "DIS":  0.30, "NFLX": 0.42, "ADBE":  0.35, "CRM":  0.38, "PYPL": 0.48,
    "SPY":  0.18, "QQQ":  0.22, "IWM":   0.25, "VTI":  0.18, "GLD":  0.15,
}

# Annual dividend yield (0 = no dividend)
DIVIDEND_YIELD: Final[dict[str, float]] = {
    "AAPL": 0.005, "MSFT": 0.007, "V": 0.008, "UNH": 0.014, "XOM": 0.033,
    "JNJ":  0.030, "PG":   0.025, "MA": 0.006, "HD":  0.022, "ABBV": 0.038,
    "PFE":  0.058, "MRK":  0.026, "BAC": 0.026, "WMT": 0.012, "KO": 0.030,
    "SPY":  0.013, "QQQ":  0.006, "VTI": 0.014,
}

# CD product rates by term
CD_RATES: Final[dict[int, float]] = {
    3:  0.045,  # 3-month
    6:  0.048,  # 6-month
    12: 0.051,  # 12-month
    18: 0.050,  # 18-month
}
