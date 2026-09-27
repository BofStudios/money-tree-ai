"""What pops up from the Windows tray when something happens to the money.

Only the moments worth an interruption — a buy, a sell, a buy waiting for the
owner's OK — the same ones the phone app notifies about. Everything else stays
in the Live tab. Kept free of Qt so it can be tested on its own.
"""
from __future__ import annotations

from app.engine.words import Words


def notice_for(event: dict, words: Words) -> tuple[str, str] | None:
    """(title, body) for an engine event, or None when it is not worth a pop-up."""
    kind = event.get("type")
    try:
        if kind == "trade_opened":
            position = event["position"]
            return words.notice_bought(position["symbol"], float(position["qty"]), float(position["entry_price"]))
        if kind == "trade_closed":
            return words.notice_sold(event["symbol"], float(event["pnl"]), event.get("exit_reason") or "")
        if kind == "approval_needed":
            proposal = event["proposal"]
            return words.notice_approval(proposal["symbol"], float(proposal["qty"]), float(proposal["price"]))
    except (KeyError, TypeError, ValueError):
        return None
    return None
