"""
Crypto Bot v4.4 — TradingView Integration
Webhook server that receives TradingView alerts and converts them into
trading signals for the Strategy Engine.

Inspired by OctoBot's TradingView webhook implementation but extended with:
  - Classic indicator adapters (RSI, EMA/SMA, MACD, BB, etc.)
  - Social/sentiment indicators
  - Multi-format alert parsing (JSON, plain-text, OctoBot-style, PineConnector-style)
  - Deduplication, rate limiting, security token validation
  - Full signal lifecycle: alert → parsed signal → risk evaluation → execution
"""

import hashlib
import hmac
import json
import re
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs

import structlog

from core.models import Direction, Signal, StrategyType
from services.tradingview_service.indicators.registry import IndicatorRegistry
from services.tradingview_service.social.registry import SocialSignalRegistry

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# Alert Parsing Data Structures
# ═══════════════════════════════════════════════════════════════

class AlertFormat(str, Enum):
    """Supported TradingView alert message formats."""
    JSON = "json"                     # {"action": "BUY", "symbol": "BTCUSDT", ...}
    OCTOBOT = "octobot"               # EXCHANGE=binance SYMBOL=BTCUSDT SIGNAL=BUY
    PLAIN_TEXT = "plain_text"         # BUY BTCUSDT sl=64500 tp=66000
    PINE_CONNECTOR = "pine_connector" # PineConnector format
    ALERTATRON = "alertatron"         # Alertatron format


class AlertAction(str, Enum):
    """Trading actions from alerts."""
    BUY = "BUY"
    SELL = "SELL"
    LONG = "LONG"
    SHORT = "SHORT"
    CLOSE = "CLOSE"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"
    CANCEL = "CANCEL"
    NONE = "NONE"


@dataclass
class ParsedAlert:
    """Normalized alert after parsing regardless of input format."""
    action: AlertAction = AlertAction.NONE
    symbol: str = ""
    exchange: str = "binance"
    price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    take_profit_2: float = 0.0
    quantity: float = 0.0
    leverage: int = 1
    confidence: float = 0.8
    strategy_name: str = ""
    indicator_name: str = ""
    indicator_value: float = 0.0
    timeframe: str = ""
    alert_id: str = ""
    alert_message: str = ""
    token: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Alert Parser
# ═══════════════════════════════════════════════════════════════

