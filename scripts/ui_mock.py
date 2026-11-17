"""A stand-in server for building the console's page without the engine (12.0).

    python scripts/ui_mock.py --static app/web/static --port 8820

Serves the static folder, answers /api/bot* from tests/fixtures, and plays
tests/fixtures/bot_log.jsonl once over the web socket. Only on 127.0.0.1, no
password. A developer tool: it is never part of a build.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"


def build(static: Path, fixture: str = "open", live: bool = False) -> FastAPI:
    app = FastAPI()
    tail = "" if fixture == "open" else f"_{fixture}"
    snap = json.loads((FIXTURES / f"bot_snapshot{tail}.json").read_text(encoding="utf-8"))
    if live:   # a connected real account with an amount set: the console as the owner sees it
        snap["account"].update(mode="live", armed=True)
        snap["setup"] = {"keys": True, "live": True, "amount": True, "armed": True, "next": None}
        snap["risk"]["budget"] = snap["tiles"]["capital"]["budget"] = 500.0
    lines = [json.loads(r) for r in (FIXTURES / f"bot_log{tail}.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    start = max(0, len(lines) - 60)          # the first part is already "there", the rest is played
    played = {"n": start}

    @app.get("/api/bot")
    def bot() -> dict:
        shown = lines[:played["n"]]
        return {**snap, "log_head": shown[-1]["n"] if shown else 0}

    @app.get("/api/bot/log")
    def log(after: int = 0, limit: int = 200, agent: str | None = None, tab: str | None = None,
            before: int | None = None) -> dict:
        verbs = {"orders": ("order", "fill", "partial", "exit", "stop", "target"),
                 "risk": ("veto", "pause", "resume", "arm", "disarm")}.get(tab or "")
        rows = [l for l in lines[:played["n"]]
                if l["n"] > after and (before is None or l["n"] < before)
                and (not agent or l["agent"] == agent) and (verbs is None or l["verb"] in verbs)]
        head = lines[played["n"] - 1]["n"] if played["n"] else 0
        return {"head": head, "lines": rows[:limit] if after and before is None else rows[-limit:]}

    @app.get("/api/bot/ledger")
    def ledger(range: str = "today") -> dict:
        return {"range": range, "fills": [], "curve": [],
                "sum": {"count": 0, "wins": 0, "pnl": 0.0, "fees": 0.0, "best": 0.0, "worst": 0.0,
                        "profit_factor": None, "avg_minutes": None}}

    @app.websocket("/api/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        try:
            while played["n"] < len(lines):
                await asyncio.sleep(random.uniform(0.35, 1.0))
                await socket.send_json({"type": "bot_log", "line": lines[played["n"]]})
                played["n"] += 1
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            pass

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PATCH", "DELETE"])
    def other(rest: str) -> dict:
        return {}

    app.mount("/", StaticFiles(directory=str(static), html=True), name="static")
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--static", default=str(ROOT / "app" / "web" / "static"))
    parser.add_argument("--port", type=int, default=8820)
    parser.add_argument("--fixture", choices=["open", "closed"], default="open",
                        help="open: market open, no trades; closed: market closed, Ultra on, the Lab's proof says lost")
    parser.add_argument("--live", action="store_true", help="pretend a real account is connected, armed, with $500 set")
    args = parser.parse_args()
    uvicorn.run(build(Path(args.static), args.fixture, args.live), host="127.0.0.1", port=args.port, log_level="warning")
