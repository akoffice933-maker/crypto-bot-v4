"""
Crypto Bot v4.4 — Indicator Registry
Maps TradingView indicator names to bot-compatible logic.
Provides recommended stop-loss / take-profit based on indicator values.
"""

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from core.models import Direction

logger = structlog.get_logger(__name__)


# ═══════════════════════════════════════════════════════════════
# Individual Indicator Adapters
# ═══════════════════════════════════════════════════════════════

class RSIAdapter:
    """RSI (Relative Strength Index) adapter."""

    @staticmethod
    def interpret(value: float) -> dict:
        if value >= 70:
            return {"signal": "overbought", "strength": min(1.0, (value - 70) / 20), "bias": "SHORT"}
        elif value <= 30:
            return {"signal": "oversold", "strength": min(1.0, (30 - value) / 20), "bias": "LONG"}
        else:
            # Neutral but trending
            if value > 50:
                return {"signal": "bullish_neutral", "strength": (value - 50) / 20, "bias": "LONG"}
            else:
                return {"signal": "bearish_neutral", "strength": (50 - value) / 20, "bias": "SHORT"}

    @staticmethod
    def recommend_sl_tp(entry: float, value: float, direction: Direction) -> dict:
        """Recommend SL/TP based on RSI value."""
        volatility_factor = 1.0
        if value >= 75 or value <= 25:
            volatility_factor = 1.5  # More volatile near extremes

        if direction == Direction.LONG:
            sl_distance = entry * 0.015 * volatility_factor
            tp_distance = entry * 0.03 * volatility_factor
        else:
            sl_distance = entry * 0.015 * volatility_factor
            tp_distance = entry * 0.03 * volatility_factor

        return {
            "stop_loss": round(entry - sl_distance if direction == Direction.LONG else entry + sl_distance, 2),
            "take_profit": round(entry + tp_distance if direction == Direction.LONG else entry - tp_distance, 2),
        }


class MACDAdapter:
    """MACD (Moving Average Convergence Divergence) adapter."""

    @staticmethod
    def interpret(value: float, signal_line: float = 0.0, histogram: float = 0.0) -> dict:
        if histogram > 0:
            return {"signal": "bullish", "strength": min(1.0, abs(histogram) / 100), "bias": "LONG"}
        else:
            return {"signal": "bearish", "strength": min(1.0, abs(histogram) / 100), "bias": "SHORT"}

    @staticmethod
    def recommend_sl_tp(entry: float, histogram: float, direction: Direction) -> dict:
        strength = min(1.0, abs(histogram) / 100)
        vol_factor = 1.0 + strength * 0.5

        if direction == Direction.LONG:
            sl = entry * (1 - 0.012 * vol_factor)
            tp = entry * (1 + 0.025 * vol_factor)
        else:
            sl = entry * (1 + 0.012 * vol_factor)
            tp = entry * (1 - 0.025 * vol_factor)

        return {"stop_loss": round(sl, 2), "take_profit": round(tp, 2)}


