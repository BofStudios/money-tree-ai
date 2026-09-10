"""The contract every research data provider must satisfy.

Nothing above this layer knows the word "yfinance". Swapping in a paid feed
later means writing one new class here, not touching the dashboard or the AI.

Every method returns None (or an empty list) rather than raising when a
provider simply does not carry that data. "We don't have it" is a normal,
expected answer and must travel all the way to the screen intact.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.research.models import (
    Analysts,
    CompanyProfile,
    Dividend,
    Earnings,
    Ownership,
    PriceSnapshot,
    Quality,
    Statements,
    Valuation,
)


class ResearchProvider(ABC):
    """Company-level data: who they are, what they earn, what they are worth."""

    name: str = "base"

    @abstractmethod
    def profile(self, symbol: str) -> CompanyProfile | None:
        """Business description, sector, listing details."""

    @abstractmethod
    def price(self, symbol: str) -> PriceSnapshot | None:
        """Last price and the ranges that put it in context."""

    @abstractmethod
    def valuation(self, symbol: str) -> Valuation | None:
        """What the market is charging for the earnings."""

    @abstractmethod
    def quality(self, symbol: str) -> Quality | None:
        """Margins, growth, returns and balance-sheet strength."""

    def statements(self, symbol: str) -> Statements | None:
        """Income, balance sheet and cash flow over several periods."""
        return None

    def earnings(self, symbol: str) -> Earnings | None:
        """Reporting dates and how results landed against estimates."""
        return None

    def analysts(self, symbol: str) -> Analysts | None:
        """Published targets and the spread of opinion behind them."""
        return None

    def ownership(self, symbol: str) -> Ownership | None:
        """Who holds the shares, and what insiders have been doing."""
        return None

    def dividend(self, symbol: str) -> Dividend | None:
        """Distribution history and whether earnings comfortably cover it."""
        return None

    def search(self, query: str, limit: int = 8) -> list[dict]:
        """Ticker lookup. Empty list when the provider offers no search."""
        return []
