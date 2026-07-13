"""
Crypto Bot v4.4 — FastAPI Monitoring Server
Exposes health, portfolio, analytics, config, TradingView webhook, and Prometheus metrics.
With HTTP rate limiting (slowapi).
"""

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from prometheus_client import (
    Counter, Gauge, Histogram, generate_latest, REGISTRY,
)
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# Rate Limiter
# ═══════════════════════════════════════════════════════════════

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200/minute"],
    storage_uri="memory://",
)


# ═══════════════════════════════════════════════════════════════
# Prometheus Metrics
# ═══════════════════════════════════════════════════════════════

METRIC_PREFIX = "crypto_bot_v4"

trades_total = Counter(
    f"{METRIC_PREFIX}_trades_total",
    "Total number of trades executed",
    ["pair", "strategy", "direction"],
)
trades_pnl = Histogram(
    f"{METRIC_PREFIX}_trades_pnl",
    "Trade PnL distribution",
    ["pair", "strategy"],
    buckets=[-500, -200, -100, -50, -20, -10, 0, 10, 20, 50, 100, 200, 500, 1000],
)
open_positions = Gauge(
    f"{METRIC_PREFIX}_open_positions", "Number of currently open positions",
)
account_balance = Gauge(
    f"{METRIC_PREFIX}_account_balance", "Total account balance (USDT)",
)
account_equity = Gauge(
    f"{METRIC_PREFIX}_account_equity", "Account equity with unrealized PnL",
)
total_drawdown = Gauge(
    f"{METRIC_PREFIX}_total_drawdown_pct", "Current total drawdown %",
)
daily_pnl = Gauge(
    f"{METRIC_PREFIX}_daily_pnl", "Today's realized PnL",
)
api_latency = Histogram(
    f"{METRIC_PREFIX}_api_latency_seconds",
    "Exchange API call latency",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)
api_errors = Counter(
    f"{METRIC_PREFIX}_api_errors_total", "Total exchange API errors",
    ["endpoint"],
)
health_status = Gauge(
    f"{METRIC_PREFIX}_health_status",
    "System health: 0=healthy, 1=warning, 2=critical",
)
cpu_usage = Gauge(f"{METRIC_PREFIX}_cpu_usage_pct", "CPU usage %")
memory_usage = Gauge(f"{METRIC_PREFIX}_memory_usage_mb", "Memory usage MB")
winrate = Gauge(f"{METRIC_PREFIX}_winrate", "Current winrate", ["strategy"])
profit_factor = Gauge(f"{METRIC_PREFIX}_profit_factor", "Current profit factor")
sharpe_ratio = Gauge(f"{METRIC_PREFIX}_sharpe_ratio", "Current Sharpe ratio")

# TradingView-specific metrics
tv_alerts_total = Counter(
    f"{METRIC_PREFIX}_tv_alerts_total",
    "Total TradingView alerts received",
    ["action", "symbol"],
)
tv_alerts_rejected = Counter(
    f"{METRIC_PREFIX}_tv_alerts_rejected_total",
    "TradingView alerts rejected (duplicate/rate-limited/invalid)",
    ["reason"],
)
tv_signals_created = Counter(
    f"{METRIC_PREFIX}_tv_signals_created_total",
    "Signals created from TradingView alerts",
    ["symbol", "strategy"],
)