class AlertParser:
    """
    Parses incoming TradingView alerts in multiple formats.
    Detects format automatically and normalizes to ParsedAlert.
    """

    # OctoBot format pattern: KEY=VALUE pairs separated by spaces or newlines
    OCTOBOT_RE = re.compile(
        r'(?:^|\s)(EXCHANGE|SYMBOL|SIGNAL|TOKEN|STRATEGY|STOP_LOSS|'
        r'TAKE_PROFIT|QUANTITY|LEVERAGE|TIMEFRAME|CONFIDENCE|PRICE|'
        r'TP1|TP2|SL|ENTRY)=([^\s]+)',
        re.IGNORECASE,
    )

    # Plain text pattern: ACTION SYMBOL [price=...] [sl=...] [tp=...]
    PLAIN_TEXT_RE = re.compile(
        r'^(BUY|SELL|LONG|SHORT|CLOSE)\s+'
        r'([A-Z0-9]+)[\s:]*(?:.*?sl[=:\s]*([\d.]+))?'
        r'(?:.*?tp[=:\s]*([\d.]+))?',
        re.IGNORECASE,
    )

    @classmethod
    def detect_format(cls, raw_body: bytes) -> AlertFormat:
        """Auto-detect the alert format from body content."""
        try:
            body = raw_body.decode("utf-8").strip()
        except UnicodeDecodeError:
            body = raw_body.decode("latin-1").strip()

        # JSON
        if body.startswith("{") or body.startswith("["):
            # Check for PineConnector-specific JSON keys
            try:
                data = json.loads(body)
                if "close_position" in data or "reverse_position" in data:
                    return AlertFormat.PINE_CONNECTOR
            except (json.JSONDecodeError, TypeError):
                pass
            return AlertFormat.JSON

        # Plain text: starts with known action word
        first_word = body.split()[0].upper() if body.split() else ""
        if first_word in ("BUY", "SELL", "LONG", "SHORT", "CLOSE"):
            return AlertFormat.PLAIN_TEXT

        # OctoBot: KEY=VALUE ...
        if cls.OCTOBOT_RE.search(body):
            return AlertFormat.OCTOBOT

        # Fallback: treat as plain text
        return AlertFormat.PLAIN_TEXT

    @classmethod
    def parse(cls, raw_body: bytes, headers: Optional[dict] = None) -> ParsedAlert:
        """
        Parse a raw webhook body into a normalized ParsedAlert.
        Auto-detects format.
        """
        fmt = cls.detect_format(raw_body)

        if fmt == AlertFormat.JSON:
            return cls._parse_json(raw_body, headers)
        elif fmt == AlertFormat.OCTOBOT:
            return cls._parse_octobot(raw_body)
        elif fmt == AlertFormat.PINE_CONNECTOR:
            return cls._parse_pine_connector(raw_body)
        else:
            return cls._parse_plain_text(raw_body)

    @classmethod
    def _parse_json(cls, raw_body: bytes, headers: Optional[dict] = None) -> ParsedAlert:
        """Parse JSON alert format."""
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            # Try with URL-encoded JSON
            try:
                body_str = raw_body.decode("utf-8")
                parsed = parse_qs(body_str)
                # Some services send urlencoded JSON payload
                if "payload" in parsed:
                    data = json.loads(parsed["payload"][0])
                else:
                    data = {k: v[0] for k, v in parsed.items()}
            except Exception:
                logger.warning("alert_json_parse_failed", body=raw_body[:200])
                return ParsedAlert()

        return cls._normalize_json(data, headers)

    @classmethod
    def _normalize_json(cls, data: dict, headers: Optional[dict] = None) -> ParsedAlert:
        """Normalize JSON data into ParsedAlert — handles many JSON schemas."""
        # Map common JSON field names
        action_map = {
            "action": data.get("action") or data.get("signal") or data.get("side") or data.get("type"),
            "buy": "BUY", "sell": "SELL", "long": "LONG", "short": "SHORT",
            "close_long": "CLOSE_LONG", "close_short": "CLOSE_SHORT",
            "exit_long": "CLOSE_LONG", "exit_short": "CLOSE_SHORT",
        }
        raw_action = str(data.get("action") or data.get("signal") or data.get("side") or data.get("type", "")).upper()
        if raw_action in ("BUY", "SELL", "LONG", "SHORT", "CLOSE", "CLOSE_LONG", "CLOSE_SHORT", "CANCEL"):
            pass
        elif raw_action == "1" or raw_action == "true":
            raw_action = "BUY"
        elif raw_action == "-1" or raw_action == "exit":
            raw_action = "SELL"

        try:
            action = AlertAction(raw_action)
        except ValueError:
            action = AlertAction.NONE

        return ParsedAlert(
            action=action,
            symbol=str(data.get("symbol") or data.get("ticker") or data.get("pair") or "").upper(),
            exchange=str(data.get("exchange") or data.get("market") or "binance").lower(),
            price=float(data.get("price") or data.get("entry") or 0),
            stop_loss=float(data.get("stop_loss") or data.get("sl") or data.get("stop") or 0),
            take_profit=float(data.get("take_profit") or data.get("tp") or data.get("tp1") or 0),
            take_profit_2=float(data.get("tp2") or 0),
            quantity=float(data.get("quantity") or data.get("amount") or data.get("size") or 0),
            leverage=int(data.get("leverage") or 1),
            confidence=float(data.get("confidence") or data.get("score") or 0.8),
            strategy_name=str(data.get("strategy") or data.get("strategy_name") or ""),
            indicator_name=str(data.get("indicator") or ""),
            indicator_value=float(data.get("indicator_value") or data.get("value") or 0),
            timeframe=str(data.get("timeframe") or data.get("interval") or ""),
            alert_id=str(data.get("alert_id") or data.get("id") or ""),
            alert_message=str(data.get("message") or data.get("comment") or ""),
            token=str(data.get("token") or data.get("webhook_token") or ""),
            timestamp=datetime.now(timezone.utc),
            raw=data,
        )

    @classmethod
    def _parse_octobot(cls, raw_body: bytes) -> ParsedAlert:
        """Parse OctoBot-format alert: KEY=VALUE KEY=VALUE ..."""
        body = raw_body.decode("utf-8", errors="replace")
        matches = cls.OCTOBOT_RE.findall(body)

        data = {}
        for key, value in matches:
            data[key.upper()] = value.strip()

        # Also try query-style: key=value&key=value
        if not data and "=" in body:
            try:
                parsed_qs = parse_qs(body)
                data = {k.upper(): v[0] for k, v in parsed_qs.items()}
            except Exception:
                pass

        signal_str = data.get("SIGNAL", "").upper()
        if signal_str in ("BUY", "LONG", "ENTER_LONG"):
            action = AlertAction.BUY
        elif signal_str in ("SELL", "SHORT", "ENTER_SHORT"):
            action = AlertAction.SELL
        elif signal_str in ("CLOSE", "EXIT", "CLOSE_ALL"):
            action = AlertAction.CLOSE
        else:
            action = AlertAction.NONE

        return ParsedAlert(
            action=action,
            symbol=data.get("SYMBOL", "").upper(),
            exchange=data.get("EXCHANGE", "binance").lower(),
            price=float(data.get("PRICE") or data.get("ENTRY") or 0),
            stop_loss=float(data.get("STOP_LOSS") or data.get("SL") or 0),
            take_profit=float(data.get("TAKE_PROFIT") or data.get("TP") or data.get("TP1") or 0),
            take_profit_2=float(data.get("TP2") or 0),
            quantity=float(data.get("QUANTITY") or 0),
            leverage=int(data.get("LEVERAGE") or 1),
            confidence=float(data.get("CONFIDENCE") or 0.8),
            strategy_name=data.get("STRATEGY", ""),
            timeframe=data.get("TIMEFRAME", ""),
            token=data.get("TOKEN", ""),
            alert_message=body,
            timestamp=datetime.now(timezone.utc),
            raw=data,
        )

    @classmethod
    def _parse_pine_connector(cls, raw_body: bytes) -> ParsedAlert:
        """Parse PineConnector-format alert."""
        try:
            data = json.loads(raw_body)
        except json.JSONDecodeError:
            return cls._parse_octobot(raw_body)  # fallback

        raw_action = ""
        if data.get("close_position"):
            raw_action = "CLOSE"
        elif data.get("reverse_position"):
            raw_action = data.get("reverse_position", "").upper()
        elif data.get("action"):
            raw_action = data["action"].upper()
        elif data.get("side"):
            raw_action = data["side"].upper()

        try:
            action = AlertAction(raw_action)
        except ValueError:
            action = AlertAction.NONE

        return ParsedAlert(
            action=action,
            symbol=str(data.get("symbol", "")).upper(),
            stop_loss=float(data.get("stopLoss") or data.get("sl") or 0),
            take_profit=float(data.get("takeProfit") or data.get("tp") or 0),
            quantity=float(data.get("quantity") or data.get("size") or 0),
            raw=data,
            timestamp=datetime.now(timezone.utc),
        )

    @classmethod
    def _parse_plain_text(cls, raw_body: bytes) -> ParsedAlert:
        """Parse plain-text alert."""
        body = raw_body.decode("utf-8", errors="replace").strip()
        upper = body.upper()

        match = cls.PLAIN_TEXT_RE.match(upper)
        if not match:
            return ParsedAlert(alert_message=body, timestamp=datetime.now(timezone.utc))

        action_str = match.group(1)
        if action_str in ("BUY", "LONG"):
            action = AlertAction.BUY
        elif action_str in ("SELL", "SHORT"):
            action = AlertAction.SELL
        elif action_str == "CLOSE":
            action = AlertAction.CLOSE
        else:
            action = AlertAction.NONE

        return ParsedAlert(
            action=action,
            symbol=match.group(2) or "",
            stop_loss=float(match.group(3) or 0),
            take_profit=float(match.group(4) or 0),
            alert_message=body,
            timestamp=datetime.now(timezone.utc),
        )


