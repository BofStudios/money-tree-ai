"""Which stocks the bot watches, by the market the owner picked.

The same three lists as the phone app. European companies are traded through
their US listings (ASML, SAP, Novo Nordisk ...), because Alpaca only trades US
exchanges; VGK is a fund that holds the European market as a whole.
"""
from __future__ import annotations

MARKETS: dict[str, list[str]] = {
    "us": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "SPY"],
    "europe": ["ASML", "SAP", "NVO", "AZN", "SHEL", "TTE", "UL", "VGK"],
    "both": ["AAPL", "MSFT", "NVDA", "AMZN", "ASML", "SAP", "NVO", "SPY"],
}


def watchlist_for(market: str | None) -> list[str] | None:
    """The market's list, or None when nothing was chosen (keep the config's)."""
    symbols = MARKETS.get(market or "")
    return list(symbols) if symbols else None
