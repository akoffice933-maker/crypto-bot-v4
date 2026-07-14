"""
Crypto Bot v5.0 — FastAPI Server

All endpoints: Health, Portfolio, Analytics, Learning, Config, Execution,
Bot control, Position actions, Risk editing, Logs, WebSocket events,
TradingView webhook, SPA static files, JWT authentication.
"""

import asyncio
import inspect
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import PlainTextResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import (Counter, Gauge, Histogram, generate_latest, REGISTRY)
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog

logger = structlog.get_logger(__name__)

# ═══════════════════════════════════════════
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"], storage_uri="memory://")

JWT_SECRET = os.getenv("JWT_SECRET", "crypto-bot-v5-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
_default_key = os.urandom(32).hex()
API_KEY = os.getenv("API_KEY", _default_key)
if not os.getenv("API_KEY"):
    import sys
    print(f"\n  ╔══════════════════════════════════════════════════════════╗", file=sys.stderr)
    print(f"  ║  WEB PANEL AUTH TOKEN (generated):                     ║", file=sys.stderr)
    print(f"  ║  {_default_key}  ║", file=sys.stderr)
    print(f"  ║  Set API_KEY env var to override.                      ║", file=sys.stderr)
    print(f"  ╚══════════════════════════════════════════════════════════╝\n", file=sys.stderr)
security = HTTPBearer(auto_error=False)


def create_token(username: str) -> str:
    p = {"sub": username, "iat": datetime.now(timezone.utc),
         "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)}
    return jwt.encode(p, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])


async def require_auth(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    if credentials:
        if credentials.credentials == API_KEY:
            return None
        try:
            verify_token(credentials.credentials)
            return None
        except jwt.InvalidTokenError:
            pass
    raise HTTPException(status_code=401, detail="Invalid or missing credentials")


# ═══════════════════════════════════════════
# Prometheus
# ═══════════════════════════════════════════

PREF = "crypto_bot_v5"
trades_total = Counter(f"{PREF}_trades_total", "Trades", ["pair", "strategy", "direction"])
trades_pnl = Histogram(f"{PREF}_trades_pnl", "PnL", ["pair", "strategy"],
                        buckets=[-500, -200, -100, -50, -20, -10, 0, 10, 20, 50, 100, 200, 500, 1000])
open_positions_g = Gauge(f"{PREF}_open_positions", "Open positions")
account_balance = Gauge(f"{PREF}_account_balance", "Balance USDT")
account_equity = Gauge(f"{PREF}_account_equity", "Equity")
total_drawdown_g = Gauge(f"{PREF}_total_drawdown_pct", "Drawdown %")
daily_pnl_g = Gauge(f"{PREF}_daily_pnl", "Daily PnL")
health_status_g = Gauge(f"{PREF}_health_status", "0=healthy,1=warning,2=critical")
cpu_g = Gauge(f"{PREF}_cpu_usage_pct", "CPU %")
mem_g = Gauge(f"{PREF}_memory_usage_mb", "Memory MB")
winrate_g = Gauge(f"{PREF}_winrate", "Winrate", ["strategy"])
pf_g = Gauge(f"{PREF}_profit_factor", "Profit factor")
sharpe_g = Gauge(f"{PREF}_sharpe_ratio", "Sharpe")

# ═══════════════════════════════════════════
# WebSocket Manager
# ═══════════════════════════════════════════

class WSManager:
    def __init__(self):
        self._conns: list[WebSocket] = []
        self._history: list[dict] = []
        self._max_hist = 500

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._conns.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._conns:
            self._conns.remove(ws)

    def broadcast(self, topic: str, data: dict):
        ev = {"topic": topic, "data": data, "timestamp": datetime.now(timezone.utc).isoformat(),
              "event_id": os.urandom(6).hex()}
        self._history.append(ev)
        if len(self._history) > self._max_hist:
            self._history = self._history[-self._max_hist:]
        dead = []
        for ws in self._conns:
            try:
                asyncio.create_task(ws.send_json(ev))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def recent(self, n: int = 50) -> list:
        return self._history[-n:]

ws_mgr = WSManager()

# ═══════════════════════════════════════════
# Log Buffer
# ═══════════════════════════════════════════

_log_buffer: list[dict] = []


def capture_log(level: str, msg: str, service: str = "core"):
    _log_buffer.append({"ts": datetime.now(timezone.utc).isoformat(),
                        "level": level.upper(), "service": service, "message": msg})
    if len(_log_buffer) > 2000:
        del _log_buffer[:500]


# ═══════════════════════════════════════════
# App Factory
# ═══════════════════════════════════════════

def create_app(bot=None) -> FastAPI:
    app = FastAPI(title="Crypto Bot v5.0", version="5.0.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    def _bot():
        return bot

    _start_lock = asyncio.Lock()
    _start_task = None

    async def _read_body(request: Request) -> dict:
        try:
            return await request.json()
        except Exception:
            return {}

    # ── Auth ───────────────────────────────────

    @app.post("/api/auth/login")
    @limiter.limit("10/minute")
    async def login(request: Request):
        body = await _read_body(request)
        if body.get("username") == os.getenv("ADMIN_USER", "admin") and \
           body.get("password") == os.getenv("ADMIN_PASS", "admin"):
            return {"token": create_token(body["username"]), "expires_in": JWT_EXPIRE_HOURS * 3600}
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # ── Health ─────────────────────────────────

    @app.get("/health")
    @limiter.limit("60/minute")
    async def health(request: Request):
        b = _bot()
        return b.health_monitor.get_status() if b else {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/health/status")
    @limiter.limit("30/minute")
    async def health_detail(request: Request):
        b = _bot()
        s = b.health_monitor.get_status() if b else {"status": "healthy"}
        u = b.health_monitor.get_uptime_metrics(hours=24) if b else {"availability_pct": 100.0}
        return {"status": s, "uptime_24h": u}

    # ── Portfolio ──────────────────────────────

    @app.get("/portfolio")
    @limiter.limit("30/minute")
    async def portfolio(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            return {"balance": 0, "equity": 0, "open_positions_count": 0, "positions": {}}
        state = b.risk_engine.get_portfolio_state()
        positions = b.portfolio_engine.open_positions
        return {"balance": state.balance, "equity": state.equity,
                "open_positions_count": state.open_positions,
                "daily_pnl": state.daily_pnl, "weekly_pnl": state.weekly_pnl,
                "monthly_pnl": state.monthly_pnl,
                "total_drawdown_pct": state.total_drawdown,
                "recovery_mode": state.recovery_mode,
                "positions": {pair: {"direction": p.direction.value, "entry_price": p.entry_price,
                                     "size": p.size, "stop_loss": p.stop_loss,
                                     "tp1": p.tp1, "tp2": p.tp2,
                                     "current_pnl": p.current_pnl, "strategy": p.strategy}
                              for pair, p in positions.items()}}

    # ── Positions (write) ──────────────────────

    @app.post("/api/positions/{pair}/close")
    @limiter.limit("30/minute")
    async def close_position(pair: str, request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            raise HTTPException(status_code=503, detail="Bot not running")
        pos = b.portfolio_engine.get_position(pair)
        if not pos:
            raise HTTPException(status_code=404, detail="Position not found")

        body = await _read_body(request)
        exit_price_user = float(body.get("exit_price", 0) or 0)

        # ── Real market close on the exchange ───────────
        actual_price = exit_price_user
        realized_pnl = 0.0
        try:
            from core.models import Signal, Direction as Dir, StrategyType, RiskDecision
            from services.execution_engine.orders.market import MarketOrderExecutor

            ccxt_symbol = b.exchange_adapter.normalize_symbol(pair, b.exchange_adapter.exchange_id)
            side = "sell" if pos.direction == Dir.LONG else "buy"

            signal = Signal(pair=pair, direction=pos.direction, entry_market=pos.entry_price,
                           entry_limit=pos.entry_price, stop_loss=0, tp1=0, tp2=0,
                           strategy=StrategyType.SWEEP, confidence=1.0, regime="ui_close")
            rd = RiskDecision(approved=True, position_size=pos.size, stop_loss=pos.stop_loss)

            executor = MarketOrderExecutor(b.exchange_adapter)
            record = await executor.place(signal, rd, ccxt_symbol, side)

            if record and record.actual_price > 0:
                actual_price = record.actual_price
            elif not record:
                raise Exception("Exchange returned no record")

            realized_pnl = ((actual_price - pos.entry_price) * pos.size
                           if pos.direction == Dir.LONG else
                           (pos.entry_price - actual_price) * pos.size)
        except Exception as e:
            logger.error("close_position_exchange_failed", pair=pair, error=str(e))
            raise HTTPException(status_code=502, detail=f"Exchange close failed: {str(e)}")

        # ── Update internal state ──────────────────────
        b.portfolio_engine.close_position(pair, actual_price, realized_pnl)
        b.analytics_service.add_trade({
            "entry_price": pos.entry_price, "exit_price": actual_price,
            "size": pos.size, "pnl": realized_pnl, "fees": 0,
            "is_win": realized_pnl > 0, "timestamp": datetime.now(timezone.utc),
            "strategy": pos.strategy, "pair": pair,
        })
        b.learning_service.record_trade(pos.strategy, realized_pnl > 0, 0)
        b.risk_engine.record_trade_result(realized_pnl, realized_pnl > 0)
        b.risk_engine.update_balance(b.risk_engine.balance + realized_pnl)

        ws_mgr.broadcast("position.closed", {"pair": pair, "exit_price": actual_price, "pnl": realized_pnl})
        capture_log("INFO", f"Position closed via UI: {pair} @ {actual_price}, PnL=${realized_pnl:.2f}", service="api")
        return {"status": "ok", "pair": pair, "closed": True, "exit_price": actual_price, "pnl": realized_pnl}

    @app.put("/api/positions/{pair}/stop-loss")
    @limiter.limit("30/minute")
    async def move_stop_loss(pair: str, request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            raise HTTPException(status_code=503, detail="Bot not running")
        body = await _read_body(request)
        new_sl = float(body.get("stop_loss", 0))
        if new_sl <= 0:
            raise HTTPException(status_code=400, detail="Invalid stop_loss")

        pos = b.portfolio_engine.get_position(pair)
        if not pos:
            raise HTTPException(status_code=404, detail="Position not found")

        # ── Real stop replacement on exchange ───────────
        try:
            pos.stop_loss = new_sl  # Temporarily update for the order call
            await b.execution_engine.place_stop_loss(pos)
        except Exception as e:
            logger.error("move_stop_loss_exchange_failed", pair=pair, error=str(e))
            raise HTTPException(status_code=502, detail=f"Exchange stop update failed: {str(e)}")

        b.portfolio_engine.update_stop_loss(pair, new_sl)
        ws_mgr.broadcast("position.stop_moved", {"pair": pair, "new_stop": new_sl})
        capture_log("INFO", f"Stop-loss updated via UI: {pair} -> ${new_sl}", service="api")
        return {"status": "ok", "pair": pair, "stop_loss": new_sl}

    # ── Analytics ──────────────────────────────

    @app.get("/analytics/metrics")
    @limiter.limit("30/minute")
    async def analytics_metrics(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        return b.analytics_service.get_metrics() if b else {"total_trades": 0, "winrate": 0}

    @app.get("/analytics/daily")
    @limiter.limit("10/minute")
    async def analytics_daily(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        return b.analytics_service.get_daily_report() if b else {"total_trades": 0}

    # ── Learning ───────────────────────────────

    @app.get("/learning/status")
    @limiter.limit("20/minute")
    async def learning_status(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            return {"ewma_expected_return": 0, "strategies": {}, "trade_count": 0}
        ls = b.learning_service
        return {"ewma_expected_return": ls.get_expected_return(),
                "strategies": {s: ls.get_strategy_winrate(s)
                               for s in ["sweep", "bounce", "breakout"]
                               if ls.get_strategy_winrate(s)},
                "trade_count": ls._trade_count}

    # ── Config ─────────────────────────────────

    @app.get("/config/current")
    @limiter.limit("10/minute")
    async def config_current(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if b:
            c = b.config_registry.current_config
            return {"version": b.config_registry.current_version,
                    "pairs": c.pairs if c else [],
                    "timeframes": c.timeframes if c else [],
                    "mode": b._mode.value}
        return {"version": "unknown"}

    @app.get("/config/versions")
    @limiter.limit("10/minute")
    async def config_versions(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        return b.config_registry.get_version_history() if b else []

    @app.post("/api/config/reload")
    @limiter.limit("5/minute")
    async def config_reload(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            raise HTTPException(status_code=503, detail="Bot not running")
        try:
            b.config = b.config_registry.load()
            ws_mgr.broadcast("config.updated", {"version": b.config_registry.current_version})
            return {"status": "ok", "version": b.config_registry.current_version}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ── Execution ──────────────────────────────

    @app.get("/execution/quality")
    @limiter.limit("20/minute")
    async def execution_quality(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        return b.execution_engine.get_execution_quality() if b else {"total_executions": 0}

    # ── Risk ───────────────────────────────────

    @app.get("/api/risk")
    @limiter.limit("20/minute")
    async def get_risk(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            return {"max_risk_per_trade": 0.015, "max_positions": 3}
        re = b.risk_engine
        return {"max_risk_per_trade": re._get_risk_per_trade(),
                "max_positions": 3, "max_correlation": 0.7, "max_exposure": 3.0,
                "stop_multipliers": re.stop_multiplier,
                "drawdown_limits": re.drawdown_limits,
                "recovery_threshold": re.RECOVERY_THRESHOLD,
                "recovery_exit_threshold": re.RECOVERY_EXIT,
                "recovery_min_wins": re.RECOVERY_MIN_WINS,
                "recovery_mode": re._recovery_mode,
                "recovery_consecutive_wins": re._consecutive_wins}

    @app.put("/api/risk/limits")
    @limiter.limit("10/minute")
    async def update_risk_limits(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            raise HTTPException(status_code=503, detail="Bot not running")
        body = await _read_body(request)
        re = b.risk_engine
        if "stop_multipliers" in body:
            re.stop_multiplier.update(body["stop_multipliers"])
        if "drawdown_limits" in body:
            re.drawdown_limits.update(body["drawdown_limits"])
        ws_mgr.broadcast("risk.updated", {"limits": body})
        capture_log("INFO", "Risk limits updated via UI", service="api")
        return {"status": "ok", "limits": re.drawdown_limits}

    @app.post("/api/risk/recovery/exit")
    @limiter.limit("5/minute")
    async def exit_recovery(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            raise HTTPException(status_code=503, detail="Bot not running")
        re = b.risk_engine
        if re._recovery_mode:
            re._exit_recovery()
            ws_mgr.broadcast("recovery.exited", {"balance": re.balance})
            capture_log("WARNING", "Recovery mode exited via UI", service="api")
            return {"status": "ok", "recovery": False}
        return {"status": "ok", "recovery": False, "message": "Not in recovery"}

    # ── Bot Control ────────────────────────────

    @app.get("/api/bot/status")
    @limiter.limit("30/minute")
    async def bot_status(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        return {"running": b._running if b else False,
                "mode": b._mode.value if b else "stopped",
                "version": b.config.version if b else "5.1.0",
                "uptime_seconds": 0,
                "websocket": b.ws_manager.is_connected if b else False}

    @app.post("/api/bot/start")
    @limiter.limit("5/minute")
    async def bot_start(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            raise HTTPException(status_code=503, detail="Bot instance not available")

        async with _start_lock:
            if b._running:
                return {"status": "ok", "running": True, "message": "Already running"}

            if _start_task and not _start_task.done():
                _start_task.cancel()
                try:
                    await _start_task
                except asyncio.CancelledError:
                    pass

            b._running = True
            _start_task = asyncio.create_task(b.run())
            ws_mgr.broadcast("bot.started", {"mode": b._mode.value})
            capture_log("INFO", "Bot started via UI", service="api")
            return {"status": "ok", "running": True}

    @app.post("/api/bot/stop")
    @limiter.limit("5/minute")
    async def bot_stop(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            raise HTTPException(status_code=503, detail="Bot instance not available")
        b._running = False
        ws_mgr.broadcast("bot.stopped", {})
        capture_log("WARNING", "Bot stopped via UI", service="api")
        return {"status": "ok", "running": False}

    @app.post("/api/bot/restart")
    @limiter.limit("3/minute")
    async def bot_restart(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        if not b:
            raise HTTPException(status_code=503, detail="Bot instance not available")

        async with _start_lock:
            b._running = False
            if _start_task and not _start_task.done():
                _start_task.cancel()
                try:
                    await _start_task
                except asyncio.CancelledError:
                    pass
            await asyncio.sleep(1)
            b._running = True
            _start_task = asyncio.create_task(b.run())
            ws_mgr.broadcast("bot.restarted", {})
            return {"status": "ok", "running": True}

    # ── Logs API ───────────────────────────────

    @app.get("/api/logs")
    @limiter.limit("30/minute")
    async def get_logs(request: Request, n: int = 200, level: str = "ALL"):
        logs = list(_log_buffer[-n:])
        if level != "ALL":
            logs = [l for l in logs if l["level"] == level.upper()]
        return {"logs": list(reversed(logs)), "total": len(_log_buffer)}

    # ── WebSocket /ws/events ───────────────────

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket):
        await ws_mgr.connect(ws)
        for ev in ws_mgr.recent(50):
            try:
                await ws.send_json(ev)
            except Exception:
                break
        try:
            while True:
                await ws.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            ws_mgr.disconnect(ws)

    # ── Strategies ─────────────────────────────

    @app.get("/api/strategies")
    @limiter.limit("20/minute")
    async def get_strategies(request: Request, _auth=Depends(require_auth)):
        b = _bot()
        strategies = [
            {"name": "sweep", "enabled": True, "wick_ratio": 1.8, "volume_multiplier": 1.25,
             "tolerance": 0.0018, "min_rr": 2.0},
            {"name": "bounce", "enabled": True, "wick_ratio": 1.5, "volume_multiplier": 1.10,
             "tolerance": 0.0018, "min_rr": 1.5},
            {"name": "breakout", "enabled": True, "sl_atr_mult": 1.5, "tp_min": 0.02, "tp_max": 0.04},
        ]
        if b:
            for s in strategies:
                wr = b.learning_service.get_strategy_winrate(s["name"])
                if wr:
                    s["winrate"] = wr["expected_winrate"]
        return {"strategies": strategies}

    # ── Settings ───────────────────────────────

    @app.get("/api/settings")
    @limiter.limit("10/minute")
    async def get_settings(request: Request, _auth=Depends(require_auth)):
        return {"exchange_id": os.getenv("EXCHANGE_ID", "binance"),
                "testnet": os.getenv("BINANCE_TESTNET", "true") == "true",
                "api_key_configured": bool(os.getenv("BINANCE_API_KEY", "")),
                "notifications": {"telegram": False, "email": False, "webhook": False}}

    # ── Metrics ────────────────────────────────

    @app.get("/metrics")
    @limiter.limit("30/minute")
    async def prometheus_metrics(request: Request):
        b = _bot()
        if b:
            s = b.risk_engine.get_portfolio_state()
            h = b.health_monitor.get_status()
            open_positions_g.set(s.open_positions)
            account_balance.set(s.balance); account_equity.set(s.equity)
            total_drawdown_g.set(s.total_drawdown); daily_pnl_g.set(s.daily_pnl)
            hm = {"healthy": 0, "warning": 1, "critical": 2}
            health_status_g.set(hm.get(h.get("status", "healthy"), 0))
            cpu_g.set(h.get("cpu_pct", 0)); mem_g.set(h.get("memory_mb", 0))
            a = b.analytics_service.get_metrics()
            winrate_g.labels(strategy="all").set(a.get("winrate", 0))
            pf_g.set(a.get("profit_factor", 0))
            sharpe_g.set(a.get("sharpe_ratio", 0))
        return PlainTextResponse(generate_latest(REGISTRY), media_type="text/plain; version=0.0.4")

    # ── TradingView ────────────────────────────

    from api.tradingview_routes import create_tradingview_router
    app.include_router(create_tradingview_router(
        bot=_bot, webhook_token=os.getenv("WEBHOOK_TOKEN", ""),
        hmac_secret=os.getenv("WEBHOOK_HMAC_SECRET", "")))

    # ── SPA ────────────────────────────────────

    web_dir = os.path.join(os.path.dirname(__file__), "..", "web", "dist")
    if os.path.isdir(web_dir):
        from fastapi.staticfiles import StaticFiles
        from starlette.responses import FileResponse
        app.mount("/assets", StaticFiles(directory=os.path.join(web_dir, "assets")), name="web_assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            ix = os.path.join(web_dir, "index.html")
            if os.path.isfile(ix) and not full_path.startswith(("api/", "ws/", "docs", "redoc", "openapi.json")):
                return FileResponse(ix)
            raise HTTPException(status_code=404)

    return app


def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"status": "rejected",
        "details": f"Rate limit exceeded. Retry in {exc.retry_after}s." if hasattr(exc, 'retry_after') else "Rate limit exceeded."})