# ═══════════════════════════════════════════════════════════════
# Alert → Signal Converter
# ═══════════════════════════════════════════════════════════════

class AlertToSignalConverter:
    """
    Converts a ParsedAlert into the bot's native Signal format,
    using indicator data for enhanced decision quality.
    """

    def __init__(self, indicator_registry: Optional[IndicatorRegistry] = None):
        self.indicator_registry = indicator_registry or IndicatorRegistry()
        self.social_registry = SocialSignalRegistry()

    def convert(self, alert: ParsedAlert, current_price: float = 0.0) -> Optional[Signal]:
        """
        Convert a parsed alert into a trading Signal.

        Args:
            alert: Normalized parsed alert
            current_price: Current market price (fetched from exchange)

        Returns:
            Signal dataclass, or None if conversion is not possible
        """
        if alert.action in (AlertAction.NONE, AlertAction.CANCEL):
            return None

        # Determine direction
        if alert.action in (AlertAction.BUY, AlertAction.LONG):
            direction = Direction.LONG
        elif alert.action in (AlertAction.SELL, AlertAction.SHORT):
            direction = Direction.SHORT
        else:
            # CLOSE actions: handled separately by Portfolio Engine
            return None

        entry = alert.price if alert.price > 0 else current_price
        if entry <= 0:
            logger.warning("alert_no_price", symbol=alert.symbol)
            return None

        # Compute stop-loss and take-profit from alert or defaults
        stop_loss = alert.stop_loss
        take_profit = alert.take_profit
        take_profit_2 = alert.take_profit_2

        # If no SL/TP provided, use indicator-based defaults
        if stop_loss <= 0 or take_profit <= 0:
            indicator_rec = self.indicator_registry.recommend_sl_tp(
                alert.symbol, alert.timeframe, entry, direction
            )
            if stop_loss <= 0:
                stop_loss = indicator_rec.get("stop_loss", entry * 0.98 if direction == Direction.LONG else entry * 1.02)
            if take_profit <= 0:
                take_profit = indicator_rec.get("take_profit", entry * 1.04 if direction == Direction.LONG else entry * 0.96)
            if take_profit_2 <= 0:
                take_profit_2 = indicator_rec.get("take_profit_2", 0.0)

        # Enhance confidence using social/sentiment signals
        confidence = alert.confidence

        # Apply social sentiment boost if available
        social_data = self.social_registry.get_signals(alert.symbol)
        if social_data:
            sentiment_boost = social_data.get("sentiment_score", 0.0)
            trust_boost = social_data.get("trust_score", 0.0)
            # Blend alert confidence with social signals (30% weight)
            confidence = 0.7 * confidence + 0.15 * sentiment_boost + 0.15 * trust_boost
            confidence = min(1.0, max(0.0, confidence))

        # Map alert strategy to bot strategy type
        strategy = self._map_strategy(alert)

        return Signal(
            pair=alert.symbol,
            direction=direction,
            entry_market=entry,
            entry_limit=entry * 0.9995 if direction == Direction.LONG else entry * 1.0005,
            stop_loss=stop_loss,
            tp1=take_profit,
            tp2=take_profit_2 if take_profit_2 > 0 else take_profit * 1.5,
            strategy=strategy,
            confidence=round(confidence, 4),
            regime="tv_alert",  # Mark as TradingView-generated
            factors=[
                {"type": "tradingview_alert", "strategy": alert.strategy_name},
                {"type": "indicator", "name": alert.indicator_name, "value": alert.indicator_value},
            ],
            timestamp=alert.timestamp,
        )

    @staticmethod
    def _map_strategy(alert: ParsedAlert) -> StrategyType:
        """Map alert to the closest bot strategy."""
        strat = alert.strategy_name.lower()
        if "sweep" in strat or "liquidity" in strat:
            return StrategyType.SWEEP
        if "bounce" in strat or "reversal" in strat:
            return StrategyType.BOUNCE
        if "breakout" in strat or "momentum" in strat or "trend" in strat:
            return StrategyType.BREAKOUT
        # Default: use SWEEP as it works across regimes
        return StrategyType.SWEEP


