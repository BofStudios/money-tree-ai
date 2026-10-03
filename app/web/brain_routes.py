"""The research desk and the swarm, for the dashboard.

Reading is open to anyone holding the dashboard token; changing how the brain
trades (gates, bots, power) and resetting what it learned is for the owner —
this PC, or a device with the token — like keys and the money mode.
"""
from __future__ import annotations

import secrets as pysecrets

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
SETTABLE = {"quality_mode", "news_check", "learning", "ai_check", "self_improve", "discover", "bots", "power", "warned"}


def build_brain_router(engine, token: str) -> APIRouter:
    router = APIRouter(prefix="/api")

    def require_token(t: str = Query(default="", alias="token")) -> None:
        if token and not pysecrets.compare_digest(t, token):
            raise HTTPException(status_code=401, detail="invalid token")

    def require_owner(request: Request, t: str = Query(default="", alias="token")) -> None:
        if token:
            if pysecrets.compare_digest(t, token):
                return
            raise HTTPException(status_code=401, detail="invalid token")
        host = request.client.host if request.client else ""
        if host not in LOCAL_HOSTS:
            raise HTTPException(status_code=403, detail="The brain's settings can only be changed on the PC running the bot.")

    guarded = [Depends(require_token)]
    owner = [Depends(require_owner)]

    def brain():
        b = getattr(engine, "brain", None)
        if b is None:
            raise HTTPException(status_code=503, detail="The research desk is not running.")
        return b

    def watched() -> list[str]:
        with engine._lock:
            return engine._scan_symbols()

    @router.get("/brain", dependencies=guarded)
    def get_brain() -> dict:
        return brain().snapshot(watched())

    @router.post("/brain/settings", dependencies=owner)
    def set_brain(changes: dict = Body(...)) -> dict:
        unknown = set(changes) - SETTABLE
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown settings: {', '.join(sorted(unknown))}")
        b = brain()
        s = b.apply_settings(changes)
        engine.scan_now()
        return {"ok": True, "settings": s.__dict__}

    @router.post("/brain/forget", dependencies=owner)
    def forget() -> dict:
        brain().forget()
        return {"ok": True}

    @router.get("/swarm", dependencies=guarded)
    def get_swarm() -> dict:
        b = brain()
        snap = b.swarm.snapshot()
        snap["settings"] = {"bots": b.settings.bots, "power": b.settings.power, "self_improve": b.settings.self_improve}
        return snap

    @router.post("/swarm/reset", dependencies=owner)
    def reset() -> dict:
        p = brain().swarm.reset()
        engine.scan_now()
        return {"ok": True, "rollback": p.to_dict() if p else None}

    return router
