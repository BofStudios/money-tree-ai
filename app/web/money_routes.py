"""Money, keys and the Live feed: the routes behind the desktop's newest screens.

Key values only travel inward. The page can save or delete a key and learn
whether one is set (with its last four characters), never read one back.

Keys and the money mode decide which account real orders go to, so changing
them is refused from other devices unless the dashboard token is set.
"""
from __future__ import annotations

import logging
import secrets as pysecrets
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from app.common.keystore import KeyStore
from app.common.restart import Restarter
from app.config import Settings, set_config_value
from app.engine.markets import MARKETS
from app.engine.portfolio_engine import PortfolioEngine
from app.storage.repository import Repository

log = logging.getLogger(__name__)

# Alpaca's own dashboard. Deposits and withdrawals happen there, under
# "Funds & Wallet" — this app never touches bank details or moves money.
ALPACA_DASHBOARD = "https://app.alpaca.markets/brokerage/dashboard/overview"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def build_money_router(
    engine: PortfolioEngine,
    repo: Repository,
    settings: Settings | None,
    keystore: KeyStore | None,
    restarter: Restarter | None,
    token: str,
    config_path: Path | None = None,
    key_problems: dict[str, str] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    state = {"restart_needed": False}
    # Pairs Alpaca refused when the app started ("paper"/"live" -> "HTTP 401"),
    # so the page can say so instead of showing them as fine.
    problems = dict(key_problems or {})

    def require_token(t: str = Query(default="", alias="token")) -> None:
        if token and not pysecrets.compare_digest(t, token):
            raise HTTPException(status_code=401, detail="invalid token")

    def require_owner(request: Request, t: str = Query(default="", alias="token")) -> None:
        """This PC, or a device holding the dashboard token."""
        if token:
            if pysecrets.compare_digest(t, token):
                return
            raise HTTPException(status_code=401, detail="invalid token")
        host = request.client.host if request.client else ""
        if host not in LOCAL_HOSTS:
            raise HTTPException(
                status_code=403,
                detail="Keys and the money mode can only be changed on the PC running the bot "
                       "(or set DASHBOARD_TOKEN to allow your phone).",
            )

    guarded = [Depends(require_token)]
    owner = [Depends(require_owner)]

    def need(thing, what: str):
        if thing is None:
            raise HTTPException(status_code=503, detail=f"{what} is not available.")
        return thing

    # ---------------------------------------------------------------- live feed

    @router.get("/steps", dependencies=guarded)
    def steps() -> dict:
        return {"steps": engine.monitor.snapshot(), **engine.look_state()}

    # --------------------------------------------------------------------- keys

    @router.get("/keys", dependencies=guarded)
    def keys() -> dict:
        s = need(settings, "Settings")
        stored = keystore.describe() if keystore else {}

        def alpaca(account: str) -> dict:
            problem = problems.get(account)
            key, secret = stored.get(f"alpaca_{account}_key", {}), stored.get(f"alpaca_{account}_secret", {})
            if key.get("set") and secret.get("set"):
                return {"set": True, "tail": key.get("tail"), "source": "app", "problem": problem}
            env_key, env_secret = s.secrets.alpaca_keys(account == "live")
            if env_key and env_secret:
                return {"set": True, "tail": env_key[-4:], "source": "env", "problem": problem}
            return {"set": False, "tail": None, "source": None, "problem": None}

        groq = stored.get("groq_api_key", {})
        if groq.get("set"):
            groq_view = {"set": True, "tail": groq.get("tail"), "source": "app"}
        elif s.secrets.groq_api_key:
            groq_view = {"set": True, "tail": s.secrets.groq_api_key[-4:], "source": "env"}
        else:
            groq_view = {"set": False, "tail": None, "source": None}

        return {
            "alpaca_paper": alpaca("paper"),
            "alpaca_live": alpaca("live"),
            "groq": groq_view,
            "in_use": engine.executor.broker,
            "restart_needed": state["restart_needed"],
            "encrypted": keystore is not None,
        }

    @router.post("/keys/alpaca", dependencies=owner)
    def save_alpaca(
        account: str = Body(..., embed=True),
        key: str = Body(..., embed=True),
        secret: str = Body(..., embed=True),
    ) -> dict:
        s = need(settings, "Settings")
        store = need(keystore, "The key store")
        if account not in ("paper", "live"):
            raise HTTPException(status_code=400, detail="account must be paper or live")
        key, secret = (key or "").strip(), (secret or "").strip()
        if not key or not secret:
            raise HTTPException(status_code=400, detail="Paste both the API key and the secret.")
        live = account == "live"

        # One real call proves the pair before anything is written.
        try:
            summary = _check_alpaca(key, secret, live)
        except PermissionError:
            raise HTTPException(status_code=400, detail=_refusal_hint(key, live)) from None
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Could not reach Alpaca to check the keys: {_short(exc)}"
            ) from exc

        store.set(f"alpaca_{account}_key", key)
        store.set(f"alpaca_{account}_secret", secret)
        setattr(s.secrets, f"alpaca_{account}_key", key)
        setattr(s.secrets, f"alpaca_{account}_secret", secret)
        state["restart_needed"] = True
        problems.pop(account, None)
        log.info("saved Alpaca %s keys ending %s", account, key[-4:])
        return {"ok": True, "account": summary, "restart_needed": True}

    @router.delete("/keys/alpaca/{account}", dependencies=owner)
    def delete_alpaca(account: str) -> dict:
        s = need(settings, "Settings")
        store = need(keystore, "The key store")
        if account not in ("paper", "live"):
            raise HTTPException(status_code=400, detail="account must be paper or live")
        store.delete(f"alpaca_{account}_key")
        store.delete(f"alpaca_{account}_secret")
        setattr(s.secrets, f"alpaca_{account}_key", "")
        setattr(s.secrets, f"alpaca_{account}_secret", "")
        state["restart_needed"] = True
        return {"ok": True, "restart_needed": True}

    # ------------------------------------------------------------- money mode

    @router.post("/mode", dependencies=owner)
    def set_mode(mode: str = Body(..., embed=True), confirm: bool = Body(default=False, embed=True)) -> dict:
        """Practice or real money. Takes effect through a restart.

        Real money still starts disarmed after the restart: arming is always a
        separate, deliberate step.
        """
        s = need(settings, "Settings")
        if mode not in ("signal", "paper", "live"):
            raise HTTPException(status_code=400, detail="mode must be signal, paper or live")
        if mode == "live":
            key, secret = s.secrets.alpaca_keys(True)
            if not (key and secret):
                raise HTTPException(status_code=400, detail="Add your live Alpaca keys first.")
            if not confirm:
                raise HTTPException(status_code=400, detail="Switching to real money needs confirm=true.")
        set_config_value("mode", mode, config_path)
        if restarter is not None:
            restarter.request()
        return {"ok": True, "mode": mode, "restarting": restarter is not None}

    @router.post("/restart", dependencies=owner)
    def restart() -> dict:
        need(restarter, "Restarting").request()
        return {"ok": True, "restarting": True}

    # ------------------------------------------------------------------ money

    @router.get("/money", dependencies=guarded)
    def money() -> dict:
        broker = engine.executor.broker
        error = None
        try:
            account = engine.executor.account_summary().to_dict()
        except Exception as exc:
            account, error = None, _short(exc)

        stats = repo.trade_stats(engine.mode)
        status = engine.status()
        unrealised = round(sum(p.get("unrealized_pnl") or 0.0 for p in status["positions"]), 2)
        realised = round(stats["total_pnl"], 2)
        keys_now = keys() if settings is not None else {}
        return {
            "broker": broker,
            "mode": engine.mode,
            "real": broker == "alpaca_live",
            "account": account,
            "error": error,
            "made": {
                "realised": realised,
                "unrealised": unrealised,
                "total": round(realised + unrealised, 2),
                "trades": stats["total_trades"],
                "win_rate": stats["win_rate"],
            },
            "positions": len(status["positions"]),
            "unmanaged": status["unmanaged"],
            "keys": {
                "paper": bool(keys_now.get("alpaca_paper", {}).get("set")),
                "live": bool(keys_now.get("alpaca_live", {}).get("set")),
            },
            "armed": engine.risk.armed,
            "restart_needed": state["restart_needed"],
            "alpaca_url": ALPACA_DASHBOARD,
        }

    @router.get("/markets", dependencies=guarded)
    def markets() -> dict:
        return {"markets": MARKETS, "watchlist": list(engine.symbols)}

    return router