# ═══════════════════════════════════════════════════════════════
# Deduplication & Rate Limiting
# ═══════════════════════════════════════════════════════════════

@dataclass
class AlertRecord:
    """Stored alert for deduplication."""
    alert_id: str
    symbol: str
    action: str
    timestamp: datetime
    processed: bool = False
    signal: Optional[Signal] = None


class AlertManager:
    """
    Manages incoming alerts: deduplication, rate limiting, history.
    """

    MAX_HISTORY = 1000
    DEDUP_WINDOW_SEC = 30       # Deduplicate identical alerts within 30 seconds
    MAX_ALERTS_PER_MINUTE = 20  # Hard cap on alert processing

    def __init__(self):
        self._history: List[AlertRecord] = []
        self._minute_counts: List[float] = []  # timestamps of alerts in the last minute

    def should_process(self, alert: ParsedAlert) -> bool:
        """Check if an alert should be processed (not duplicate, not rate-limited)."""
        now = time.time()

        # Clean old minute counts
        self._minute_counts = [t for t in self._minute_counts if now - t < 60]

        # Rate limit check
        if len(self._minute_counts) >= self.MAX_ALERTS_PER_MINUTE:
            logger.warning("alert_rate_limit_exceeded", count=len(self._minute_counts))
            return False

        # Deduplication check
        if alert.alert_id:
            for record in self._history:
                age = (now - record.timestamp.timestamp())
                if age < self.DEDUP_WINDOW_SEC and record.alert_id == alert.alert_id:
                    logger.info("alert_duplicate", alert_id=alert.alert_id)
                    return False
        else:
            # Content-based dedup for alerts without IDs
            content_hash = f"{alert.symbol}:{alert.action.value}:{alert.price:.2f}"
            for record in self._history[-50:]:
                age = now - record.timestamp.timestamp()
                rec_hash = f"{record.symbol}:{record.action}:{record.raw.get('price', 0)}"
                if age < self.DEDUP_WINDOW_SEC and rec_hash == content_hash:
                    logger.info("alert_duplicate_content", content=content_hash)
                    return False

        return True

    def record(self, alert: ParsedAlert, signal: Optional[Signal] = None):
        """Record a processed alert."""
        self._minute_counts.append(time.time())

        record = AlertRecord(
            alert_id=alert.alert_id or hashlib.md5(
                f"{alert.symbol}{alert.action.value}{time.time()}".encode()
            ).hexdigest()[:12],
            symbol=alert.symbol,
            action=alert.action.value,
            timestamp=alert.timestamp,
            processed=True,
            signal=signal,
        )
        self._history.append(record)

        # Trim history
        if len(self._history) > self.MAX_HISTORY:
            self._history = self._history[-self.MAX_HISTORY:]

    def get_recent_alerts(self, n: int = 20) -> List[dict]:
        """Get most recent alerts for monitoring."""
        recent = self._history[-n:]
        return [
            {
                "id": r.alert_id,
                "symbol": r.symbol,
                "action": r.action,
                "timestamp": r.timestamp.isoformat(),
                "processed": r.processed,
                "has_signal": r.signal is not None,
            }
            for r in recent
        ]


