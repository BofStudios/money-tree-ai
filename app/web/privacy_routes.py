"""The Privacy and data screen (10.1).

  GET   /api/privacy           the choices, every server the app talks to, your files, phone access
  PATCH /api/privacy           change a choice (AI level, chat memory, phone access, log days ...)
  GET   /api/privacy/ai-last   exactly what the AI was last sent
  POST  /api/privacy/export    a zip of your data in <data home>/exports (never keys or the password)
  POST  /api/privacy/open      open the data folder (this PC only)
  POST  /api/privacy/clear     clear chat | learned | lab | logs | all (all = those four)
  POST  /api/privacy/password  make a new dashboard password (phones must sign in again)

Clearing goes through the running app, never by deleting files under it. The
trade history and the keys are not cleared here (see app/privacy/data.py).
"""
from __future__ import annotations

import logging
import os
import secrets
import sys
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from app import __version__
from app.common.home import root as data_home
from app.config import DATA_DIR, LOG_DIR
from app.privacy import data as mydata
from app.privacy import hosts as hostlist
from app.privacy.prefs import AI_LEVELS, LOG_DAYS
from app.web.auth import COOKIE, COOKIE_DAYS, LOCAL_HOSTS, Auth, address_of

log = logging.getLogger(__name__)

CLEAR_WORDS = {"delete", "sil"}


def build_privacy_router(engine, repo, claude, restarter, token) -> APIRouter:
    router = APIRouter(prefix="/api/privacy")
    auth = token if isinstance(token, Auth) else Auth(token)
    guarded = [Depends(auth.guard())]
    owner = [Depends(auth.owner("Privacy choices can only be changed on the PC running the bot."))]

    def prefs():
        got = getattr(engine, "privacy", None)
        if got is None:
            raise HTTPException(status_code=503, detail="The privacy choices are not ready.")
        return got

    def home():
        return data_home()

    @router.get("", dependencies=guarded)
    def view() -> dict:
        p = prefs()
        return {
            "version": __version__,
            "choices": p.all(),
            "options": {"ai_levels": list(AI_LEVELS), "log_days": list(LOG_DAYS)},
            "hosts": hostlist.as_dicts("desktop"),
            "files": mydata.inventory(home()),
            "home": str(home()),
            "phone": {"on": bool(p.get("lan")), "asked": bool(p.get("lan_asked"))},
            "can_look": bool(claude is not None and claude.can_look()),
            "remembers": bool(p.get("remember_chat")),
        }

    @router.patch("", dependencies=owner)
    def change(body: dict = Body(...)) -> dict:
        p = prefs()
        before = p.all()
        try:
            after = p.update(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        if "log_days" in body:
            mydata.prune_logs(LOG_DIR, after["log_days"])
        restart = after["lan"] != before["lan"]
        return {"choices": after, "restart_needed": restart}

    @router.get("/ai-last", dependencies=guarded)
    def ai_last() -> dict:
        last = getattr(claude, "last_sent", None) if claude is not None else None
        return {"last": last}

    @router.post("/export", dependencies=owner)
    def export() -> dict:
        trades = repo.recent_trades(engine.mode, limit=100000)
        out = mydata.export_zip(home(), trades)
        return {"path": str(out), "bytes": out.stat().st_size, "folder": str(out.parent)}

    @router.post("/open", dependencies=owner)
    def open_folder(request: Request) -> dict:
        if address_of(request) not in LOCAL_HOSTS:
            raise HTTPException(status_code=403, detail="The folder opens on the PC running the bot.")
        target = str(home())
        try:
            if sys.platform == "win32":
                os.startfile(target)        # noqa: S606 - the owner's own data folder
            else:
                raise HTTPException(status_code=501, detail=f"Open this folder yourself: {target}")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from None
        return {"ok": True}

    @router.post("/clear", dependencies=owner)
    def clear(body: dict = Body(...)) -> dict:
        group = str(body.get("group", ""))
        if group not in (*mydata.CLEARABLE, "all"):
            raise HTTPException(status_code=400, detail="Choose chat, learned, lab, logs or all.")
        if group == "all" and str(body.get("confirm", "")).strip().lower() not in CLEAR_WORDS:
            raise HTTPException(status_code=400, detail="Type the word to confirm.")
        done = []
        for g in (mydata.CLEARABLE if group == "all" else (group,)):
            if g == "chat" and claude is not None:
                claude.memory.wipe()
                done.append(g)
            elif g == "learned" and getattr(engine, "brain", None) is not None:
                engine.brain.forget()
                done.append(g)
            elif g == "lab" and getattr(engine, "lab", None) is not None:
                engine.lab.clear()
                done.append(g)
            elif g == "logs":
                mydata.prune_logs(LOG_DIR, 0)
                done.append(g)
        return {"ok": True, "cleared": done}

    @router.post("/password", dependencies=owner)
    def new_password(response: Response) -> dict:
        path = DATA_DIR / "dashboard.token"
        try:
            kept = path.read_text(encoding="utf-8").strip()
        except OSError:
            kept = ""
        if not kept or kept != auth.token:
            raise HTTPException(status_code=409, detail=(
                "The password comes from DASHBOARD_TOKEN in your settings. Change it there."))
        fresh = secrets.token_urlsafe(32)
        path.write_text(fresh, encoding="utf-8")
        auth.token = fresh
        response.set_cookie(COOKIE, fresh, max_age=COOKIE_DAYS * 86400, httponly=True, samesite="strict", path="/")
        log.info("dashboard password renewed at %s", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return {"ok": True, "message": "New password made. Other devices must open the new phone link."}

    @router.post("/restart", dependencies=owner)
    def restart() -> dict:
        if restarter is None:
            raise HTTPException(status_code=503, detail="Restarting is not available here.")
        restarter.request()
        return {"ok": True}

    return router
