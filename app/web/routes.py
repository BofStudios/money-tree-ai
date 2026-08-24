from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.catalysts.manager import CatalystManager, parse_date
from app.catalysts.news import NewsFeed
from app.common.models import Position
from app.config import Settings
from app.engine.portfolio_engine import PortfolioEngine
from app.execution.signal_executor import SignalExecutor, _build_trade
from app.mentor.ai import AIMentor
from app.mentor.narrator import Narrator
from app.storage.repository import Repository
from app.web.ws import WebSocketHub

log = logging.getLogger(__name__)


def build_router(
    engine: PortfolioEngine,
    repo: Repository,
    mentor: Narrator,
    claude: AIMentor,
    hub: WebSocketHub,
    token: str,
    settings: Settings | None = None,
    catalysts: CatalystManager | None = None,
    news: NewsFeed | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    def require_token(t: str = Query(default="", alias="token")) -> None:
        """Blocks other devices on the network from driving the bot.

        An empty configured token means local-only use with no check.
        """
        if not token:
            return
        if not secrets.compare_digest(t, token):
            raise HTTPException(status_code=401, detail="invalid token")

    guarded = [Depends(require_token)]

    # ------------------------------------------------------------------- reads

    @router.get("/status", dependencies=guarded)
    def status() -> dict:
        return engine.status()

    @router.get("/candles/{symbol}", dependencies=guarded)
    def candles(symbol: str) -> dict:
        symbol = symbol.upper()
        return {
            "symbol": symbol,
            "candles": engine.candles(symbol),
            "overlays": engine.overlays(symbol),
        }

    @router.get("/trades", dependencies=guarded)
    def trades() -> dict:
        return {
            "trades": repo.recent_trades(engine.mode, limit=60),
            "stats": repo.trade_stats(engine.mode),
        }

    @router.get("/equity", dependencies=guarded)
    def equity() -> dict:
        return {"curve": repo.equity_curve(engine.mode, days=30)}

    @router.get("/mentor", dependencies=guarded)
    def mentor_lines(limit: int = 200) -> dict:
        return {
            "lines": mentor.lines(limit),
            "claude": claude.available,   # kept for older dashboards
            "ai": claude.backend,
            "memory": claude.memory.facts(),
        }

    @router.post("/mentor/memory", dependencies=guarded)
    def mentor_remember(text: str = Body(..., embed=True)) -> dict:
        try:
            fact = claude.memory.remember(text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"fact": fact, "memory": claude.memory.facts()}

    @router.delete("/mentor/memory/{index}", dependencies=guarded)
    def mentor_forget(index: int) -> dict:
        if not claude.memory.forget(index):
            raise HTTPException(status_code=404, detail="no such memory")
        return {"memory": claude.memory.facts()}

    @router.get("/challenge", dependencies=guarded)
    def challenge() -> dict:
        manager = engine.challenges
        if manager is None:
            return {"enabled": False}
        active = manager.active()
        cfg = engine.config.challenge
        return {
            "enabled": cfg.enabled,
            "active": active.to_dict() if active else None,
            "history": manager.history(),
            "presets": cfg.presets,
            "multipliers": cfg.multipliers,
            "default_stake": cfg.default_stake,
            "default_multiplier": cfg.default_multiplier,
            "currency": engine.executor.get_balance().currency,
        }

    @router.post("/challenge/odds", dependencies=guarded)
    def challenge_odds(
        stake: float = Body(..., embed=True), target: float = Body(..., embed=True)
    ) -> dict:
        if engine.challenges is None:
            raise HTTPException(status_code=400, detail="challenges are not enabled")
        return engine.challenges.odds(stake, target)

    @router.post("/challenge/start", dependencies=guarded)
    def challenge_start(
        stake: float = Body(..., embed=True), target: float = Body(..., embed=True)
    ) -> dict:
        if engine.challenges is None:
            raise HTTPException(status_code=400, detail="challenges are not enabled")
        try:
            state = engine.challenges.start(stake, target)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        mentor.challenge_started(state, engine.challenges.odds(stake, target))
        engine.scan_now()
        return engine.status()

    @router.post("/challenge/stop", dependencies=guarded)
    def challenge_stop() -> dict:
        if engine.challenges is None or engine.challenges.stop() is None:
            raise HTTPException(status_code=400, detail="no challenge is running")
        return engine.status()

    # ------------------------------------------------------------- catalysts

    @router.get("/catalysts", dependencies=guarded)
    def list_catalysts(include_finished: bool = False) -> dict:
        if catalysts is None:
            return {"enabled": False, "catalysts": [], "news": [], "news_available": False}
        catalysts.refresh_windows()
        rows = catalysts.all(include_finished=include_finished)
        symbols = catalysts.symbols()
        headlines = news.for_symbols(symbols, limit=25) if (news and symbols) else []
        return {
            "enabled": True,
            "catalysts": [c.to_dict() for c in rows],
            "news": [h.to_dict() for h in headlines],
            "news_available": bool(news and news.available),
        }

    @router.get("/catalysts/{catalyst_id}/news", dependencies=guarded)
    def catalyst_news(catalyst_id: int) -> dict:
        if catalysts is None:
            raise HTTPException(status_code=400, detail="catalysts are not enabled")
        catalyst = catalysts.get(catalyst_id)
        if catalyst is None:
            raise HTTPException(status_code=404, detail="no such catalyst")
        headlines = news.for_symbol(catalyst.symbol, limit=15) if news else []
        return {"symbol": catalyst.symbol, "news": [h.to_dict() for h in headlines]}

    @router.post("/catalysts", dependencies=guarded)
    def add_catalyst(
        title: str = Body(...), symbol: str = Body(...), event_date: str = Body(...),
        thesis: str = Body(default=""), conviction: str = Body(default="medium"),
        entry_days_before: int = Body(default=45), exit_rule: str = Body(default="before"),
        date_confidence: str = Body(default="estimated"),
    ) -> dict:
        if catalysts is None:
            raise HTTPException(status_code=400, detail="catalysts are not enabled")
        try:
            created = catalysts.add(
                title=title, symbol=symbol, event_date=parse_date(event_date),
                thesis=thesis, conviction=conviction,
                entry_days_before=entry_days_before, exit_rule=exit_rule,
                date_confidence=date_confidence,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return created.to_dict()

    @router.patch("/catalysts/{catalyst_id}", dependencies=guarded)
    def edit_catalyst(catalyst_id: int, status: str | None = Body(default=None, embed=True)) -> dict:
        if catalysts is None:
            raise HTTPException(status_code=400, detail="catalysts are not enabled")
        updated = catalysts.update(catalyst_id, status=status)
        if updated is None:
            raise HTTPException(status_code=404, detail="no such catalyst")
        return updated.to_dict()

    @router.delete("/catalysts/{catalyst_id}", dependencies=guarded)
    def delete_catalyst(catalyst_id: int) -> dict:
        if catalysts is None or not catalysts.remove(catalyst_id):
            raise HTTPException(status_code=404, detail="no such catalyst")
        return {"ok": True}

    @router.get("/setup", dependencies=guarded)
    def setup() -> dict:
        """What is configured and what is still missing to trade real money.

        Reports booleans only — key values never leave the server.
        """
        secrets = settings.secrets if settings else None
        has_alpaca = bool(secrets and secrets.alpaca_api_key and secrets.alpaca_api_secret)
        mode = engine.mode
        stats = repo.trade_stats("paper")

        checks = [
            {
                "id": "alpaca_account",
                "title": "Open an Alpaca brokerage account",
                "body": (
                    "Alpaca accepts Turkish residents — US residency is not required. "
                    "It is commission-free on US stocks and gives you an API, which is "
                    "the piece Midas does not offer."
                ),
                "action": "https://alpaca.markets",
                "action_label": "alpaca.markets",
                "done": has_alpaca,
                "manual": True,
            },
            {
                "id": "keys",
                "title": "Put your API keys in .env",
                "body": (
                    "From the Alpaca dashboard generate an API key pair, then add them to "
                    "the .env file in the project folder. They stay on this machine."
                ),
                "code": "ALPACA_API_KEY=your_key_here\nALPACA_API_SECRET=your_secret_here\nALPACA_PAPER=true",
                "done": has_alpaca,
            },
            {
                "id": "paper_proof",
                "title": "Prove the strategy on paper first",
                "body": (
                    "Run mode: paper for a while and look at the numbers. If it loses money "
                    "on fake money it will lose money on real money — tune the settings in "
                    "config.yaml until the backtest and paper results hold up."
                ),
                "done": stats["total_trades"] >= 20,
                "detail": f"{stats['total_trades']} paper trades so far, "
                          f"{stats['win_rate']}% win rate, {stats['total_pnl']:+.2f} total",
            },
            {
                "id": "live_mode",
                "title": "Switch config.yaml to live",
                "body": (
                    "Set ALPACA_PAPER=false in .env and mode: live in config/config.yaml, "
                    "then restart the bot. This only permits real orders — it does not "
                    "place any yet."
                ),
                "code": "mode: live",
                "done": mode == "live",
            },
            {
                "id": "arm",
                "title": "Arm live trading",
                "body": (
                    "The final switch. The bot starts disarmed on every launch and disarms "
                    "itself if the daily loss limit is hit. Start with a small "
                    "max_position_pct until you trust it."
                ),
                "done": bool(engine.risk.armed and mode == "live"),
            },
        ]

        return {
            "mode": mode,
            "checks": checks,
            "integrations": {
                "alpaca": has_alpaca,
                "telegram": bool(secrets and secrets.telegram_bot_token and secrets.allowed_chat_ids),
                "claude": claude.available,
                "dashboard_token": bool(token),
            },
            "risk": {
                "max_position_pct": engine.config.risk.max_position_pct,
                "stop_loss_pct": engine.config.risk.stop_loss_pct,
                "take_profit_pct": engine.config.risk.take_profit_pct,
                "max_daily_loss_pct": engine.config.risk.max_daily_loss_pct,
                "max_open_positions": engine.config.risk.max_open_positions,
            },
        }

    @router.get("/signals", dependencies=guarded)
    def signals() -> dict:
        executor = engine.executor
        if not isinstance(executor, SignalExecutor):
            return {"pending": [], "recent": [], "enabled": False}
        return {
            "enabled": True,
            "pending": [s.to_dict() for s in executor.pending_signals()],
            "recent": [s.to_dict() for s in executor.recent_signals()],
        }

    # ----------------------------------------------------------------- actions

    @router.post("/signals/{signal_id}/taken", dependencies=guarded)
    def signal_taken(signal_id: str, price: float | None = Body(default=None, embed=True)) -> dict:
        executor = engine.executor
        if not isinstance(executor, SignalExecutor):
            raise HTTPException(status_code=400, detail="not in signal mode")

        pending = {s.id: s for s in executor.pending_signals()}
        signal = pending.get(signal_id)
        if signal is None:
            raise HTTPException(status_code=404, detail="signal not found or already answered")

        fill = price if price is not None else signal.intent.price
        if signal.is_exit:
            position = engine.position_for(signal.intent.symbol)
            executor.confirm_taken(signal_id, fill)
            if position is not None:
                engine.register_confirmed_exit(
                    _build_trade(position, fill, signal.intent.reason)
                )
        else:
            executor.confirm_taken(signal_id, fill)
            engine.register_confirmed_entry(
                signal.intent.symbol,
                Position(
                    symbol=signal.intent.symbol,
                    side=signal.intent.side,
                    qty=signal.intent.qty,
                    entry_price=fill,
                    opened_at=datetime.now(timezone.utc),
                    stop_loss=signal.intent.stop_loss,
                    take_profit=signal.intent.take_profit,
                    current_price=fill,
                ),
                signal.intent.reason,
            )
        return engine.status()

    @router.post("/signals/{signal_id}/skipped", dependencies=guarded)
    def signal_skipped(signal_id: str) -> dict:
        executor = engine.executor
        if not isinstance(executor, SignalExecutor):
            raise HTTPException(status_code=400, detail="not in signal mode")
        if executor.confirm_skipped(signal_id) is None:
            raise HTTPException(status_code=404, detail="signal not found or already answered")
        return engine.status()

    @router.post("/ask", dependencies=guarded)
    def ask(question: str = Body(..., embed=True)) -> dict:
        answer = claude.answer(question, engine.mentor_context())
        if answer is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No AI is connected. Install Ollama (free, no account) or put a "
                    "free GEMINI_API_KEY or GROQ_API_KEY in .env."
                ),
            )
        return {"answer": answer}

    @router.post("/arm", dependencies=guarded)
    def arm(confirm: bool = Body(default=False, embed=True)) -> dict:
        if engine.risk.is_live and not confirm:
            raise HTTPException(status_code=400, detail="live arming requires confirm=true")
        engine.arm()
        return engine.status()

    @router.post("/disarm", dependencies=guarded)
    def disarm() -> dict:
        engine.disarm("manual")
        return engine.status()

    @router.post("/close/{symbol}", dependencies=guarded)
    def close_position(symbol: str) -> dict:
        if not engine.close_position_now(symbol.upper()):
            raise HTTPException(status_code=400, detail="no open position in that symbol")
        return engine.status()

    @router.post("/watchlist/add", dependencies=guarded)
    def add_symbol(symbol: str = Body(..., embed=True)) -> dict:
        if not engine.add_symbol(symbol):
            raise HTTPException(status_code=400, detail="already on the watchlist")
        return engine.status()

    @router.post("/watchlist/remove", dependencies=guarded)
    def remove_symbol(symbol: str = Body(..., embed=True)) -> dict:
        if not engine.remove_symbol(symbol):
            raise HTTPException(
                status_code=400, detail="not on the watchlist, or a position is open"
            )
        return engine.status()

    @router.post("/engine/start", dependencies=guarded)
    def start_engine() -> dict:
        engine.start()
        return engine.status()

    @router.post("/engine/stop", dependencies=guarded)
    def stop_engine() -> dict:
        engine.stop()
        return engine.status()

    @router.post("/engine/scan", dependencies=guarded)
    def scan_now() -> dict:
        engine.scan_now()
        return {"ok": True}

    # --------------------------------------------------------------- websocket

    @router.websocket("/ws")
    async def websocket(socket: WebSocket) -> None:
        if token and not secrets.compare_digest(socket.query_params.get("token", ""), token):
            await socket.close(code=1008)
            return
        await hub.connect(socket)
        try:
            await socket.send_json({"type": "status", **engine.status()})
            while True:
                await socket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception:
            log.debug("websocket closed", exc_info=True)
        finally:
            hub.disconnect(socket)

    return router
