"""
Crypto Bot v4.4 — TradingView Integration Tests
Tests alert parsing, signal conversion, indicator registry, and social signals.
"""

import json
from datetime import datetime, timezone

import pytest

from core.models import Direction, Signal, StrategyType
from services.tradingview_service import (
    AlertParser, AlertToSignalConverter, AlertManager,
    WebhookSecurity, AlertAction, AlertFormat, ParsedAlert,
)
from services.tradingview_service.indicators.registry import (
    IndicatorRegistry, RSIAdapter, MACDAdapter,
    BollingerBandsAdapter, MovingAverageAdapter, StochasticAdapter,
)
from services.tradingview_service.social.registry import SocialSignalRegistry


# ═══════════════════════════════════════════════════════════════
# Alert Parser Tests
# ═══════════════════════════════════════════════════════════════

class TestAlertParserFormatDetection:
    def test_detect_json(self):
        body = b'{"action": "BUY", "symbol": "BTCUSDT"}'
        fmt = AlertParser.detect_format(body)
        assert fmt == AlertFormat.JSON

    def test_detect_octobot(self):
        body = b"EXCHANGE=binance SYMBOL=BTCUSDT SIGNAL=BUY"
        fmt = AlertParser.detect_format(body)
        assert fmt == AlertFormat.OCTOBOT

    def test_detect_plain_text(self):
        body = b"BUY BTCUSDT sl=64500 tp=66000"
        fmt = AlertParser.detect_format(body)
        assert fmt == AlertFormat.PLAIN_TEXT

    def test_detect_pine_connector(self):
        body = b'{"close_position": true, "symbol": "BTCUSDT"}'
        fmt = AlertParser.detect_format(body)
        assert fmt == AlertFormat.PINE_CONNECTOR


class TestAlertParserJSON:
    def test_json_buy(self):
        body = json.dumps({
            "action": "BUY", "symbol": "BTCUSDT",
            "price": 65000, "stop_loss": 64500, "take_profit": 66000,
        }).encode()
        alert = AlertParser.parse(body)
        assert alert.action == AlertAction.BUY
        assert alert.symbol == "BTCUSDT"
        assert alert.price == 65000
        assert alert.stop_loss == 64500

    def test_json_sell_variant_keys(self):
        """Test that alternative JSON keys like 'signal', 'side' work."""
        body = json.dumps({
            "signal": "SELL", "ticker": "ETHUSDT",
            "entry": 3400, "sl": 3350, "tp": 3500,
        }).encode()
        alert = AlertParser.parse(body)
        assert alert.action == AlertAction.SELL
        assert alert.symbol == "ETHUSDT"
        assert alert.price == 3400

    def test_json_with_strategy_and_confidence(self):
        body = json.dumps({
            "action": "LONG", "pair": "SOLUSDT",
            "strategy": "rsi_oversold", "confidence": 0.92,
            "indicator": "rsi", "indicator_value": 22.5,
        }).encode()
        alert = AlertParser.parse(body)
        # LONG/action → kept verbatim; converter maps to Direction.LONG
        assert alert.action == AlertAction.LONG
        assert alert.strategy_name == "rsi_oversold"
        assert alert.confidence == 0.92
        assert alert.indicator_value == 22.5


class TestAlertParserOctoBot:
    def test_octobot_buy(self):
        body = b"SIGNAL=BUY EXCHANGE=binance SYMBOL=BTCUSDT PRICE=65000 STOP_LOSS=64500 TAKE_PROFIT=66000"
        alert = AlertParser.parse(body)
        assert alert.action == AlertAction.BUY
        assert alert.symbol == "BTCUSDT"
        assert alert.price == 65000

    def test_octobot_with_token(self):
        body = b"SIGNAL=SELL SYMBOL=ETHUSDT TOKEN=abc123 QUANTITY=0.5 LEVERAGE=5"
        alert = AlertParser.parse(body)
        assert alert.action == AlertAction.SELL
        assert alert.token == "abc123"
        assert alert.quantity == 0.5
        assert alert.leverage == 5

    def test_octobot_close(self):
        body = b"SIGNAL=CLOSE SYMBOL=BTCUSDT EXCHANGE=binance"
        alert = AlertParser.parse(body)
        assert alert.action == AlertAction.CLOSE


class TestAlertParserPlainText:
    def test_plain_buy_with_sl_tp(self):
        body = b"BUY BTCUSDT sl=64500 tp=66000"
        alert = AlertParser.parse(body)
        assert alert.action == AlertAction.BUY
        assert alert.symbol == "BTCUSDT"
        assert alert.stop_loss == 64500
        assert alert.take_profit == 66000

    def test_plain_sell(self):
        body = b"SELL ETHUSDT sl=3500 tp=3300"
        alert = AlertParser.parse(body)
        assert alert.action == AlertAction.SELL

    def test_plain_text_no_action(self):
        body = b"just some random text without action"
        alert = AlertParser.parse(body)
        assert alert.action == AlertAction.NONE


# ═══════════════════════════════════════════════════════════════
# Alert → Signal Converter Tests
# ═══════════════════════════════════════════════════════════════

