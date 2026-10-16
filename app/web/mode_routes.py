"""The Modes tab: every way the bot can run, in one place, as a few big choices.

  speed     Eco (light bots) · Normal · Ultra (every core, the world's feeds)
  style     Careful · Balanced · Bold: how sure the research and the news
            must be before a buy. The risk limits do not change with it.
  switches  news trading, self-improvement, discovery, the AI check ...

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

STYLES = {
    "careful": {"quality_mode": "STRICT", "news_min_confidence": 0.75},
    "balanced": {"quality_mode": "BALANCED", "news_min_confidence": 0.6},
    "bold": {"quality_mode": "OFF", "news_min_confidence": 0.55},
}
SWITCHES = ("news_trading", "self_improve", "discover", "ai_check", "learning", "news_check", "auto_eco")


def style_of(settings) -> str:
    for name, values in STYLES.items():
        if settings.quality_mode == values["quality_mode"] and \
                abs(float(settings.news_min_confidence) - values["news_min_confidence"]) < 0.001:
            return name
    return "custom"


def speed_of(settings) -> str:
    if settings.ultra:
        return "ultra"
    return "eco" if settings.power == "light" else "normal"


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
            "speed": speed_of(s) if s else "normal",
            "style": style_of(s) if s else "balanced",
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
        speed = changes.get("speed")
        if speed is not None:
            if speed not in ("eco", "normal", "ultra"):
                raise HTTPException(status_code=400, detail="speed must be eco, normal or ultra")
            if speed == "ultra" and not b.settings.ultra and not changes.get("confirm"):
                raise HTTPException(status_code=400, detail="Ultra needs confirm=true after the warning.")
            if speed == "ultra":
                update["ultra"] = True
            else:
                if b.settings.ultra:
                    b.apply_settings({"ultra": False})
                update["power"] = "light" if speed == "eco" else "full"
        style = changes.get("style")
        if style is not None:
            if style not in STYLES:
                raise HTTPException(status_code=400, detail="style must be careful, balanced or bold")
            update.update(STYLES[style])
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

    @router.get("/memory", dependencies=guarded)
    def memory() -> dict:
        from app.brain.memory_report import report

        return report(engine, getattr(engine, "language", "en") == "tr")

    return router
