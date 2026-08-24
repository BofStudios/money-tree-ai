"""Replay cached candles through the strategy and risk rules.

    python scripts/run_backtest.py --symbol AAPL
    python scripts/run_backtest.py --watchlist --timeframe 1h
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings
from app.engine.backtester import run_backtest
from app.storage.db import create_session_factory
from app.storage.repository import Repository
from app.strategy.ema_rsi import EmaRsiStrategy


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest the strategy on cached candles")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--watchlist", action="store_true")
    parser.add_argument("--timeframe", default=None)
    parser.add_argument("--fast", type=int, default=None)
    parser.add_argument("--slow", type=int, default=None)
    args = parser.parse_args()

    settings = load_settings()
    timeframe = args.timeframe or settings.app.timeframe
    strategy_config = settings.app.strategy

    if args.watchlist:
        symbols = list(settings.app.watchlist)
    elif args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = [settings.app.watchlist[0]]

    repo = Repository(create_session_factory(settings.db_path))

    print(f"\n  Strategy   : EMA {args.fast or strategy_config.fast_ema}/"
          f"{args.slow or strategy_config.slow_ema}, RSI {strategy_config.rsi_period}")
    print(f"  Risk       : {settings.app.risk.max_position_pct}% size, "
          f"-{settings.app.risk.stop_loss_pct}% stop, +{settings.app.risk.take_profit_pct}% target")
    print(f"  Timeframe  : {timeframe}\n")

    header = f"  {'SYMBOL':<8}{'BARS':>7}{'TRADES':>8}{'WIN%':>8}{'RETURN':>10}{'MAXDD':>9}{'PF':>7}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    total_return = 0.0
    tested = 0

    for symbol in symbols:
        candles = repo.load_candles("yahoo", symbol, timeframe)
        if candles.empty:
            print(f"  {symbol:<8}{'no cached data — run fetch_history.py':>40}")
            continue

        strategy = EmaRsiStrategy(
            fast_ema=args.fast or strategy_config.fast_ema,
            slow_ema=args.slow or strategy_config.slow_ema,
            rsi_period=strategy_config.rsi_period,
            rsi_overbought=strategy_config.rsi_overbought,
            rsi_oversold=strategy_config.rsi_oversold,
        )
        result = run_backtest(candles, strategy, settings.app.risk)
        total_return += result.total_return_pct
        tested += 1

        print(
            f"  {symbol:<8}{len(candles):>7}{len(result.trades):>8}"
            f"{result.win_rate:>7.1f}%{result.total_return_pct:>9.2f}%"
            f"{result.max_drawdown_pct:>8.2f}%{result.profit_factor:>7.2f}"
        )

    if tested > 1:
        print("  " + "-" * (len(header) - 2))
        print(f"  {'AVERAGE':<8}{'':>7}{'':>8}{'':>8}{total_return / tested:>9.2f}%")
    print()


if __name__ == "__main__":
    main()
