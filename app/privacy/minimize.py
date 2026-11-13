"""What the AI may see of the account (10.1): the levels in app/privacy/prefs.py.

mentor_context() builds one picture of the bot for every AI call (the chat,
Telegram). It is passed through here, so a level is kept everywhere.

  full     unchanged
  percent  symbols, prices of the market and percentages stay; the balance,
           equity, share counts and every dollar profit, loss or risk amount go
  none     nothing about the account: only the market's open or closed state
"""
from __future__ import annotations

# Keys whose value is the owner's money or size. Prices of stocks are public
# and stay; what the owner paid, owns or made does not.
MONEY_KEYS = frozenset({
    "equity", "balance", "cash", "available", "buying_power", "total", "starting_balance",
    "qty", "quantity", "market_value", "cost", "cost_basis", "value",
    "unrealized_pnl", "pnl", "total_pnl", "realised", "unrealised", "best_trade", "worst_trade",
    "avg_win", "avg_loss", "daily_loss", "daily_pnl", "loss_today", "risk_amount", "max_loss",
})


def scrub(value):
    """A copy without the money keys, at any depth."""
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items() if k not in MONEY_KEYS}
    if isinstance(value, list):
        return [scrub(v) for v in value]
    return value


def apply(context: dict, level: str) -> dict:
    if level == "percent":
        return scrub(context)
    if level == "none":
        market = context.get("market") or {}
        return {"mode": context.get("mode"), "market": {"is_open": market.get("is_open")},
                "note": "The owner chose not to share account data with the AI."}
    return context


def trade_facts(symbol: str, price: float, reason: str, qty: float, risk_usd: float | None,
                stop: float | None, target: float | None, level: str) -> str:
    """The sentence given to the AI after a buy, cut to the level."""
    if level == "none":
        return f"Bought {symbol}. Rule that fired: {reason}. "
    out = f"Bought {symbol} at {price:.2f}. " if level == "percent" else f"Bought {qty:g} {symbol} at {price:.2f}. "
    out += f"Rule that fired: {reason}. "
    if stop and target:
        out += f"Stop-loss {stop:.2f}, target {target:.2f}. "
        if risk_usd is not None and level == "full":
            out += f"Money at risk if the stop fills: {risk_usd:.2f} USD. "
    return out
