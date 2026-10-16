"""The honest scorecard: did the bot beat simply buying SPY and waiting?

Since the first day the app recorded this account's equity (at most 90 days
back), compare:

  the bot   equity now against equity then, plus the money its finished
            trades made or lost (deposits do not change that part)
  SPY       the same starting money put into SPY on that day and held

If the bot is behind, the card says so plainly. A bot that cannot beat doing
nothing is worth knowing about early, before more money goes in.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

log = logging.getLogger(__name__)

WINDOW_DAYS = 90
SPY_TTL = 600.0

_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def _spy_daily(data):
    with _lock:
        hit = _cache.get("spy")
        if hit and time.time() - hit[0] < SPY_TTL:
            return hit[1]
    try:
        bars = data.get_ohlcv("SPY", "1d", limit=WINDOW_DAYS + 10)
    except Exception as exc:
        log.info("could not read SPY for the scorecard: %s", exc)
        bars = None
    with _lock:
        _cache["spy"] = (time.time(), bars)
    return bars


def scorecard(engine, turkish: bool = False) -> dict:
    def t(en: str, tr: str) -> str:
        return tr if turkish else en

    curve = engine.repo.equity_curve(engine.mode, days=WINDOW_DAYS)
    stats = engine.repo.trade_stats(engine.mode)
    out = {"ready": False, "days": 0, "bot_pct": None, "spy_pct": None, "start_equity": None,
           "equity": None, "spy_value": None, "realised": round(stats["total_pnl"], 2),
           "trades": stats["total_trades"], "win_rate": stats["win_rate"], "verdict": "", "headline": "",
           "note": t("Deposits and withdrawals change the equity numbers; the money from finished trades does not.",
                     "Para yatırma ve çekme bakiye rakamlarını değiştirir; biten işlemlerin kazancı değişmez.")}
    if len(curve) < 2:
        out["headline"] = t("Not enough history yet. The scorecard starts after the first day.",
                            "Henüz yeterli geçmiş yok. Karne ilk günden sonra başlar.")
        return out
    first_t, first_eq = curve[0]["time"], curve[0]["value"]
    last_eq = curve[-1]["value"]
    days = max((time.time() - first_t) / 86400, 0.0)
    out.update(days=round(days, 1), start_equity=first_eq, equity=last_eq)
    if first_eq <= 0:
        return out
    out["bot_pct"] = round((last_eq / first_eq - 1) * 100, 2)

    bars = _spy_daily(engine.data)
    if bars is not None and len(bars) >= 2:
        start = datetime.fromtimestamp(first_t, timezone.utc)
        idx = [ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts for ts in bars.index]
        before = [i for i, ts in enumerate(idx) if (ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)) <= start]
        base = float(bars["close"].iloc[before[-1]]) if before else float(bars["open"].iloc[0])
        now = float(bars["close"].iloc[-1])
        if base > 0:
            out["spy_pct"] = round((now / base - 1) * 100, 2)
            out["spy_value"] = round(first_eq * now / base, 2)

    out["ready"] = days >= 1
    bot, spy = out["bot_pct"], out["spy_pct"]
    if stats["total_trades"] == 0 and not engine.status_positions():
        out["verdict"] = "idle"
        out["headline"] = t("No trades yet, so this only compares cash with SPY"
                            + (f" ({spy:+.2f}%)." if spy is not None else "."),
                            "Henüz işlem yok; bu sadece nakdi SPY ile karşılaştırır"
                            + (f" (%{spy:+.2f})." if spy is not None else "."))
    elif spy is None:
        out["verdict"] = "unknown"
        out["headline"] = t("SPY prices are not available right now.", "SPY fiyatları şu an alınamıyor.")
    elif bot >= spy:
        out["verdict"] = "ahead"
        out["headline"] = t(f"The bot is ahead of SPY: {bot:+.2f}% against {spy:+.2f}% in {days:.0f} days.",
                            f"Bot SPY'ın önünde: {days:.0f} günde %{bot:+.2f}, SPY %{spy:+.2f}.")
    else:
        out["verdict"] = "behind"
        out["headline"] = t(f"The bot is behind SPY: {bot:+.2f}% against {spy:+.2f}% in {days:.0f} days. "
                            "Holding SPY would have done better so far.",
                            f"Bot SPY'ın gerisinde: {days:.0f} günde %{bot:+.2f}, SPY %{spy:+.2f}. "
                            "Şimdiye kadar SPY tutmak daha iyi olurdu.")
    if days < 14:
        out["headline"] += " " + t("Under two weeks says little; look again later.",
                                   "İki haftadan kısa süre pek bir şey söylemez; sonra tekrar bak.")
    return out
