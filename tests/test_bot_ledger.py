"""Money Bot 12.0: one ledger for the console and Telegram's end of the day."""
from __future__ import annotations

from datetime import datetime

from app.bot.ledger import NY, ledger, to_ms
from app.notify import formatting as fmt

NOW = datetime(2026, 11, 17, 16, 30, tzinfo=NY)


class Repo:
    def __init__(self, trades, curve=()):
        self.trades, self.curve = trades, list(curve)

    def recent_trades(self, mode, limit=50):
        return self.trades[:limit]

    def equity_curve(self, mode, days=30):
        return self.curve


def trade(sym, pnl, opened, closed, reason="Scalp: take profit"):
    return {"symbol": sym, "side": "long", "qty": 3.0, "entry_price": 10.0, "exit_price": 10.5, "pnl": pnl,
            "pnl_pct": pnl / 30 * 100, "exit_reason": reason, "opened_at": opened, "closed_at": closed}


def test_the_ledger_reads_qty_and_times_and_keeps_to_the_range():
    today = "2026-11-17T15:00:00+00:00"                      # 10:00 New York
    repo = Repo([trade("AAPL", 1.5, "2026-11-17T14:48:00", today),          # naive time = UTC
                 trade("MSFT", -0.5, "2026-11-17T15:10:00+00:00", "2026-11-17T15:40:00+00:00", "Stop loss"),
                 trade("NVDA", 2.0, "2026-11-10T15:00:00+00:00", "2026-11-10T16:00:00+00:00")],
                curve=[{"time": to_ms(today) // 1000, "value": 1001.0}, {"time": 0, "value": 999.0}])
    book = ledger(repo, "paper", "today", now=NOW)
    a, m = book["fills"]
    assert a["qty"] == 3.0 and a["minutes"] == 12 and a["book"] == "ultra" and m["book"] is None
    assert book["sum"] == {"count": 2, "wins": 1, "pnl": 1.0, "fees": 0.0, "best": 1.5, "worst": -0.5,
                           "profit_factor": 3.0, "avg_minutes": 21}
    assert book["curve"] == [[to_ms(today), 1001.0]]
    assert ledger(repo, "paper", "all", now=NOW)["sum"]["count"] == 3
    assert ledger(repo, "paper", "all", now=NOW)["curve"] == []


def test_the_day_end_message_shows_the_ledgers_numbers():
    repo = Repo([trade("AAPL", 1.5, None, "2026-11-17T15:00:00+00:00")])
    book = ledger(repo, "paper", "today", now=NOW)
    text = fmt.day_end_message(book, {"blocked": [{"label": "Trend", "n": 4}]},
                               {"state": "lost", "per_trade_pct": -0.0121})
    assert text.startswith("*Money Bot — today*") and "Trades: 1 (1 won)" in text
    assert "Trend (4×)" in text and "lost, -0.012% a trade" in text
    assert "No trades today." in fmt.day_end_message(ledger(Repo([]), "paper", "today", now=NOW))