# ═══════════════════════════════════════════════════════════════
# Security
# ═══════════════════════════════════════════════════════════════

class WebhookSecurity:
    """
    Validates webhook authenticity via secret token and optional HMAC.
    """

    def __init__(self, webhook_token: str = "", hmac_secret: str = ""):
        self.webhook_token = webhook_token
        self.hmac_secret = hmac_secret

    def validate(self, alert: ParsedAlert, headers: Optional[dict] = None) -> bool:
        """Validate that the webhook request is authentic."""
        # Token-based validation
        if self.webhook_token:
            # Check body-embedded token
            if alert.token and alert.token == self.webhook_token:
                return True

            # Check query parameter token
            if headers:
                query_token = headers.get("x-webhook-token") or headers.get("authorization", "").replace("Bearer ", "")
                if query_token and query_token == self.webhook_token:
                    return True

            # Check header token
            if headers and headers.get("x-tv-token") == self.webhook_token:
                return True

            # Token required but not matched
            if alert.token or (headers and "x-webhook-token" in headers):
                logger.warning("webhook_token_mismatch")
                return False

        # HMAC validation
        if self.hmac_secret and headers:
            signature = headers.get("x-signature") or headers.get("x-hub-signature-256", "")
            if signature:
                return self._verify_hmac(signature, headers)

        # No token configured → allow (dev mode)
        return True

    def _verify_hmac(self, signature: str, headers: dict) -> bool:
        """Verify HMAC-SHA256 signature."""
        try:
            computed = hmac.new(
                self.hmac_secret.encode(),
                json.dumps(headers, sort_keys=True).encode(),
                hashlib.sha256,
            ).hexdigest()
            return hmac.compare_digest(f"sha256={computed}", signature)
        except Exception:
            return False
