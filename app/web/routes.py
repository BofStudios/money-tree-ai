from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect

from app.catalysts.manager import CatalystManager, parse_date
from app.catalysts.news import NewsFeed
from app.common.models import Position
from app.config import Settings, write_secret
from app.engine.portfolio_engine import PortfolioEngine
from app.engine import commands
from app.mentor.ai import AIMentor
from app.engine.autonomy import HORIZON_TIMEFRAMES, resolve_autonomy
from app.engine.markets import watchlist_for
from app.mentor.providers import BUILDERS
from app.mentor.narrator import Narrator
from app.research.analyst import Analyst, build_plan
from app.research.service import DEPTHS as RESEARCH_DEPTHS
from app.research.service import ResearchService
from app.research.user_profile import CHOICES as PROFILE_CHOICES
from app.research.user_profile import ProfileStore
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
    research: ResearchService | None = None,
    analyst: Analyst | None = None,
    profiles: ProfileStore | None = None,
    keystore=None,
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

    @router.post("/mentor/setup", dependencies=guarded)
    def mentor_setup(
        mode: str = Body(..., embed=True),
        provider: str = Body(default="groq", embed=True),
        api_key: str = Body(default="", embed=True),
    ) -> dict:
        """Connect an AI provider from Settings, live — no restart.

        Two paths, mirroring the two buttons in the UI: reuse a Groq key
        already on file, or take a freshly pasted key for any of the three
        hosted providers and write it into .env before switching to it.
        """
        if settings is None:
            raise HTTPException(status_code=503, detail="Settings are not available.")

        if mode == "groq_free":
            provider = "groq"
            key = settings.secrets.groq_api_key
            if not key:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No free Groq key on file yet. Get one free at "
                        "console.groq.com/keys, then use Enter manually."
                    ),
                )
        elif mode == "manual":
            provider = (provider or "").strip().lower()
            if provider not in ("groq", "gemini", "anthropic"):
                raise HTTPException(status_code=400, detail="Unknown provider.")
            key = (api_key or "").strip()
            if not key:
                raise HTTPException(status_code=400, detail="Paste an API key first.")

            # Prove the key actually works with one real call before writing
            # anything to disk — .available() only checks the key is non-empty,
            # so a typo'd key would otherwise be saved and reported as success.
            candidate = BUILDERS[provider]({provider: key}, "")
            # Some free-tier models (Groq's gpt-oss line) spend part of the
            # budget on hidden reasoning before the visible reply, so this
            # needs real headroom — a tight budget here reads as a bad key.
            probe = candidate.chat(
                "Reply with one word.", [{"role": "user", "content": "Say OK."}], 80
            )
            if probe is None:
                raise HTTPException(
                    status_code=400,
                    detail="That key was rejected by the provider. Double-check it and try again.",
                )

            if keystore is not None:
                keystore.set(f"{provider}_api_key", key)   # encrypted on this PC
            else:
                write_secret(f"{provider.upper()}_API_KEY", key)
            setattr(settings.secrets, f"{provider}_api_key", key)
        else:
            raise HTTPException(status_code=400, detail="mode must be groq_free or manual")

        settings.app.mentor.provider = provider
        ok = claude.reload(provider, settings.secrets.mentor_keys, settings.app.mentor.model)
        if not ok:
            raise HTTPException(
                status_code=502,
                detail="Saved the key, but could not reach the model. Double-check it is correct.",
            )
        return {"ai": claude.backend}

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
        has_paper = bool(secrets and all(secrets.alpaca_keys(False)))
        has_live = bool(secrets and all(secrets.alpaca_keys(True)))
        has_alpaca = has_paper or has_live
        mode = engine.mode
        broker = engine.executor.broker
        stats = repo.trade_stats("paper")

        checks = [
            {
                "id": "alpaca_account",
                "title": "Open an Alpaca brokerage account",
                "body": (
                    "Alpaca accepts Turkish residents — US residency is not required. "
                    "It is commission-free on US stocks and gives you an API. "
                    "The bot trades only through Alpaca."
                ),
                "action": "https://alpaca.markets",
                "action_label": "alpaca.markets",
                "done": has_alpaca,
                "manual": True,
            },
            {
                "id": "keys",
                "title": "Paste your API keys in Settings",
                "body": (
                    "In Alpaca, open API Keys and generate a pair, then paste the key and "
                    "the secret into Settings → Money in this app. They are checked with "
                    "Alpaca first and stored encrypted on this PC; the page never shows "
                    "them again."
                ),
                "done": has_alpaca,
            },
            {
                "id": "paper_proof",
                "title": "Prove the strategy on practice money first",
                "body": (
                    "Run on practice money for a while and look at the numbers. If it loses "
                    "money on fake money it will lose money on real money."
                ),
                "done": stats["total_trades"] >= 20,
                "detail": f"{stats['total_trades']} practice trades so far, "
                          f"{stats['win_rate']}% win rate, {stats['total_pnl']:+.2f} total",
            },
            {
                "id": "live_mode",
                "title": "Switch to real money",
                "body": (
                    "Add your live keys, then choose Real money in Settings → Money. The app "
                    "restarts on your live account. This only permits real orders — it does "
                    "not place any yet."
                ),
                "done": broker == "alpaca_live",
            },
            {
                "id": "arm",
                "title": "Arm live trading",
                "body": (
                    "The final switch. The bot starts disarmed on every launch and disarms "
                    "itself if the daily loss limit is hit."
                ),
                "done": bool(engine.risk.armed and broker == "alpaca_live"),
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

    # ----------------------------------------------------------------- actions

    @router.post("/ask", dependencies=guarded)
    def ask(question: str = Body(..., embed=True)) -> dict:
        # Stop and Start never go to the AI: they are done here, at once.
        command = commands.command(question)
        w = engine.words()
        if command == "stop":
            engine.halt("chat")
            return {"answer": w.chat_stopped(), "action": "halted"}
        if command == "start":
            engine.resume("chat")
            return {"answer": w.chat_started(), "action": "resumed"}
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
        problem = engine.why_not_close(symbol.upper())
        if problem:
            raise HTTPException(status_code=409, detail=problem)
        if not engine.close_position_now(symbol.upper()):
            raise HTTPException(status_code=409, detail="The position could not be closed.")
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
        engine.resume("button")
        return engine.status()

    @router.post("/engine/stop", dependencies=guarded)
    def stop_engine() -> dict:
        engine.halt("button")
        return engine.status()

    @router.post("/engine/scan", dependencies=guarded)
    def scan_now() -> dict:
        engine.scan_now()
        return {"ok": True}

    # -------------------------------------------------------------------- news

    @router.get("/news", dependencies=guarded)
    def market_news(limit: int = Query(default=30, ge=1, le=60)) -> dict:
        """Headlines across everything being watched — the watchlist, whatever
        is held, and any catalyst symbols. One feed rather than three."""
        symbols: list[str] = []
        for symbol in engine.config.watchlist:
            if symbol not in symbols:
                symbols.append(symbol)
        if catalysts is not None:
            for symbol in catalysts.symbols():
                if symbol not in symbols:
                    symbols.append(symbol)

        if news is None or not symbols:
            return {"available": False, "symbols": symbols, "news": []}

        try:
            headlines = news.for_symbols(symbols, limit=limit)
        except Exception:
            log.debug("news feed unavailable", exc_info=True)
            return {"available": False, "symbols": symbols, "news": []}

        return {
            "available": bool(news.available),
            "symbols": symbols,
            "news": [h.to_dict() if hasattr(h, "to_dict") else h for h in headlines],
        }

    # ---------------------------------------------------------------- research

    def _need_research() -> None:
        if research is None:
            raise HTTPException(status_code=503, detail="Company research is not configured.")

    @router.get("/research/search", dependencies=guarded)
    def research_search(q: str = Query(default=""), limit: int = Query(default=8, ge=1, le=25)) -> dict:
        _need_research()
        return {"query": q, "results": research.search(q, limit)}

    @router.get("/research/{symbol}", dependencies=guarded)
    def research_company(symbol: str, depth: str = Query(default="standard")) -> dict:
        _need_research()
        if depth not in RESEARCH_DEPTHS:
            raise HTTPException(status_code=400, detail=f"depth must be one of {RESEARCH_DEPTHS}")

        view = research.company(symbol, depth)
        if view.get("profile") is None and view.get("price") is None:
            raise HTTPException(status_code=404, detail=f"No data for {symbol.upper()}.")

        headlines = _headlines_for(symbol)
        plan = build_plan(view, profiles.get().attention if profiles else [])
        return {
            **view,
            "news": headlines,
            "plan": plan.to_dict(),
            "ai_available": bool(analyst and analyst.available),
        }

    @router.post("/research/{symbol}/analyse", dependencies=guarded)
    def research_analyse(
        symbol: str,
        depth: str = Body(default="standard", embed=True),
        attention: list[str] = Body(default=[], embed=True),
        question: str | None = Body(default=None, embed=True),
    ) -> dict:
        _need_research()
        if analyst is None or not analyst.available:
            raise HTTPException(
                status_code=503,
                detail=(
                    "No AI is connected. Install Ollama (free, no account) or put a "
                    "free GEMINI_API_KEY or GROQ_API_KEY in .env."
                ),
            )
        if depth not in RESEARCH_DEPTHS:
            raise HTTPException(status_code=400, detail=f"depth must be one of {RESEARCH_DEPTHS}")

        view = research.company(symbol, depth)
        if view.get("profile") is None and view.get("price") is None:
            raise HTTPException(status_code=404, detail=f"No data for {symbol.upper()}.")

        plan = build_plan(view, attention)
        note = analyst.analyse(
            view,
            plan,
            profile_prompt=profiles.get().as_prompt() if profiles else "",
            headlines=_headlines_for(symbol),
            question=question,
        )
        if note is None:
            raise HTTPException(status_code=502, detail="The model did not return an analysis.")
        return {"symbol": symbol.upper(), "depth": depth, "plan": plan.to_dict(), "note": note}

    @router.post("/research/{symbol}/ask", dependencies=guarded)
    def research_ask(symbol: str, question: str = Body(..., embed=True)) -> dict:
        _need_research()
        if analyst is None or not analyst.available:
            raise HTTPException(status_code=503, detail="No AI is connected.")

        view = research.company(symbol, "standard")
        answer = analyst.ask(
            view,
            question,
            profile_prompt=profiles.get().as_prompt() if profiles else "",
            headlines=_headlines_for(symbol),
        )
        if answer is None:
            raise HTTPException(status_code=502, detail="The model did not return an answer.")
        return {"symbol": symbol.upper(), "answer": answer}

    def _headlines_for(symbol: str) -> list[dict]:
        """News for one symbol, or an empty list when no feed is configured."""
        if news is None:
            return []
        try:
            return [h.to_dict() if hasattr(h, "to_dict") else h
                    for h in news.for_symbols([symbol.upper()], limit=10)]
        except Exception:
            log.debug("no headlines for %s", symbol, exc_info=True)
            return []

    # ----------------------------------------------------------------- profile

    @router.get("/profile", dependencies=guarded)
    def get_profile() -> dict:
        if profiles is None:
            raise HTTPException(status_code=503, detail="Profiles are not configured.")
        return {"profile": profiles.get().to_dict(), "choices": PROFILE_CHOICES}

    @router.patch("/profile", dependencies=guarded)
    def patch_profile(changes: dict = Body(...)) -> dict:
        if profiles is None:
            raise HTTPException(status_code=503, detail="Profiles are not configured.")
        profile = profiles.update(changes)
        # Two of the answers are live controls on the bot, not just preferences.
        if "autonomy" in changes:
            engine.set_autonomy(resolve_autonomy(profile.autonomy, engine.mode))
        if "trading_horizon" in changes and profile.trading_horizon in HORIZON_TIMEFRAMES:
            engine.set_horizon(profile.trading_horizon)
        if "market" in changes:
            symbols = watchlist_for(profile.market)
            if symbols:
                engine.set_watchlist(symbols)
        if "small_account" in changes:
            engine.set_small_account(profile.small_account)
        if "language" in changes:
            engine.set_language(profile.language)
        return {"profile": profile.to_dict(), "autonomy": engine.autonomy,
                "timeframe": engine.timeframe, "watchlist": list(engine.symbols)}

    # --------------------------------------------------------------- approvals

    @router.post("/proposals/{proposal_id}/approve", dependencies=guarded)
    def approve_proposal(proposal_id: str) -> dict:
        result = engine.approve(proposal_id)
        if not result["ok"]:
            raise HTTPException(status_code=409, detail=result["message"])
        return result

    @router.post("/proposals/{proposal_id}/skip", dependencies=guarded)
    def skip_proposal(proposal_id: str) -> dict:
        if not engine.skip_proposal(proposal_id):
            raise HTTPException(status_code=404, detail="That request is no longer open.")
        return {"ok": True}

    # ------------------------------------------------------------- performance

    @router.get("/performance", dependencies=guarded)
    def performance() -> dict:
        """What the bot has made or lost for the owner, in one honest number.

        Realised is closed trades. Unrealised is what the open positions are
        worth right now relative to what was paid — it can still change.
        """
        stats = repo.trade_stats(engine.mode)
        status = engine.status()
        unrealised = round(sum(p.get("unrealized_pnl") or 0.0 for p in status["positions"]), 2)
        realised = stats["total_pnl"]
        start = (
            engine.config.risk.starting_paper_balance if engine.mode == "paper" else None
        )
        return {
            "mode": engine.mode,
            "practice": engine.mode != "live",
            "equity": status["equity"],
            "starting_balance": start,
            "realised": realised,
            "unrealised": unrealised,
            "total": round(realised + unrealised, 2),
            "trades": stats["total_trades"],
            "wins": stats["wins"],
            "losses": stats["losses"],
            "win_rate": stats["win_rate"],
            "best_trade": stats["best_trade"],
            "worst_trade": stats["worst_trade"],
        }

    @router.post("/profile/reset", dependencies=guarded)
    def reset_profile() -> dict:
        if profiles is None:
            raise HTTPException(status_code=503, detail="Profiles are not configured.")
        return {"profile": profiles.reset().to_dict()}

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
