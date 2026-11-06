"""The Modes tab. Since 9.0 there are two modes and nothing in between:

  balanced  the portfolio: long, swing and short books, 15-minute candles,
            the research and news gates at their balanced setting.
  ultra     fast trading: one-minute candles, a look every ten seconds, the
            confluence vote of nine indicators, every CPU core and the
            world's news feeds; up to the whole account in play.

  switches  news trading, self-improvement, discovery, the AI check ...

Neither mode changes a safety gate: Stop, the daily loss limit, the safety
pauses, arming and the stops at the broker are the same in both.

Who decides (full auto / ask me / ideas only) is the profile's autonomy
(PATCH /api/profile); real money and arming stay on /api/mode and /api/arm.

Also here: /api/readiness (is it trading, and if not why) and /api/memory
(what it learned and how far it grew).
"""
from __future__ import annotations

import secrets as pysecrets

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from app.config import HOME

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}

MODES = ("balanced", "ultra")
# What each mode sets on the research desk besides Ultra itself.
MODE_SETTINGS = {
    "balanced": {"quality_mode": "BALANCED", "news_min_confidence": 0.6, "power": "full"},
    "ultra": {"quality_mode": "BALANCED", "news_min_confidence": 0.55, "power": "full"},
}
SWITCHES = ("news_trading", "self_improve", "discover", "ai_check", "learning", "news_check", "auto_eco")


def mode_of(settings) -> str:
    return "ultra" if getattr(settings, "ultra", False) else "balanced"


def build_mode_router(engine, token: str) -> APIRouter:
    router = APIRouter(prefix="/api")

    def require_token(t: str = Query(default="", alias="token")) -> None:
        if token and not pysecrets.compare_digest(t, token):
            raise HTTPException(status_code=401, detail="invalid token")

    def require_owner(request: Request, t: str = Query(default="", alias="token")) -> None:
        if token:
            if pysecrets.compare_digest(t, token):
                return
            raise HTTPException(status_code=401, detail="invalid token")
        if (request.client.host if request.client else "") not in LOCAL_HOSTS:
            raise HTTPException(status_code=403, detail="Modes can only be changed on the PC running the bot.")

    guarded = [Depends(require_token)]
    owner = [Depends(require_owner)]

    def brain():
        b = getattr(engine, "brain", None)
        if b is None:
            raise HTTPException(status_code=503, detail="The research desk is not running.")
        return b

    def view() -> dict:
        b = getattr(engine, "brain", None)
        s = b.settings if b is not None else None
        return {
            "mode": mode_of(s) if s else "balanced",
            "autonomy": engine.autonomy,
            "money": {"mode": engine.mode, "broker": engine.executor.broker, "armed": engine.risk.armed},
            "switches": {k: bool(getattr(s, k, True)) for k in SWITCHES} if s else {},
            "bots": getattr(s, "bots", 0) if s else 0,
            "scan_interval": engine.config.scan_interval_seconds,
            "watching": len(engine.watched_symbols()),
            "home": str(HOME),
        }

    @router.get("/modes", dependencies=guarded)
    def modes() -> dict:
        return view()

    @router.post("/modes", dependencies=owner)
    def set_modes(changes: dict = Body(...)) -> dict:
        b = brain()
        update: dict = {}
        mode = changes.get("mode")
        if mode is None and changes.get("speed") is not None:     # before 9.0
            mode = "ultra" if changes["speed"] == "ultra" else "balanced"
        if mode is not None:
            if mode not in MODES:
                raise HTTPException(status_code=400, detail="mode must be balanced or ultra")
            if mode == "ultra" and not b.settings.ultra and not changes.get("confirm"):
                raise HTTPException(status_code=400, detail="Ultra needs confirm=true after the warning.")
            if mode == "balanced" and b.settings.ultra:
                b.apply_settings({"ultra": False})
            update.update(MODE_SETTINGS[mode])
            if mode == "ultra":
                update["ultra"] = True
        for key in SWITCHES:
            if key in changes:
                update[key] = bool(changes[key])
        if update:
            b.apply_settings(update)
        engine.events.publish("status", engine.status())
        return view()

    @router.get("/readiness", dependencies=guarded)
    def readiness() -> dict:
        from app.engine.readiness import readiness as build

        return build(engine, getattr(engine, "brain", None), getattr(engine, "reflex", None))

    @router.get("/scorecard", dependencies=guarded)
    def scorecard() -> dict:
        from app.engine.scorecard import scorecard as build

        return build(engine, getattr(engine, "language", "en") == "tr")

    @router.get("/portfolio", dependencies=guarded)
    def portfolio() -> dict:
        if getattr(engine, "style", "") == "scalp":
            return engine.scalper.snapshot()
        return engine.books.snapshot()

    @router.post("/portfolio/review", dependencies=owner)
    def portfolio_review() -> dict:
        """Run the daily review now (it still only trades while the market is open)."""
        rows = engine.books.review(force=True)
        return {"done": rows, **engine.books.snapshot()}

    @router.get("/desk", dependencies=guarded)
    def desk() -> dict:
        from app.engine.desk import report

        return report(engine, getattr(engine, "language", "en") == "tr")

    @router.get("/memory", dependencies=guarded)
    def memory() -> dict:
        from app.brain.memory_report import report

        return report(engine, getattr(engine, "language", "en") == "tr")

    return router