class TestAlertToSignalConverter:
    def test_converts_buy_alert(self):
        converter = AlertToSignalConverter()
        alert = ParsedAlert(
            action=AlertAction.BUY, symbol="BTCUSDT",
            price=65000, stop_loss=64500, take_profit=66000,
            confidence=0.85, strategy_name="rsi_oversold",
        )
        signal = converter.convert(alert, current_price=65000)
        assert signal is not None
        assert signal.pair == "BTCUSDT"
        assert signal.direction == Direction.LONG
        assert signal.entry_market == 65000
        assert signal.confidence > 0
        assert signal.regime == "tv_alert"

    def test_converts_sell_alert(self):
        converter = AlertToSignalConverter()
        alert = ParsedAlert(
            action=AlertAction.SELL, symbol="ETHUSDT",
            price=3400, stop_loss=3450, take_profit=3300,
        )
        signal = converter.convert(alert, current_price=3400)
        assert signal is not None
        assert signal.direction == Direction.SHORT

    def test_skips_close_alerts(self):
        converter = AlertToSignalConverter()
        alert = ParsedAlert(action=AlertAction.CLOSE, symbol="BTCUSDT")
        signal = converter.convert(alert)
        assert signal is None

    def test_skips_no_action(self):
        converter = AlertToSignalConverter()
        alert = ParsedAlert(action=AlertAction.NONE)
        signal = converter.convert(alert)
        assert signal is None

    def test_computes_sl_tp_when_missing(self):
        """When no SL/TP in alert, indicator registry provides defaults."""
        converter = AlertToSignalConverter()
        alert = ParsedAlert(
            action=AlertAction.BUY, symbol="BTCUSDT",
            price=65000, stop_loss=0, take_profit=0,
        )
        signal = converter.convert(alert, current_price=65000)
        assert signal is not None
        assert signal.stop_loss > 0
        assert signal.tp1 > 0
        assert signal.stop_loss < signal.entry_market  # LONG: SL below entry

    def test_maps_strategy_to_bot_type(self):
        converter = AlertToSignalConverter()
        for strat_name, expected in [
            ("sweep_liquidity", StrategyType.SWEEP),
            ("bounce_level", StrategyType.BOUNCE),
            ("breakout_momentum", StrategyType.BREAKOUT),
            ("unknown_strategy", StrategyType.SWEEP),  # default
        ]:
            alert = ParsedAlert(
                action=AlertAction.BUY, symbol="BTCUSDT",
                price=65000, stop_loss=64500, take_profit=66000,
                strategy_name=strat_name,
            )
            signal = converter.convert(alert, current_price=65000)
            assert signal.strategy == expected, f"{strat_name} → {expected}"


# ═══════════════════════════════════════════════════════════════
# Indicator Adapter Tests
# ═══════════════════════════════════════════════════════════════

class TestRSIAdapter:
    def test_oversold(self):
        result = RSIAdapter.interpret(25.0)
        assert result["signal"] == "oversold"
        assert result["bias"] == "LONG"

    def test_overbought(self):
        result = RSIAdapter.interpret(75.0)
        assert result["signal"] == "overbought"
        assert result["bias"] == "SHORT"

    def test_neutral_bullish(self):
        result = RSIAdapter.interpret(55.0)
        assert result["signal"] == "bullish_neutral"

    def test_recommend_sl_tp_long(self):
        rec = RSIAdapter.recommend_sl_tp(65000, 25.0, Direction.LONG)
        assert rec["stop_loss"] < 65000
        assert rec["take_profit"] > 65000


class TestMACDAdapter:
    def test_bullish(self):
        result = MACDAdapter.interpret(0, 0, 50.0)
        assert result["bias"] == "LONG"

    def test_bearish(self):
        result = MACDAdapter.interpret(0, 0, -30.0)
        assert result["bias"] == "SHORT"


class TestBollingerBandsAdapter:
    def test_oversold(self):
        result = BollingerBandsAdapter.interpret(64000, 66000, 65000, 64000)
        assert result["signal"] == "oversold_bb"

    def test_squeeze(self):
        result = BollingerBandsAdapter.interpret(65000, 65150, 65000, 64850)
        assert result["squeeze"] is True


class TestStochasticAdapter:
    def test_overbought(self):
        result = StochasticAdapter.interpret(85.0, 82.0)
        assert result["signal"] == "overbought"

    def test_oversold(self):
        result = StochasticAdapter.interpret(15.0, 18.0)
        assert result["signal"] == "oversold"


# ═══════════════════════════════════════════════════════════════
# Indicator Registry Tests
# ═══════════════════════════════════════════════════════════════