class BollingerBandsAdapter:
    """Bollinger Bands adapter."""

    @staticmethod
    def interpret(current_price: float, upper: float, middle: float, lower: float) -> dict:
        bandwidth = (upper - lower) / middle
        position = (current_price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

        if position < 0.15:
            return {"signal": "oversold_bb", "strength": 1.0 - position, "bias": "LONG", "squeeze": bandwidth < 0.05}
        elif position > 0.85:
            return {"signal": "overbought_bb", "strength": position, "bias": "SHORT", "squeeze": bandwidth < 0.05}
        elif bandwidth < 0.04:
            return {"signal": "squeeze", "strength": 1.0, "bias": "BREAKOUT", "squeeze": True}
        return {"signal": "neutral_bb", "strength": 0.5, "bias": "NEUTRAL", "squeeze": False}

    @staticmethod
    def recommend_sl_tp(entry: float, lower: float, upper: float, direction: Direction) -> dict:
        if direction == Direction.LONG:
            sl = lower * 0.995
            tp = upper * 0.99
        else:
            sl = upper * 1.005
            tp = lower * 1.01
        return {"stop_loss": round(sl, 2), "take_profit": round(tp, 2)}


class MovingAverageAdapter:
    """EMA/SMA crossover adapter."""

    @staticmethod
    def interpret(short_ma: float, long_ma: float, current_price: float) -> dict:
        crossover = short_ma - long_ma
        strength = min(1.0, abs(crossover) / current_price * 100)

        if crossover > 0 and current_price > short_ma:
            return {"signal": "strong_bullish", "strength": strength, "bias": "LONG"}
        elif crossover > 0:
            return {"signal": "bullish_crossover", "strength": strength, "bias": "LONG"}
        elif current_price < short_ma:
            return {"signal": "strong_bearish", "strength": strength, "bias": "SHORT"}
        else:
            return {"signal": "bearish_crossover", "strength": strength, "bias": "SHORT"}

    @staticmethod
    def recommend_sl_tp(entry: float, short_ma: float, long_ma: float, direction: Direction) -> dict:
        # Use MA distance as volatility estimate
        ma_distance = abs(short_ma - long_ma) / long_ma
        vol_factor = 1.0 + ma_distance * 5

        if direction == Direction.LONG:
            sl = entry * (1 - 0.01 * vol_factor)
            tp = entry * (1 + 0.025 * vol_factor)
        else:
            sl = entry * (1 + 0.01 * vol_factor)
            tp = entry * (1 - 0.025 * vol_factor)

        return {"stop_loss": round(sl, 2), "take_profit": round(tp, 2)}


class StochasticAdapter:
    """Stochastic Oscillator adapter."""

    @staticmethod
    def interpret(k: float, d: float) -> dict:
        if k > 80 and d > 80:
            return {"signal": "overbought", "strength": min(1.0, (k - 80) / 20), "bias": "SHORT"}
        elif k < 20 and d < 20:
            return {"signal": "oversold", "strength": min(1.0, (20 - k) / 20), "bias": "LONG"}
        elif k > d:
            return {"signal": "bullish_momentum", "strength": (k - d) / 50, "bias": "LONG"}
        return {"signal": "bearish_momentum", "strength": (d - k) / 50, "bias": "SHORT"}

    @staticmethod
    def recommend_sl_tp(entry: float, k: float, direction: Direction) -> dict:
        extreme_factor = 1.0 + max(0, (abs(k - 50) - 20) / 50)
        if direction == Direction.LONG:
            return {
                "stop_loss": round(entry * (1 - 0.012 * extreme_factor), 2),
                "take_profit": round(entry * (1 + 0.025 * extreme_factor), 2),
            }
        return {
            "stop_loss": round(entry * (1 + 0.012 * extreme_factor), 2),
            "take_profit": round(entry * (1 - 0.025 * extreme_factor), 2),
        }


class VolumeProfileAdapter:
    """Volume Profile / VPVR adapter."""

    @staticmethod
    def interpret(poc_price: float, va_high: float, va_low: float, current_price: float) -> dict:
        if current_price > va_high:
            return {"signal": "above_value_area", "strength": 0.6, "bias": "LONG"}
        elif current_price < va_low:
            return {"signal": "below_value_area", "strength": 0.6, "bias": "SHORT"}
        elif current_price > poc_price:
            return {"signal": "va_upper", "strength": 0.4, "bias": "LONG"}
        else:
            return {"signal": "va_lower", "strength": 0.4, "bias": "SHORT"}

    @staticmethod
    def recommend_sl_tp(entry: float, va_high: float, va_low: float, direction: Direction) -> dict:
        if direction == Direction.LONG:
            return {"stop_loss": round(va_low, 2), "take_profit": round(va_high, 2)}
        return {"stop_loss": round(va_high, 2), "take_profit": round(va_low, 2)}


# ═══════════════════════════════════════════════════════════════
# Indicator Registry (unified interface)
# ═══════════════════════════════════════════════════════════════

class IndicatorRegistry:
    """
    Central registry for all indicator adapters.
    Provides a unified interface to interpret indicator values and
    generate stop-loss / take-profit recommendations.
    """

    ADAPTERS = {
        "rsi": RSIAdapter,
        "macd": MACDAdapter,
        "bollinger_bands": BollingerBandsAdapter,
        "bb": BollingerBandsAdapter,
        "ema": MovingAverageAdapter,
        "sma": MovingAverageAdapter,
        "ma_cross": MovingAverageAdapter,
        "moving_average": MovingAverageAdapter,
        "stochastic": StochasticAdapter,
        "stoch": StochasticAdapter,
        "volume_profile": VolumeProfileAdapter,
        "vpvr": VolumeProfileAdapter,
    }

    # Indicator → recommended parameters for PineScript alerts
    PINESCRIPT_PARAMS = {
        "rsi": {
            "description": "RSI (Relative Strength Index)",
            "params": {"length": 14},
            "alert_condition": "rsiValue = ta.rsi(close, 14)\n// Alert when: rsiValue < 30 (oversold → BUY)\n// Alert when: rsiValue > 70 (overbought → SELL)",
        },
        "macd": {
            "description": "MACD (Moving Average Convergence Divergence)",
            "params": {"fast": 12, "slow": 26, "signal": 9},
            "alert_condition": "[macdLine, signalLine, hist] = ta.macd(close, 12, 26, 9)\n// Alert when: hist > 0 (BUY) or hist < 0 (SELL)",
        },
        "ema": {
            "description": "EMA Crossover",
            "params": {"fast": 9, "slow": 21},
            "alert_condition": "emaFast = ta.ema(close, 9)\nemaSlow = ta.ema(close, 21)\n// Alert when: emaFast > emaSlow (BUY) or emaFast < emaSlow (SELL)",
        },
        "bollinger_bands": {
            "description": "Bollinger Bands",
            "params": {"length": 20, "mult": 2.0},
            "alert_condition": "[middle, upper, lower] = ta.bb(close, 20, 2)\n// Alert when: close < lower (BUY) or close > upper (SELL)",
        },
        "stochastic": {
            "description": "Stochastic Oscillator",
            "params": {"k": 14, "d": 3},
            "alert_condition": "k = ta.stoch(close, high, low, 14)\nd = ta.sma(k, 3)\n// Alert when: k < 20 (oversold BUY) or k > 80 (overbought SELL)",
        },
    }

    def __init__(self):
        self._last_values: Dict[str, dict] = {}  # symbol → latest indicator values

    def get_adapter(self, indicator_name: str):
        """Get the adapter class for an indicator name."""
        name = indicator_name.lower().replace(" ", "_")
        return self.ADAPTERS.get(name)

    def interpret(self, symbol: str, indicator_name: str, **values) -> dict:
        """
        Interpret indicator values into a trading signal.

        Returns dict with keys: signal, strength, bias
        """
        adapter = self.get_adapter(indicator_name)
        if adapter is None:
            logger.warning("unknown_indicator", name=indicator_name)
            return {"signal": "unknown", "strength": 0.0, "bias": "NEUTRAL"}

        # Store for history
        self._last_values[symbol] = {
            "indicator": indicator_name,
            "values": values,
            "timestamp": datetime.now(timezone.utc),
        }

        return adapter.interpret(**values)

    def recommend_sl_tp(
        self, symbol: str, timeframe: str,
        entry: float, direction: Direction,
        indicator_name: Optional[str] = None,
        **indicator_values,
    ) -> dict:
        """
        Recommend stop-loss and take-profit levels based on indicator data.
        If no indicator provided, uses defaults based on price.
        """
        if indicator_name:
            adapter = self.get_adapter(indicator_name)
            if adapter:
                return adapter.recommend_sl_tp(entry, direction=direction, **indicator_values)

        # Smart defaults based on timeframe
        tf_factors = {"1m": 0.5, "5m": 0.7, "15m": 1.0, "1h": 1.2, "4h": 1.5, "1d": 2.0}
        factor = tf_factors.get(timeframe, 1.0)
        sl_pct = 0.01 * factor
        tp_pct = 0.025 * factor

        if direction == Direction.LONG:
            return {
                "stop_loss": round(entry * (1 - sl_pct), 2),
                "take_profit": round(entry * (1 + tp_pct), 2),
                "take_profit_2": round(entry * (1 + tp_pct * 2), 2),
            }
        return {
            "stop_loss": round(entry * (1 + sl_pct), 2),
            "take_profit": round(entry * (1 - tp_pct), 2),
            "take_profit_2": round(entry * (1 - tp_pct * 2), 2),
        }

    def get_pinescript_template(self, indicator_name: str) -> Optional[dict]:
        """Get PineScript template for a given indicator."""
        name = indicator_name.lower().replace(" ", "_")
        return self.PINESCRIPT_PARAMS.get(name)

    def list_indicators(self) -> List[dict]:
        """List all supported indicators with metadata."""
        return [
            {"name": name, **params}
            for name, params in self.PINESCRIPT_PARAMS.items()
        ]