def create_app(bot=None) -> FastAPI:
    """Create the FastAPI application with all monitoring routes."""

    app = FastAPI(
        title="Crypto Bot v4.4 — Monitoring API",
        version="4.4.1",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Attach rate limiter to app
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    def _get_bot():
        return bot

    # ═══════════════════════════════════════════════════════════
    # Health
    # ═══════════════════════════════════════════════════════════

    @app.get("/health")
    @limiter.limit("60/minute")
    async def health(request: Request):
        b = _get_bot()
        if b:
            return b.health_monitor.get_status()
        return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

    @app.get("/health/status")
    @limiter.limit("30/minute")
    async def health_status_detail(request: Request):
        b = _get_bot()
        if b:
            status = b.health_monitor.get_status()
            uptime = b.health_monitor.get_uptime_metrics(hours=24)
        else:
            status = {"status": "healthy"}
            uptime = {"availability_pct": 100.0}
        return {"status": status, "uptime_24h": uptime}

    # ═══════════════════════════════════════════════════════════
    # Portfolio
    # ═══════════════════════════════════════════════════════════

    @app.get("/portfolio")
    @limiter.limit("30/minute")
    async def portfolio(request: Request):
        b = _get_bot()
        if b:
            state = b.risk_engine.get_portfolio_state()
            positions = b.portfolio_engine.open_positions
            return {
                "balance": state.balance,
                "equity": state.equity,
                "open_positions_count": state.open_positions,
                "daily_pnl": state.daily_pnl,
                "weekly_pnl": state.weekly_pnl,
                "monthly_pnl": state.monthly_pnl,
                "total_drawdown_pct": state.total_drawdown,
                "recovery_mode": state.recovery_mode,
                "positions": {
                    pair: {
                        "direction": p.direction.value,
                        "entry_price": p.entry_price,
                        "size": p.size,
                        "stop_loss": p.stop_loss,
                        "tp1": p.tp1,
                        "tp2": p.tp2,
                        "current_pnl": p.current_pnl,
                        "strategy": p.strategy,
                    }
                    for pair, p in positions.items()
                },
            }
        return {"balance": 0, "equity": 0, "open_positions_count": 0}

    # ═══════════════════════════════════════════════════════════
    # Analytics
    # ═══════════════════════════════════════════════════════════

    @app.get("/analytics/metrics")
    @limiter.limit("30/minute")
    async def analytics_metrics(request: Request):
        b = _get_bot()
        if b:
            return b.analytics_service.get_metrics()
        return {"total_trades": 0, "winrate": 0}

    @app.get("/analytics/daily")
    @limiter.limit("10/minute")
    async def analytics_daily(request: Request):
        b = _get_bot()
        if b:
            return b.analytics_service.get_daily_report()
        return {"total_trades": 0}

    # ═══════════════════════════════════════════════════════════
    # Learning
    # ═══════════════════════════════════════════════════════════

    @app.get("/learning/status")
    @limiter.limit("20/minute")
    async def learning_status(request: Request):
        b = _get_bot()
        if b:
            ls = b.learning_service
            return {
                "ewma_expected_return": ls.get_expected_return(),
                "strategies": {
                    s: ls.get_strategy_winrate(s)
                    for s in ["sweep", "bounce", "breakout"]
                    if ls.get_strategy_winrate(s)
                },
                "trade_count": ls._trade_count,
            }
        return {"ewma_expected_return": 0, "strategies": {}}

    # ═══════════════════════════════════════════════════════════
    # Config
    # ═══════════════════════════════════════════════════════════

    @app.get("/config/current")
    @limiter.limit("10/minute")
    async def config_current(request: Request):
        b = _get_bot()
        if b:
            cfg = b.config_registry.current_config
            return {
                "version": b.config_registry.current_version,
                "pairs": cfg.pairs if cfg else [],
                "timeframes": cfg.timeframes if cfg else [],
                "mode": b._mode.value,
            }
        return {"version": "unknown"}

    @app.get("/config/versions")
    @limiter.limit("10/minute")
    async def config_versions(request: Request):
        b = _get_bot()
        if b:
            return b.config_registry.get_version_history()
        return []

    # ═══════════════════════════════════════════════════════════
    # Execution
    # ═══════════════════════════════════════════════════════════

    @app.get("/execution/quality")
    @limiter.limit("20/minute")
    async def execution_quality(request: Request):
        b = _get_bot()
        if b:
            return b.execution_engine.get_execution_quality()
        return {"total_executions": 0}

    # ═══════════════════════════════════════════════════════════
    # Prometheus Metrics
    # ═══════════════════════════════════════════════════════════

    @app.get("/metrics")
    @limiter.limit("30/minute")
    async def prometheus_metrics(request: Request):
        b = _get_bot()
        if b:
            state = b.risk_engine.get_portfolio_state()
            health = b.health_monitor.get_status()

            open_positions.set(state.open_positions)
            account_balance.set(state.balance)
            account_equity.set(state.equity)
            total_drawdown.set(state.total_drawdown)
            daily_pnl.set(state.daily_pnl)

            health_map = {"healthy": 0, "warning": 1, "critical": 2}
            health_status.set(health_map.get(health.get("status", "healthy"), 0))
            cpu_usage.set(health.get("cpu_pct", 0))
            memory_usage.set(health.get("memory_mb", 0))

            analytics = b.analytics_service.get_metrics()
            winrate.labels(strategy="all").set(analytics.get("winrate", 0))
            profit_factor.set(analytics.get("profit_factor", 0))
            sharpe_ratio.set(analytics.get("sharpe_ratio", 0))

        return PlainTextResponse(
            generate_latest(REGISTRY),
            media_type="text/plain; version=0.0.4",
        )

    # ═══════════════════════════════════════════════════════════
    # TradingView Webhook Integration
    # ═══════════════════════════════════════════════════════════

    webhook_token = os.getenv("WEBHOOK_TOKEN", "")
    hmac_secret = os.getenv("WEBHOOK_HMAC_SECRET", "")
    if webhook_token:
        logger.info("tv_webhook_security_enabled", token_length=len(webhook_token))

    from api.tradingview_routes import create_tradingview_router
    tv_router = create_tradingview_router(
        bot=_get_bot(),
        webhook_token=webhook_token,
        hmac_secret=hmac_secret,
    )
    app.include_router(tv_router)

    return app


def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Return 429 Too Many Requests with a helpful message."""
    return JSONResponse(
        status_code=429,
        content={
            "status": "rejected",
            "details": f"Rate limit exceeded. Try again in {exc.retry_after} seconds."
            if hasattr(exc, "retry_after") else "Rate limit exceeded.",
        },
    )
