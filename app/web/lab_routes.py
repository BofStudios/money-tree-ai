"""The Lab tab (10.0): the replay of Ultra's rules and the trade analytics.

  GET  /api/lab          the last replay, the edge filter, whether one is running
  POST /api/lab/run      replay now (its own thread; about 40 seconds)
  POST /api/lab/edge     {"on": bool}: skip symbols the replay lost on
  GET  /api/analytics    the numbers of the real, finished trades

Nothing here trades or changes a safety gate. The edge filter only removes
buys; turning it off gives Ultra back the 9.0 list.
"""
from __future__ import annotations

import secrets as pysecrets

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from app.engine.analytics import analyse

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def build_lab_router(engine, repo, token: str) -> APIRouter:
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
            raise HTTPException(status_code=403, detail="The Lab can only be changed on the PC running the bot.")

    guarded = [Depends(require_token)]
    owner = [Depends(require_owner)]

    def lab():
        got = getattr(engine, "lab", None)
        if got is None:
            raise HTTPException(status_code=503, detail="The Lab is not ready.")
        return got

    @router.get("/lab", dependencies=guarded)
    def lab_view() -> dict:
        return lab().status()

    @router.post("/lab/run", dependencies=owner)
    def lab_run() -> dict:
        started = lab().start()
        return {"ok": True, "started": started, "running": lab().running}

    @router.post("/lab/edge", dependencies=owner)
    def lab_edge(body: dict = Body(default={})) -> dict:
        if not isinstance(body.get("on"), bool):
            raise HTTPException(status_code=400, detail='Send {"on": true} or {"on": false}.')
        lab().set_edge(body["on"])
        return {"ok": True, "edge": lab().edge_on}

    @router.get("/analytics", dependencies=guarded)
    def analytics() -> dict:
        trades = repo.recent_trades(engine.mode, limit=5000)
        curve = repo.equity_curve(engine.mode, days=365)
        return {"mode": engine.mode, **analyse(trades, curve)}

    return router
