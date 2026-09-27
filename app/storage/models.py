from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TradeRow(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    broker: Mapped[str] = mapped_column(String(24))
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    exit_price: Mapped[float] = mapped_column(Float)
    pnl: Mapped[float] = mapped_column(Float)
    pnl_pct: Mapped[float] = mapped_column(Float)
    entry_reason: Mapped[str] = mapped_column(String(200), default="")
    exit_reason: Mapped[str] = mapped_column(String(200), default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class OpenPositionRow(Base):
    """The engine's authoritative view of what is open, so a restart can resume."""

    __tablename__ = "open_positions"
    # Practice and real money can hold the same stock at the same time.
    __table_args__ = (UniqueConstraint("mode", "symbol", name="uq_open_positions_mode_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    symbol: Mapped[str] = mapped_column(String(24))
    side: Mapped[str] = mapped_column(String(8))
    qty: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_reason: Mapped[str] = mapped_column(String(200), default="")
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EquityRow(Base):
    __tablename__ = "equity_curve"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    equity: Mapped[float] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ChallengeRow(Base):
    """A run: take this much, try to reach that much."""

    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    stake: Mapped[float] = mapped_column(Float)
    target: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(12), index=True)  # active|won|lost|stopped
    realised_pnl: Mapped[float] = mapped_column(Float, default=0.0)
    peak_value: Mapped[float] = mapped_column(Float, default=0.0)
    trades: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CatalystRow(Base):
    """An upcoming event expected to move a stock — a game launch, a film, a ruling."""

    __tablename__ = "catalysts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(160))
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    date_confidence: Mapped[str] = mapped_column(String(12), default="estimated")
    thesis: Mapped[str] = mapped_column(String(600), default="")
    conviction: Mapped[str] = mapped_column(String(8), default="medium")
    # watching -> armed (inside the entry window) -> holding -> closed | dropped
    status: Mapped[str] = mapped_column(String(12), default="watching", index=True)
    entry_days_before: Mapped[int] = mapped_column(Integer, default=45)
    exit_rule: Mapped[str] = mapped_column(String(8), default="before")
    notes: Mapped[str] = mapped_column(String(600), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CandleRow(Base):
    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    broker: Mapped[str] = mapped_column(String(24))
    symbol: Mapped[str] = mapped_column(String(24))
    timeframe: Mapped[str] = mapped_column(String(8))
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)

    __table_args__ = (
        Index("ix_candle_unique", "broker", "symbol", "timeframe", "open_time", unique=True),
    )
