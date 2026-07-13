"""
Crypto Bot v4.4 — TradingView Webhook Routes (FastAPI)

Endpoints:
  POST /webhook/tradingview     — main TradingView webhook receiver
  POST /webhook/tradingview/v2  — extended webhook with indicator payloads
  GET  /webhook/indicators      — list supported indicators with PineScript templates
  GET  /webhook/social          — social/sentiment signals for an asset
  GET  /webhook/alerts/recent   — recent alert history
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel

import structlog

from services.tradingview_service import (
    AlertParser, AlertToSignalConverter, AlertManager,
    WebhookSecurity, AlertAction,
)
from services.tradingview_service.indicators.registry import IndicatorRegistry
from services.tradingview_service.social.registry import SocialSignalRegistry

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# Pydantic models for API documentation
# ═══════════════════════════════════════════════════════════════

class TradingViewAlertV2(BaseModel):
    """Extended TradingView alert with full indicator payload."""
    action: str = ""               # BUY | SELL | CLOSE | LONG | SHORT
    symbol: str = ""               # BTCUSDT
    exchange: str = "binance"
    price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    take_profit_2: float = 0.0
    quantity: float = 0.0
    leverage: int = 1
    confidence: float = 0.8
    strategy: str = ""
    timeframe: str = ""
    indicator: str = ""
    indicator_value: float = 0.0
    indicator_params: dict = {}
    token: str = ""
    alert_id: str = ""
    message: str = ""


class WebhookResponse(BaseModel):
    """Standard webhook response."""
    status: str = "ok"             # ok | rejected | error
    action: str = ""
    signal_created: bool = False
    alert_id: str = ""
    details: str = ""


class IndicatorListResponse(BaseModel):
    indicators: list
    count: int


class SocialSignalResponse(BaseModel):
    pair: str
    asset: str
    signals: dict


# ═══════════════════════════════════════════════════════════════
# Router factory
# ═══════════════════════════════════════════════════════════════

def create_tradingview_router(
    bot=None,
    webhook_token: str = "",
    hmac_secret: str = "",
) -> APIRouter:
    """
    Create the TradingView webhook FastAPI router.

    Args:
        bot: CryptoBot instance (optional, for live trading integration)
        webhook_token: Security token for webhook authentication
        hmac_secret: HMAC secret for signature verification
    """
    router = APIRouter(prefix="/webhook", tags=["TradingView"])

    # Initialize components
    security = WebhookSecurity(webhook_token=webhook_token, hmac_secret=hmac_secret)
    alert_manager = AlertManager()
    indicator_registry = IndicatorRegistry()
    social_registry = SocialSignalRegistry()
    converter = AlertToSignalConverter(indicator_registry=indicator_registry)

    # ═══════════════════════════════════════════════════════════
    # POST /webhook/tradingview — main TradingView webhook
    # ═══════════════════════════════════════════════════════════

    @router.post("/tradingview", response_model=WebhookResponse)
    async def tradingview_webhook(request: Request):
        """
        Receive TradingView alert webhook.

        Compatible formats:
          - JSON: {"action": "BUY", "symbol": "BTCUSDT", ...}
          - OctoBot: SIGNAL=BUY SYMBOL=BTCUSDT EXCHANGE=binance
          - Plain text: BUY BTCUSDT sl=64500 tp=66000
          - PineConnector: {"action": "BUY", "symbol": "BTCUSDT", ...}

        Headers:
          - x-webhook-token: security token (optional but recommended)
          - x-tv-token: alternative token header
          - x-signature: HMAC-SHA256 signature (optional)
        """
        try:
            raw_body = await request.body()
            headers = dict(request.headers)

            # Parse alert
            alert = AlertParser.parse(raw_body, headers)

            if alert.action == AlertAction.NONE:
                return WebhookResponse(
                    status="rejected",
                    action="NONE",
                    details="Could not determine action from alert",
                )

            # Security check
            if not security.validate(alert, headers):
                logger.warning("webhook_security_failed", symbol=alert.symbol)
                raise HTTPException(status_code=403, detail="Invalid webhook token")

            # Deduplication & rate limiting
            if not alert_manager.should_process(alert):
                return WebhookResponse(
                    status="rejected",
                    action=alert.action.value,
                    details="Duplicate or rate-limited alert",
                )

            # Handle CLOSE actions
            if alert.action in (AlertAction.CLOSE, AlertAction.CLOSE_LONG, AlertAction.CLOSE_SHORT):
                signal = None
                close_target = alert.symbol
                if bot:
                    bot.portfolio_engine.close_position(close_target, alert.price, 0.0)
                    logger.info("alert_close_position", symbol=close_target)

                alert_manager.record(alert, signal)
                return WebhookResponse(
                    status="ok",
                    action=alert.action.value,
                    signal_created=False,
                    alert_id=alert.alert_id,
                    details=f"Position close requested for {close_target}",
                )

            # Get current price from bot if available
            current_price = alert.price
            if current_price <= 0 and bot:
                try:
                    candles = await bot.data_service.get_latest_candles(alert.symbol, "15m", n=1)
                    if candles:
                        current_price = candles[0].close
                except Exception:
                    pass

            # Convert alert to native Signal
            signal = converter.convert(alert, current_price=current_price)

            # Route through Risk + Execution if bot is connected
            if signal and bot:
                portfolio_state = bot.risk_engine.get_portfolio_state()
                risk_decision = bot.risk_engine.evaluate_signal(signal, portfolio_state)

                if risk_decision.approved:
                    exec_record = await bot.execution_engine.place_entry_limit(signal, risk_decision)
                    if exec_record and not exec_record.cancelled:
                        bot.portfolio_engine.open_position(
                            pair=signal.pair,
                            direction=signal.direction,
                            entry_price=exec_record.actual_price,
                            size=risk_decision.position_size,
                            stop_loss=risk_decision.stop_loss,
                            tp1=signal.tp1,
                            tp2=signal.tp2,
                            strategy=signal.strategy.value,
                        )
                        logger.info("tv_signal_executed",
                                    pair=signal.pair, direction=signal.direction.value,
                                    confidence=signal.confidence)

            alert_manager.record(alert, signal)

            return WebhookResponse(
                status="ok",
                action=alert.action.value,
                signal_created=signal is not None,
                alert_id=alert.alert_id,
                details=f"Alert processed: {alert.action.value} {alert.symbol}"
                         f" {'(signal created)' if signal else '(no signal)'}",
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error("webhook_error", error=str(e))
            return WebhookResponse(
                status="error",
                details=str(e),
            )

    # ═══════════════════════════════════════════════════════════
    # POST /webhook/tradingview/v2 — extended indicator webhook
    # ═══════════════════════════════════════════════════════════

    @router.post("/tradingview/v2", response_model=WebhookResponse)
    async def tradingview_webhook_v2(alert_data: TradingViewAlertV2, request: Request):
        """
        Enhanced TradingView webhook with indicator data.

        Example PineScript alert message for V2:
        ```json
        {
            "action": "BUY",
            "symbol": "BTCUSDT",
            "indicator": "rsi",
            "indicator_value": 28.5,
            "indicator_params": {"length": 14},
            "confidence": 0.85
        }
        ```

        The indicator data enables the bot to:
          - Compute adaptive stop-loss and take-profit levels
          - Cross-validate the signal with internal TA
          - Log the indicator context for later analysis
        """
        try:
            headers = dict(request.headers)

            # Build ParsedAlert from structured data
            alert = AlertParser.parse(
                json.dumps(alert_data.model_dump()).encode(),
                headers,
            )

            if alert.action == AlertAction.NONE:
                return WebhookResponse(status="rejected", details="No action specified")

            # Validate
            if not security.validate(alert, headers):
                raise HTTPException(status_code=403, detail="Invalid token")

            if not alert_manager.should_process(alert):
                return WebhookResponse(status="rejected", details="Duplicate/rate-limited")

            # If indicator data is present, enhance with indicator interpretation
            if alert_data.indicator and alert_data.indicator_value:
                interpretation = indicator_registry.interpret(
                    alert.symbol,
                    alert_data.indicator,
                    value=alert_data.indicator_value,
                    **alert_data.indicator_params,
                )
                # Adjust confidence based on indicator strength
                alert.confidence = round(
                    0.7 * alert.confidence + 0.3 * interpretation.get("strength", 0.5),
                    4,
                )
                alert.extra["indicator_interpretation"] = interpretation

            # Convert and execute (same logic as v1)
            current_price = alert.price
            if current_price <= 0 and bot:
                try:
                    candles = await bot.data_service.get_latest_candles(alert.symbol, "15m", n=1)
                    if candles:
                        current_price = candles[0].close
                except Exception:
                    pass

            signal = converter.convert(alert, current_price=current_price)

            if signal and bot:
                portfolio_state = bot.risk_engine.get_portfolio_state()
                risk_decision = bot.risk_engine.evaluate_signal(signal, portfolio_state)
                if risk_decision.approved:
                    await bot.execution_engine.place_entry_limit(signal, risk_decision)

            alert_manager.record(alert, signal)

            return WebhookResponse(
                status="ok",
                action=alert.action.value,
                signal_created=signal is not None,
                alert_id=alert.alert_id,
                details=f"V2 alert: {alert.action.value} {alert.symbol} "
                         f"(indicator: {alert_data.indicator}={alert_data.indicator_value})",
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error("webhook_v2_error", error=str(e))
            return WebhookResponse(status="error", details=str(e))

    # ═══════════════════════════════════════════════════════════
    # GET /webhook/indicators — list supported indicators
    # ═══════════════════════════════════════════════════════════

    @router.get("/indicators", response_model=IndicatorListResponse)
    async def list_indicators():
        """
        List all supported indicators with PineScript templates.

        Use these templates to configure TradingView alerts that
        send properly-formatted signals to the webhook.
        """
        indicators = indicator_registry.list_indicators()
        return IndicatorListResponse(
            indicators=indicators,
            count=len(indicators),
        )

    # ═══════════════════════════════════════════════════════════
    # GET /webhook/indicators/{name} — specific indicator template
    # ═══════════════════════════════════════════════════════════

    @router.get("/indicators/{name}")
    async def get_indicator_template(name: str):
        """Get PineScript alert template for a specific indicator."""
        template = indicator_registry.get_pinescript_template(name)
        if template is None:
            raise HTTPException(status_code=404, detail=f"Unknown indicator: {name}")

        # Generate webhook URL hint
        webhook_url = "https://your-bot.com/webhook/tradingview/v2"
        return {
            "indicator": name,
            **template,
            "webhook_url": webhook_url,
            "webhook_payload_example": {
                "action": "BUY",
                "symbol": "BTCUSDT",
                "indicator": name,
                "indicator_value": 0.0,
                "indicator_params": template["params"],
                "confidence": 0.8,
            },
        }

    # ═══════════════════════════════════════════════════════════
    # GET /webhook/social — social/sentiment signals
    # ═══════════════════════════════════════════════════════════

    @router.get("/social", response_model=SocialSignalResponse)
    async def get_social_signals(pair: str = Query("BTCUSDT", description="Trading pair")):
        """
        Get social and sentiment signals for a trading pair.

        Returns sentiment score, Fear & Greed index, social volume,
        whale activity, influencer sentiment, and a composite recommendation.

        Use these signals to enhance TradingView alerts:
          - High Fear & Greed (>70) → tighten stops even on BUY signals
          - Extreme Fear (<25) → increase position size on BUY signals
          - Whale "distributing" → reduce confidence on BUY signals
        """
        signals = social_registry.get_signals(pair)
        return SocialSignalResponse(
            pair=pair,
            asset=signals.get("asset", ""),
            signals=signals,
        )

    # ═══════════════════════════════════════════════════════════
    # GET /webhook/social/fear-greed — Fear & Greed only
    # ═══════════════════════════════════════════════════════════

    @router.get("/social/fear-greed")
    async def get_fear_greed():
        """Get the current Fear & Greed Index value."""
        return social_registry.get_fear_greed_only()

    # ═══════════════════════════════════════════════════════════
    # GET /webhook/social/supported — list supported assets
    # ═══════════════════════════════════════════════════════════

    @router.get("/social/supported")
    async def get_supported_social_assets():
        """List assets with available social/sentiment data."""
        return {
            "assets": social_registry.list_supported_assets(),
            "count": len(social_registry.list_supported_assets()),
        }

    # ═══════════════════════════════════════════════════════════
    # GET /webhook/alerts/recent — recent alert history
    # ═══════════════════════════════════════════════════════════

    @router.get("/alerts/recent")
    async def get_recent_alerts(n: int = Query(20, le=100)):
        """Get recent alert history."""
        return {
            "alerts": alert_manager.get_recent_alerts(n),
            "total_processed": len(alert_manager._history),
        }

    return router
