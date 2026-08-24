from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from app.common.models import Action, Balance, ClosedTrade, Position, Side
from app.config import ProtectionsConfig, RiskConfig
from app.risk.protections import Protections
from app.risk.risk_manager import RiskManager
from app.strategy.indicators import atr
from app.strategy.base import Strategy

FEE_PCT = 0.1


class _SimulatedClock:
    """Lets the risk manager's daily counters roll with bar time, not wall time."""

    def __init__(self, start: pd.Timestamp) -> None:
        self.now = start

    def today(self) -> date:
        return self.now.date()


@dataclass
class BacktestResult:
    starting_equity: float
    ending_equity: float
    trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[tuple[pd.Timestamp, float]] = field(default_factory=list)

    @property
    def total_return_pct(self) -> float:
        if not self.starting_equity:
            return 0.0
        return (self.ending_equity / self.starting_equity - 1) * 100

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        return len([t for t in self.trades if t.pnl > 0]) / len(self.trades) * 100

    @property
    def max_drawdown_pct(self) -> float:
        if not self.equity_curve:
            return 0.0
        peak = self.equity_curve[0][1]
        worst = 0.0
        for _, equity in self.equity_curve:
            peak = max(peak, equity)
            if peak:
                worst = min(worst, (equity - peak) / peak * 100)
        return abs(worst)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t.pnl for t in self.trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trades if t.pnl <= 0))
        return gross_profit / gross_loss if gross_loss else 0.0

    def summary(self) -> str:
        return "\n".join(
            [
                f"  Trades           : {len(self.trades)}",
                f"  Win rate         : {self.win_rate:.1f}%",
                f"  Starting equity  : {self.starting_equity:,.2f}",
                f"  Ending equity    : {self.ending_equity:,.2f}",
                f"  Total return     : {self.total_return_pct:+.2f}%",
                f"  Max drawdown     : {self.max_drawdown_pct:.2f}%",
                f"  Profit factor    : {self.profit_factor:.2f}",
            ]
        )


def run_backtest(
    candles: pd.DataFrame,
    strategy: Strategy,
    risk_config: RiskConfig,
    starting_equity: float | None = None,
    protections_config: ProtectionsConfig | None = None,
) -> BacktestResult:
    """Replay candles through strategy + risk rules. Never touches a broker.

    Stops and targets are checked against each bar's high/low before the
    strategy runs, so an intrabar stop-out is not missed.
    """
    equity = starting_equity or risk_config.starting_paper_balance
    clock = _SimulatedClock(candles.index[0])
    risk = RiskManager(risk_config, mode="paper", clock=clock.today)
    # Off by default so existing tests keep measuring the strategy alone.
    protections = Protections(
        protections_config or ProtectionsConfig(enabled=False)
    )
    result = BacktestResult(starting_equity=equity, ending_equity=equity)

    # Computed once for the whole series — recomputing it per bar turns the
    # backtest quadratic and it does not change with the window anyway.
    atr_series = atr(candles, risk_config.atr_period) if risk_config.stop_mode == "atr" else None

    cash = equity
    position: Position | None = None

    for i in range(strategy.warmup_bars, len(candles)):
        window = candles.iloc[: i + 1]
        bar = window.iloc[-1]
        timestamp = window.index[-1]
        clock.now = timestamp

        if position is not None:
            position.current_price = float(bar["close"])
            exit_price = None
            exit_reason = ""
            # Check the stop against the bar's low before trailing it up, so a bar
            # that dipped and then rallied still counts as a stop-out.
            if position.stop_loss and float(bar["low"]) <= position.stop_loss:
                exit_price, exit_reason = position.stop_loss, "stop-loss"
            elif position.take_profit and float(bar["high"]) >= position.take_profit:
                exit_price, exit_reason = position.take_profit, "take-profit"
            else:
                risk.update_trailing_stop(position, float(bar["high"]))

            if exit_price is not None:
                cash, trade = _close(position, exit_price, timestamp, cash, exit_reason)
                result.trades.append(trade)
                risk.record_closed_trade(trade, cash)
                protections.record_trade(trade, cash, now=timestamp.to_pydatetime())
                position = None

        signal = strategy.on_bar(window, position)
        price = float(bar["close"])
        balance = Balance(total=cash + (position.market_value if position else 0.0), available=cash)

        if position is None and protections.blocked("BACKTEST", now=timestamp.to_pydatetime()):
            result.equity_curve.append((timestamp, cash))
            continue

        bar_atr = atr_series.iloc[i] if atr_series is not None else None
        order, _ = risk.validate(
            signal, balance, position, price, symbol="BACKTEST",
            atr=None if bar_atr is None or pd.isna(bar_atr) else float(bar_atr),
        )

        if order is not None:
            if signal.action is Action.CLOSE and position is not None:
                cash, trade = _close(position, price, timestamp, cash, signal.reason)
                result.trades.append(trade)
                risk.record_closed_trade(trade, cash)
                position = None
            elif signal.action is Action.BUY:
                cost = price * order.qty
                fee = cost * FEE_PCT / 100.0
                if cost + fee <= cash:
                    cash -= cost + fee
                    position = Position(
                        symbol="BACKTEST",
                        side=Side.BUY,
                        qty=order.qty,
                        entry_price=price,
                        opened_at=timestamp.to_pydatetime(),
                        stop_loss=order.stop_loss,
                        take_profit=order.take_profit,
                        current_price=price,
                    )

        equity = cash + (position.qty * price if position else 0.0)
        result.equity_curve.append((timestamp, equity))

    if position is not None:
        final_price = float(candles.iloc[-1]["close"])
        cash, trade = _close(
            position, final_price, candles.index[-1], cash, "end of backtest"
        )
        result.trades.append(trade)
        equity = cash

    result.ending_equity = equity
    return result


def _close(
    position: Position,
    exit_price: float,
    timestamp: pd.Timestamp,
    cash: float,
    reason: str,
) -> tuple[float, ClosedTrade]:
    gross = exit_price * position.qty
    fee = gross * FEE_PCT / 100.0
    entry_fee = position.entry_price * position.qty * FEE_PCT / 100.0
    pnl = (exit_price - position.entry_price) * position.qty - fee - entry_fee
    return cash + gross - fee, ClosedTrade(
        symbol=position.symbol,
        side=position.side,
        qty=position.qty,
        entry_price=position.entry_price,
        exit_price=exit_price,
        opened_at=position.opened_at,
        closed_at=timestamp.to_pydatetime(),
        pnl=pnl,
        exit_reason=reason,
    )
