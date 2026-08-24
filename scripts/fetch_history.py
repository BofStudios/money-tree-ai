"""Cache historical US stock candles for backtesting.

    python scripts/fetch_history.py --symbol AAPL --timeframe 1h
    python scripts/fetch_history.py --watchlist --timeframe 15m
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import load_settings
from app.data.yahoo import YahooData
from app.storage.db import create_session_factory
from app.storage.repository import Repository


def main() -> None:
    parser = argparse.ArgumentParser(description="Cache US stock candles for backtesting")
    parser.add_argument("--symbol", default=None, help="single ticker, e.g. AAPL")
    parser.add_argument("--watchlist", action="store_true", help="fetch the whole watchlist")
    parser.add_argument("--timeframe", default=None)
    args = parser.parse_args()

    settings = load_settings()
    timeframe = args.timeframe or settings.app.timeframe

    if args.watchlist:
        symbols = list(settings.app.watchlist)
    elif args.symbol:
        symbols = [args.symbol.upper()]
    else:
        symbols = [settings.app.watchlist[0]]

    print(f"Fetching {', '.join(symbols)} at {timeframe} from Yahoo...")
    data = YahooData()
    frames = data.get_many_ohlcv(symbols, timeframe, limit=100_000)
    if not frames:
        print("Nothing returned. Check the tickers and the timeframe.")
        return

    repo = Repository(create_session_factory(settings.db_path))
    for symbol, frame in sorted(frames.items()):
        saved = repo.save_candles(frame, broker="yahoo", symbol=symbol, timeframe=timeframe)
        print(f"  {symbol:6s} {saved:6d} candles  {frame.index[0]} -> {frame.index[-1]}")

    missing = sorted(set(symbols) - set(frames))
    if missing:
        print(f"\nNo data for: {', '.join(missing)}")
    print(f"\nDatabase: {settings.db_path}")


if __name__ == "__main__":
    main()