def _check_alpaca(key: str, secret: str, live: bool) -> dict:
    """The account behind the keys. PermissionError when Alpaca refuses them."""
    from alpaca.trading.client import TradingClient

    try:
        account = TradingClient(key, secret, paper=not live).get_account()
    except Exception as exc:
        try:
            status = getattr(exc, "status_code", None)
        except Exception:
            status = None
        if status in (401, 403):
            raise PermissionError(str(status)) from exc
        raise
    return {
        "status": str(getattr(account.status, "value", account.status)),
        "equity": float(account.equity or 0),
        "cash": float(account.cash or 0),
        "currency": account.currency or "USD",
        "blocked": bool(account.trading_blocked or account.account_blocked),
    }


def _refusal_hint(key: str, live: bool) -> str:
    base = "Alpaca did not accept these keys."
    head = key[:2].upper()
    if live and head == "PK":
        return base + " They look like paper keys (they start with PK) — live keys come from your live account page."
    if not live and head == "AK":
        return base + " They look like live keys (they start with AK) — paper keys come from the paper account page."
    return base + " Copy them again from Alpaca; a secret is only shown once, so you may need to regenerate it."


def _short(exc: BaseException) -> str:
    text = str(exc).strip()
    return (text.splitlines()[0] if text else type(exc).__name__)[:200]
