"""
Crypto Bot v4.4 — Regime Detector
Detects market regime (trend/range × high/low volatility + breakout)
and produces strategy weight allocations.
"""

import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import structlog

from core.models import Features, MarketRegime, Regime, StrategyType

logger = structlog.get_logger(__name__)


def sigmoid(x: float) -> float:
    """Sigmoid activation function."""
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def gaussian(x: float, mean: float, sigma: float) -> float:
    """Gaussian (normal) function normalized to [0, 1]."""
    if sigma == 0:
        return 1.0 if x == mean else 0.0
    exponent = -0.5 * ((x - mean) / sigma) ** 2
    return math.exp(exponent)


class RegimeDetector:
    """
    Market regime detection.
    Supports rule-based detection with optional ML interface.

    Regimes:
      - Trend High Vol: ADX > 25, ATR_percentile > 80
      - Trend Low Vol: ADX > 25, ATR_percentile < 20
      - Range High Vol: ADX < 25, ATR_percentile > 80
      - Range Low Vol: ADX < 25, ATR_percentile < 20
      - Breakout: Squeeze active + breakout conditions
    """

    # Regime → strategy weight matrix
    STRATEGY_WEIGHTS: Dict[Regime, Dict[StrategyType, float]] = {
        Regime.TREND_HIGH_VOL: {
            StrategyType.BOUNCE: 0.2,
            StrategyType.SWEEP: 0.6,
            StrategyType.BREAKOUT: 0.2,
        },
        Regime.TREND_LOW_VOL: {
            StrategyType.BOUNCE: 0.3,
            StrategyType.SWEEP: 0.5,
            StrategyType.BREAKOUT: 0.2,
        },
        Regime.RANGE_HIGH_VOL: {
            StrategyType.BOUNCE: 0.5,
            StrategyType.SWEEP: 0.3,
            StrategyType.BREAKOUT: 0.2,
        },
        Regime.RANGE_LOW_VOL: {
            StrategyType.BOUNCE: 0.6,
            StrategyType.SWEEP: 0.3,
            StrategyType.BREAKOUT: 0.1,
        },
        Regime.BREAKOUT: {
            StrategyType.BOUNCE: 0.1,
            StrategyType.SWEEP: 0.2,
            StrategyType.BREAKOUT: 0.7,
        },
    }

    def __init__(
        self,
        adx_threshold: float = 25.0,
        atr_percentiles: Tuple[float, float] = (20.0, 80.0),
    ):
        self.adx_threshold = adx_threshold
        self.atr_low, self.atr_high = atr_percentiles
        self._last_regime: Optional[MarketRegime] = None

    def detect(
        self, features: Features, current_price: Optional[float] = None
    ) -> MarketRegime:
        """
        Detect the current market regime from computed features.

        Args:
            features: Computed Features dataclass
            current_price: Current price for breakout detection

        Returns:
            MarketRegime with strategy weights
        """
        adx = features.adx_14
        atr_perc = features.atr_percentile
        squeeze = features.squeeze_active

        # ------- Rule-based classification -------
        is_trend = adx > self.adx_threshold
        is_range = adx <= self.adx_threshold
        is_high_vol = atr_perc > self.atr_high
        is_low_vol = atr_perc < self.atr_low
        is_mid_vol = not is_high_vol and not is_low_vol

        if squeeze:
            regime = Regime.BREAKOUT
        elif is_trend and is_high_vol:
            regime = Regime.TREND_HIGH_VOL
        elif is_trend and is_low_vol:
            regime = Regime.TREND_LOW_VOL
        elif is_range and is_high_vol:
            regime = Regime.RANGE_HIGH_VOL
        elif is_range and is_low_vol:
            regime = Regime.RANGE_LOW_VOL
        elif is_mid_vol:
            # Default to trend or range based on ADX proximity
            if adx > self.adx_threshold:
                regime = Regime.TREND_LOW_VOL
            else:
                regime = Regime.RANGE_LOW_VOL
        else:
            regime = Regime.RANGE_LOW_VOL  # fallback

        # ------- Smooth weights via sigmoid/gaussian -------
        bounce_weight = sigmoid((self.adx_threshold - adx) / 5.0)
        sweep_weight = gaussian(adx, mean=30.0, sigma=10.0)
        breakout_weight = sigmoid((adx - 40.0) / 5.0)

        # Normalize smooth weights
        total = bounce_weight + sweep_weight + breakout_weight
        if total > 0:
            smooth_weights = {
                StrategyType.BOUNCE: bounce_weight / total,
                StrategyType.SWEEP: sweep_weight / total,
                StrategyType.BREAKOUT: breakout_weight / total,
            }
        else:
            smooth_weights = {
                StrategyType.BOUNCE: 1.0 / 3,
                StrategyType.SWEEP: 1.0 / 3,
                StrategyType.BREAKOUT: 1.0 / 3,
            }

        # Blend matrix weights with smooth weights (50/50)
        matrix_w = self.STRATEGY_WEIGHTS[regime]
        blended = {}
        for st in StrategyType:
            blended[st] = 0.5 * matrix_w[st] + 0.5 * smooth_weights[st]

        # Confidence in regime detection
        # Higher when ADX/ATR signals are clear
        adx_confidence = min(1.0, max(0.0, abs(adx - self.adx_threshold) / 20.0))
        vol_confidence = min(1.0, max(0.0, abs(atr_perc - 50.0) / 50.0))
        regime_confidence = 0.5 * adx_confidence + 0.5 * vol_confidence

        result = MarketRegime(
            regime=regime,
            confidence=round(regime_confidence, 4),
            adx=adx,
            atr_percentile=atr_perc,
            strategy_weights=blended,
            timestamp=datetime.now(timezone.utc),
        )

        self._last_regime = result
        logger.debug("regime_detected", regime=regime.value, confidence=regime_confidence)
        return result

    def predict(self, features: dict) -> str:
        """
        ML-compatible interface. Accepts a dict of features and returns regime name.
        Can be swapped for a trained ML model implementing the same interface.
        """
        if isinstance(features, Features):
            result = self.detect(features)
        else:
            # Convert dict to minimal Features
            f = Features(
                timestamp=datetime.now(timezone.utc),
                pair=features.get("pair", ""),
                timeframe=features.get("timeframe", "1h"),
                adx_14=features.get("adx", features.get("adx_14", 0)),
                atr_percentile=features.get("atr_percentile", 50),
                squeeze_active=features.get("squeeze_active", False),
            )
            result = self.detect(f)

        return result.regime.value

    @property
    def last_regime(self) -> Optional[MarketRegime]:
        return self._last_regime

    def get_strategy_weight(self, strategy: StrategyType) -> float:
        """Get the current weight for a given strategy type."""
        if self._last_regime:
            return self._last_regime.strategy_weights.get(strategy, 0.0)
        return 0.0
