from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.common.models import ClosedTrade, Position, Side
from app.storage.models import CandleRow, EquityRow, OpenPositionRow, TradeRow

# SQLite caps bound variables per statement; 9 columns x 500 rows stays well under it.
_INSERT_CHUNK = 500


class Repository:
    """All database access. SQLite has one writer, so writes take a lock."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._write_lock = threading.Lock()

    def save_closed_trade(
        self, trade: ClosedTrade, mode: str, broker: str, entry_reason: str = ""
    ) -> None:
        row = TradeRow(
            mode=mode,
            broker=broker,
            symbol=trade.symbol,
            side=trade.side.value,
            qty=trade.qty,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            pnl=trade.pnl,
            pnl_pct=trade.pnl_pct,
            entry_reason=entry_reason,
            exit_reason=trade.exit_reason,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
        )
        with self._write_lock, self._session_factory() as session:
            session.add(row)
            session.commit()

    def recent_trades(self, mode: str, limit: int = 50) -> list[dict]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(TradeRow)
                .where(TradeRow.mode == mode)
                .order_by(TradeRow.closed_at.desc())
                .limit(limit)
            ).all()
        return [
            {
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "entry_price": r.entry_price,
                "exit_price": r.exit_price,
                "pnl": round(r.pnl, 2),
                "pnl_pct": round(r.pnl_pct, 2),
                "exit_reason": r.exit_reason,
                "opened_at": r.opened_at.isoformat(),
                "closed_at": r.closed_at.isoformat(),
            }
            for r in rows
        ]

    def trade_stats(self, mode: str) -> dict:
        with self._session_factory() as session:
            rows = session.scalars(select(TradeRow).where(TradeRow.mode == mode)).all()
        if not rows:
            return {
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "total_pnl": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "best_trade": 0.0,
                "worst_trade": 0.0,
            }
        wins = [r.pnl for r in rows if r.pnl > 0]
        losses = [r.pnl for r in rows if r.pnl <= 0]
        gross_loss = abs(sum(losses))
        return {
            "total_trades": len(rows),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(rows) * 100, 1),
            "total_pnl": round(sum(r.pnl for r in rows), 2),
            "avg_win": round(sum(wins) / len(wins), 2) if wins else 0.0,
            "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0.0,
            "profit_factor": round(sum(wins) / gross_loss, 2) if gross_loss else 0.0,
            "best_trade": round(max(r.pnl for r in rows), 2),
            "worst_trade": round(min(r.pnl for r in rows), 2),
        }

    def save_open_position(self, position: Position, mode: str, entry_reason: str = "") -> None:
        with self._write_lock, self._session_factory() as session:
            session.execute(delete(OpenPositionRow).where(OpenPositionRow.symbol == position.symbol))
            session.add(
                OpenPositionRow(
                    mode=mode,
                    symbol=position.symbol,
                    side=position.side.value,
                    qty=position.qty,
                    entry_price=position.entry_price,
                    stop_loss=position.stop_loss,
                    take_profit=position.take_profit,
                    entry_reason=entry_reason,
                    opened_at=position.opened_at,
                )
            )
            session.commit()

    def clear_open_position(self, symbol: str) -> None:
        with self._write_lock, self._session_factory() as session:
            session.execute(delete(OpenPositionRow).where(OpenPositionRow.symbol == symbol))
            session.commit()

    def load_open_position(self, symbol: str, mode: str) -> tuple[Position | None, str]:
        with self._session_factory() as session:
            row = session.scalar(
                select(OpenPositionRow).where(
                    OpenPositionRow.symbol == symbol, OpenPositionRow.mode == mode
                )
            )
        if row is None:
            return None, ""
        return (
            Position(
                symbol=row.symbol,
                side=Side(row.side),
                qty=row.qty,
                entry_price=row.entry_price,
                opened_at=row.opened_at,
                stop_loss=row.stop_loss,
                take_profit=row.take_profit,
            ),
            row.entry_reason,
        )

    def record_equity(self, equity: float, mode: str) -> None:
        with self._write_lock, self._session_factory() as session:
            session.add(
                EquityRow(mode=mode, equity=equity, recorded_at=datetime.now(timezone.utc))
            )
            session.commit()

    def equity_curve(self, mode: str, days: int = 30) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with self._session_factory() as session:
            rows = session.scalars(
                select(EquityRow)
                .where(EquityRow.mode == mode, EquityRow.recorded_at >= cutoff)
                .order_by(EquityRow.recorded_at)
            ).all()
        # Charts need strictly increasing, unique timestamps. Two snapshots can land
        # in the same second (a double-tapped "Scan now"), so keep the last of each.
        by_second: dict[int, float] = {}
        for row in rows:
            by_second[int(row.recorded_at.timestamp())] = round(row.equity, 2)
        return [{"time": t, "value": v} for t, v in sorted(by_second.items())]

    def save_candles(
        self, frame: pd.DataFrame, broker: str, symbol: str, timeframe: str
    ) -> int:
        rows = [
            {
                "broker": broker,
                "symbol": symbol,
                "timeframe": timeframe,
                "open_time": ts.to_pydatetime(),
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume),
            }
            for ts, r in frame.iterrows()
        ]
        if not rows:
            return 0
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert

        with self._write_lock, self._session_factory() as session:
            for start in range(0, len(rows), _INSERT_CHUNK):
                session.execute(
                    sqlite_insert(CandleRow)
                    .values(rows[start : start + _INSERT_CHUNK])
                    .on_conflict_do_nothing(
                        index_elements=["broker", "symbol", "timeframe", "open_time"]
                    )
                )
            session.commit()
        return len(rows)

    def load_candles(self, broker: str, symbol: str, timeframe: str) -> pd.DataFrame:
        with self._session_factory() as session:
            rows = session.scalars(
                select(CandleRow)
                .where(
                    CandleRow.broker == broker,
                    CandleRow.symbol == symbol,
                    CandleRow.timeframe == timeframe,
                )
                .order_by(CandleRow.open_time)
            ).all()
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = pd.DataFrame(
            [
                {
                    "timestamp": r.open_time,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume,
                }
                for r in rows
            ]
        )
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        return frame.set_index("timestamp")
