from __future__ import annotations

from app.common.models import ClosedTrade, Position

UP = "▲"
DOWN = "▼"


def money(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def signed(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:+,.{digits}f}"


def signal_message(signal: dict) -> str:
    """The message you act on inside Midas."""
    is_exit = signal.get("kind") == "exit"
    symbol = signal["symbol"]

    if is_exit:
        head = f"*CLOSE {symbol}*"
        body = [
            f"Sell {signal['qty']:g} shares at about `{money(signal['price'])}`",
            "",
            f"_Why:_ {signal['reason']}",
        ]
    else:
        side = signal["side"].upper()
        head = f"*{side} {symbol}*"
        body = [
            f"Buy {signal['qty']:g} shares at about `{money(signal['price'])}`",
            f"Position size `${money(signal['notional'])}`",
            "",
            f"Stop-loss  `{money(signal['stop_loss'])}`",
            f"Take-profit `{money(signal['take_profit'])}`",
            f"Risk `${money(signal['risk_amount'])}` for `{signal['reward_risk']:.1f}:1`",
            "",
            f"_Why:_ {signal['reason']}",
        ]

    body.append("")
    body.append("Place it in Midas, then tell me below.")
    return f"{head}\n" + "\n".join(body)


def position_line(position: dict) -> str:
    arrow = UP if position["unrealized_pnl"] >= 0 else DOWN
    return (
        f"{arrow} *{position['symbol']}* {position['qty']:g} @ "
        f"`{money(position['entry_price'])}` → `{money(position['current_price'])}`  "
        f"*{signed(position['unrealized_pnl'])}* ({signed(position['unrealized_pnl_pct'])}%)"
    )


def positions_message(positions: list[dict]) -> str:
    if not positions:
        return "No open positions right now."
    lines = ["*Open positions*", ""]
    lines += [position_line(p) for p in positions]
    total = sum(p["unrealized_pnl"] for p in positions)
    lines += ["", f"Unrealised total: *{signed(total)}*"]
    return "\n".join(lines)


def run_message(challenge: dict | None) -> str:
    if not challenge:
        return (
            "No run going right now.\n\n"
            "Open the dashboard, pick a stake and a target, and I will trade just "
            "that money until it gets there or runs out."
        )

    filled = int(round(challenge["progress_pct"] / 10))
    bar = "█" * filled + "░" * (10 - filled)
    lines = [
        f"*Run: ${money(challenge['stake'])} → ${money(challenge['target'])}*",
        "",
        f"`{bar}` {challenge['progress_pct']}%",
        "",
        f"Now: *${money(challenge['value'])}*  ({signed(challenge['gain'])})",
        f"Trades: {challenge['trades']}"
        + (f"  ·  Win rate: {challenge['win_rate']}%" if challenge["win_rate"] is not None else ""),
        f"Best so far: ${money(challenge['peak_value'])}",
        f"Stops out at: ${money(challenge['bust_floor'])}",
    ]
    if not challenge["active"]:
        verdict = {
            "won": "Target reached.",
            "lost": "Ran out of bankroll.",
            "stopped": "Stopped by you.",
        }.get(challenge["status"], challenge["status"])
        lines += ["", f"_{verdict}_"]
    return "\n".join(lines)


def challenge_event_message(challenge: dict, event: str, reason: str = "") -> str:
    if event == "won":
        return (
            f"*Run complete — target hit*\n\n"
            f"${money(challenge['stake'])} → *${money(challenge['value'])}* "
            f"in {challenge['trades']} trades."
        )
    if event == "lost":
        return (
            f"*Run over*\n\n"
            f"The bankroll fell to ${money(challenge['value'])}, through the "
            f"${money(challenge['bust_floor'])} floor, after {challenge['trades']} trades."
        )
    if event == "started":
        return (
            f"*Run started: ${money(challenge['stake'])} → ${money(challenge['target'])}*\n\n"
            "I will trade only this money, one position at a time."
        )
    return run_message(challenge)


CONVICTION_MARK = {"high": "●●●", "medium": "●●○", "low": "●○○"}


def catalysts_message(catalysts: list[dict]) -> str:
    if not catalysts:
        return (
            "No catalysts on the calendar.\n\n"
            "A catalyst is an event you expect to move a stock — a game launch, a "
            "film, a court ruling. Add one in the app and I will tell you when the "
            "entry window opens."
        )

    lines = ["*Catalysts*", ""]
    for c in catalysts:
        when = (
            f"in {c['days_away']}d" if c["days_away"] > 0
            else "today" if c["days_away"] == 0 else f"{abs(c['days_away'])}d ago"
        )
        state = (
            "window open" if c["in_entry_window"] and c["status"] != "holding"
            else "holding" if c["status"] == "holding"
            else f"opens in {c['window_opens_in']}d"
        )
        lines.append(
            f"`{c['symbol']:<5}` *{c['title']}*\n"
            f"    {c['event_date']} · {when} · {state}\n"
            f"    {CONVICTION_MARK.get(c['conviction'], '')} {c['date_confidence']}"
        )
    return "\n".join(lines)


def catalyst_window_message(c: dict) -> str:
    lines = [
        f"*Entry window open — {c['symbol']}*",
        "",
        c["title"],
        f"Event: {c['event_date']} ({c['days_away']} days away)",
    ]
    if c["thesis"]:
        lines += ["", f"_{c['thesis']}_"]
    plan = (
        "Your plan says sell into the event."
        if c["exit_rule"] == "before"
        else "Your plan says hold through the event."
    )
    lines += ["", plan]
    return "\n".join(lines)


def status_message(status: dict) -> str:
    market = status["market"]
    risk = status["risk"]
    state = "OPEN" if market["is_open"] else "CLOSED"

    lines = [
        f"*Money Tree AI* — {status['mode']} mode",
        "",
        f"Market: *{state}* ({market['countdown']})",
        f"Equity: *${money(status['equity'])}*",
        f"Cash: `${money(status['balance']['available'])}`",
        f"Today: *{signed(risk['daily_realized_pnl'])}* "
        f"(limit ${money(risk['daily_loss_limit'])}, {risk['daily_loss_used_pct']}% used)",
        f"Open positions: {len(status['positions'])}",
        f"Watching: {len(status['watchlist'])} symbols on {status['timeframe']}",
    ]

    locks = status.get("locks") or []
    if locks:
        worst = max(locks, key=lambda l: l["minutes_left"])
        scope = worst["symbol"] or "all symbols"
        lines.append(f"Paused: {worst['reason']} — {scope}, {worst['minutes_left']}m left")

    if status["mode"] == "live":
        lines.append(f"Live trading: *{'ARMED' if risk['armed'] else 'disarmed'}*")
    if status.get("pending_signals"):
        lines.append(f"Waiting on you: {len(status['pending_signals'])} signal(s)")
    if not status["running"]:
        lines.append("_Engine is stopped._")
    return "\n".join(lines)


def proposal_message(proposal: dict) -> str:
    """A semi-auto buy waiting for a tap, or a manual-mode suggestion."""
    asking = proposal["kind"] == "approval"
    head = (
        f"*Approve buying {proposal['symbol']}?*" if asking
        else f"*Idea: {proposal['symbol']}* (manual — I am not placing it)"
    )
    lines = [
        head,
        "",
        f"{proposal['qty']:g} shares at about `{money(proposal['price'])}` "
        f"(`${money(proposal['qty'] * proposal['price'])}`)",
    ]
    if proposal.get("stop_loss"):
        lines.append(f"Stop `{money(proposal['stop_loss'])}` · "
                     f"Target `{money(proposal.get('take_profit'))}`")
    lines.append(f"_{proposal.get('reason', '')}_")
    if asking:
        lines += ["", "Expires in 15 minutes. It is re-checked against the price when you tap."]
    return "\n".join(lines)


def heartbeat_message(status: dict, uptime_seconds: float) -> str:
    """The periodic "still here" ping — one glance, not a report.

    The point is that silence becomes meaningful: if these stop arriving, the
    bot (or the PC it runs on) is down. So it also says plainly when the bot is
    up but not actually doing its job.
    """
    hours, rem = divmod(int(uptime_seconds), 3600)
    minutes = rem // 60
    uptime = f"{hours}h {minutes}m" if hours else f"{minutes}m"
    market = "open" if status["market"]["is_open"] else "closed"

    lines = [
        f"*Money Tree is still up* — {uptime}",
        f"{status['mode']} mode · equity *${money(status['equity'])}* · "
        f"{len(status['positions'])} open · market {market}",
    ]
    if not status["running"]:
        lines.append("_Engine is stopped — it is not scanning._")
    if status.get("last_error"):
        lines.append(f"_Last error:_ `{str(status['last_error'])[:120]}`")
    return "\n".join(lines)


def watchlist_message(rows: list[dict]) -> str:
    ready = [r for r in rows if r.get("ready")]
    if not ready:
        return "Still gathering data — nothing to show yet."

    lines = ["*Watchlist*", ""]
    for row in sorted(ready, key=lambda r: r.get("spread_pct") or 0, reverse=True):
        trend = UP if row["trend"] == "up" else DOWN
        held = " ·held" if row.get("position") else ""
        rsi = f"{row['rsi']:.0f}" if row.get("rsi") is not None else "—"
        lines.append(
            f"{trend} `{row['symbol']:<5}` {money(row['price'])}  "
            f"{signed(row.get('spread_pct'))}%  RSI {rsi}{held}"
        )
    return "\n".join(lines)


def trade_closed_message(trade: dict) -> str:
    won = trade["pnl"] >= 0
    head = "Closed a winner" if won else "Closed a loser"
    return (
        f"*{head}: {trade['symbol']}*\n\n"
        f"`{money(trade['entry_price'])}` → `{money(trade['exit_price'])}`\n"
        f"P&L *{signed(trade['pnl'])}* ({signed(trade['pnl_pct'])}%)\n"
        f"_Reason:_ {trade['exit_reason']}"
    )


def stats_message(stats: dict) -> str:
    if not stats["total_trades"]:
        return "No closed trades yet."
    return "\n".join(
        [
            "*Performance*",
            "",
            f"Trades: {stats['total_trades']}  ({stats['wins']}W / {stats['losses']}L)",
            f"Win rate: {stats['win_rate']}%",
            f"Total P&L: *{signed(stats['total_pnl'])}*",
            f"Profit factor: {stats['profit_factor']}",
            f"Best: {signed(stats['best_trade'])}   Worst: {signed(stats['worst_trade'])}",
        ]
    )


def position_to_dict(position: Position) -> dict:
    return position.to_dict()


def trade_to_dict(trade: ClosedTrade) -> dict:
    return {
        "symbol": trade.symbol,
        "entry_price": trade.entry_price,
        "exit_price": trade.exit_price,
        "pnl": round(trade.pnl, 2),
        "pnl_pct": round(trade.pnl_pct, 2),
        "exit_reason": trade.exit_reason,
    }


def memory_message(facts: list[dict]) -> str:
    if not facts:
        return (
            "I have not been told to remember anything yet.\n"
            "Try /remember I trade in Midas, not Alpaca."
        )
    lines = ["*What I remember*", ""]
    lines += [f"{i}. {f['text']}" for i, f in enumerate(facts, start=1)]
    lines += ["", "_/forget N drops one._"]
    return "\n".join(lines)