class TestIndicatorRegistry:
    def test_get_known_adapter(self):
        reg = IndicatorRegistry()
        assert reg.get_adapter("rsi") == RSIAdapter
        assert reg.get_adapter("MACD") == MACDAdapter
        assert reg.get_adapter("bollinger_bands") == BollingerBandsAdapter
        assert reg.get_adapter("ma_cross") == MovingAverageAdapter

    def test_unknown_indicator(self):
        reg = IndicatorRegistry()
        assert reg.get_adapter("nonexistent_indicator") is None

    def test_interpret_known(self):
        reg = IndicatorRegistry()
        result = reg.interpret("BTCUSDT", "rsi", value=28.0)
        assert result["signal"] == "oversold"

    def test_recommend_sl_tp_defaults(self):
        reg = IndicatorRegistry()
        rec = reg.recommend_sl_tp("BTCUSDT", "1h", 65000, Direction.LONG)
        assert rec["stop_loss"] < 65000
        assert rec["take_profit"] > 65000
        assert "take_profit_2" in rec

    def test_pinescript_templates(self):
        reg = IndicatorRegistry()
        for name in ["rsi", "macd", "ema", "bollinger_bands", "stochastic"]:
            template = reg.get_pinescript_template(name)
            assert template is not None, f"Missing template for {name}"
            assert "params" in template
            assert "alert_condition" in template

    def test_list_indicators(self):
        reg = IndicatorRegistry()
        indicators = reg.list_indicators()
        assert len(indicators) >= 5


# ═══════════════════════════════════════════════════════════════
# Social Signal Tests
# ═══════════════════════════════════════════════════════════════

class TestSocialSignalRegistry:
    def test_get_signals_bitcoin(self):
        reg = SocialSignalRegistry()
        signals = reg.get_signals("BTCUSDT")
        assert "sentiment_score" in signals
        assert "fear_greed" in signals
        assert "composite" in signals
        assert "recommendation" in signals
        assert 0 <= signals["sentiment_score"] <= 1
        assert 0 <= signals["composite"] <= 1

    def test_get_signals_ethereum(self):
        reg = SocialSignalRegistry()
        signals = reg.get_signals("ETHUSDT")
        assert signals["asset"] == "ethereum"

    def test_unknown_asset_fallback(self):
        reg = SocialSignalRegistry()
        signals = reg.get_signals("RANDOMCOINUSDT")
        assert "sentiment_score" in signals

    def test_fear_greed(self):
        reg = SocialSignalRegistry()
        fg = reg.get_fear_greed_only()
        assert "value" in fg
        assert "label" in fg
        assert 0 <= fg["value"] <= 100

    def test_custom_alert(self):
        reg = SocialSignalRegistry()
        reg.add_custom_alert("telegram", "BTCUSDT", "Whale bought 500 BTC", 0.85)
        signals = reg.get_signals("BTCUSDT")
        assert len(signals["custom_alerts"]) >= 1

    def test_cache_returns_same_result(self):
        reg = SocialSignalRegistry()
        s1 = reg.get_signals("BTCUSDT")
        s2 = reg.get_signals("BTCUSDT")
        assert s1["composite"] == s2["composite"]


# ═══════════════════════════════════════════════════════════════
# Alert Manager Tests
# ═══════════════════════════════════════════════════════════════

class TestAlertManager:
    def test_should_process_new_alert(self):
        mgr = AlertManager()
        alert = ParsedAlert(action=AlertAction.BUY, symbol="BTCUSDT", alert_id="test-1")
        assert mgr.should_process(alert) is True

    def test_deduplicates_by_id(self):
        mgr = AlertManager()
        alert = ParsedAlert(action=AlertAction.BUY, symbol="BTCUSDT", alert_id="test-1")
        assert mgr.should_process(alert) is True
        mgr.record(alert)
        assert mgr.should_process(alert) is False  # duplicate

    def test_records_alert(self):
        mgr = AlertManager()
        alert = ParsedAlert(action=AlertAction.BUY, symbol="BTCUSDT", alert_id="rec-1")
        mgr.record(alert)
        recent = mgr.get_recent_alerts(5)
        assert len(recent) >= 1
        assert recent[-1]["symbol"] == "BTCUSDT"


# ═══════════════════════════════════════════════════════════════
# Webhook Security Tests
# ═══════════════════════════════════════════════════════════════

class TestWebhookSecurity:
    def test_no_token_configured_allows_all(self):
        sec = WebhookSecurity(webhook_token="")
        alert = ParsedAlert(action=AlertAction.BUY, symbol="BTCUSDT")
        assert sec.validate(alert) is True

    def test_correct_token_in_body(self):
        sec = WebhookSecurity(webhook_token="secret123")
        alert = ParsedAlert(action=AlertAction.BUY, symbol="BTCUSDT", token="secret123")
        assert sec.validate(alert) is True

    def test_wrong_token_rejected(self):
        sec = WebhookSecurity(webhook_token="secret123")
        alert = ParsedAlert(action=AlertAction.BUY, symbol="BTCUSDT", token="wrong")
        assert sec.validate(alert) is False

    def test_token_in_header(self):
        sec = WebhookSecurity(webhook_token="header-token")
        alert = ParsedAlert(action=AlertAction.BUY, symbol="BTCUSDT")
        assert sec.validate(alert, headers={"x-webhook-token": "header-token"}) is True

    def test_token_in_tv_header(self):
        sec = WebhookSecurity(webhook_token="tv-token")
        alert = ParsedAlert(action=AlertAction.BUY, symbol="BTCUSDT")
        assert sec.validate(alert, headers={"x-tv-token": "tv-token"}) is True
