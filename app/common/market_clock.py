from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd
import pandas_market_calendars as mcal

log = logging.getLogger(__name__)

NY = "America/New_York"
ISTANBUL = "Europe/Istanbul"


@dataclass
class MarketState:
    is_open: bool
    session: str  # "open" | "pre" | "after" | "closed"
    next_open: datetime | None
    next_close: datetime | None
    now_ny: datetime

    @property
    def seconds_until_open(self) -> float | None:
        if self.next_open is None:
            return None
        return max((self.next_open - datetime.now(timezone.utc)).total_seconds(), 0.0)

    @property
    def seconds_until_close(self) -> float | None:
        if self.next_close is None:
            return None
        return max((self.next_close - datetime.now(timezone.utc)).total_seconds(), 0.0)

    def to_dict(self) -> dict:
        return {
            "is_open": self.is_open,
            "session": self.session,
            "next_open": self.next_open.isoformat() if self.next_open else None,
            "next_close": self.next_close.isoformat() if self.next_close else None,
            "seconds_until_open": self.seconds_until_open,
            "seconds_until_close": self.seconds_until_close,
            "now_ny": self.now_ny.isoformat(),
            "countdown": self.countdown_text(),
        }

    def countdown_text(self) -> str:
        if self.is_open:
            remaining = self.seconds_until_close
            return f"closes in {_humanise(remaining)}" if remaining else "open"
        remaining = self.seconds_until_open
        return f"opens in {_humanise(remaining)}" if remaining else "closed"


class MarketClock:
    """Knows when the US stock market is actually open, holidays included."""

    def __init__(self, calendar_name: str = "NYSE") -> None:
        self._calendar = mcal.get_calendar(calendar_name)
        self._schedule: pd.DataFrame | None = None
        self._schedule_built_on: datetime | None = None

    def state(self) -> MarketState:
        now = datetime.now(timezone.utc)
        schedule = self._ensure_schedule(now)
        now_ny = now.astimezone(pd.Timestamp(now).tz_convert(NY).tzinfo)

        if schedule.empty:
            return MarketState(False, "closed", None, None, now_ny)

        opens = schedule["market_open"]
        closes = schedule["market_close"]

        current = schedule[(opens <= now) & (now < closes)]
        if not current.empty:
            return MarketState(
                is_open=True,
                session="open",
                next_open=None,
                next_close=current["market_close"].iloc[0].to_pydatetime(),
                now_ny=now_ny,
            )

        upcoming = schedule[opens > now]
        next_open = upcoming["market_open"].iloc[0].to_pydatetime() if not upcoming.empty else None
        next_close = upcoming["market_close"].iloc[0].to_pydatetime() if not upcoming.empty else None

        session = "closed"
        if next_open is not None:
            until = (next_open - now).total_seconds()
            if 0 < until <= 5.5 * 3600:
                session = "pre"
        return MarketState(False, session, next_open, next_close, now_ny)

    def _ensure_schedule(self, now: datetime) -> pd.DataFrame:
        stale = (
            self._schedule is None
            or self._schedule_built_on is None
            or (now - self._schedule_built_on) > timedelta(days=1)
        )
        if stale:
            start = (now - timedelta(days=2)).date()
            end = (now + timedelta(days=14)).date()
            self._schedule = self._calendar.schedule(start_date=start, end_date=end)
            self._schedule_built_on = now
        return self._schedule


def _humanise(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    total = int(seconds)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def istanbul_time(moment: datetime) -> datetime:
    """Turkish local time, for messages read on a phone in Istanbul."""
    return moment.astimezone(pd.Timestamp(moment).tz_convert(ISTANBUL).tzinfo)
