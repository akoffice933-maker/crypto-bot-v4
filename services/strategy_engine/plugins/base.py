"""
Crypto Bot v4.5 — Strategy Plugin Base

To add a new strategy, create a file in plugins/ and subclass BaseStrategy.
Strategies are auto-discovered and registered in StrategyEngine.

Example:

    # plugins/my_strategy.py
    from .base import BaseStrategy, StrategyConfig, SignalResult

    class MyStrategy(BaseStrategy):
        name = "my_strategy"
        config = StrategyConfig(wick_ratio=1.5, volume_multiplier=1.2, min_rr=2.0)

        def detect(self, features, candles, regime) -> Optional[SignalResult]:
            ...
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from core.models import Direction, Features, MarketRegime, OHLCV, StrategyType


@dataclass
class StrategyConfig:
    """Configuration for a strategy plugin."""
    enabled: bool = True
    wick_ratio: float = 1.8
    volume_multiplier: float = 1.25
    tolerance: float = 0.0018
    min_rr: float = 2.0
    sl_atr_mult: float = 1.5
    tp_min: float = 0.02
    tp_max: float = 0.04
    extra: dict = field(default_factory=dict)


@dataclass
class SignalResult:
    """Result from strategy detection."""
    direction: Direction
    entry_market: float
    entry_limit: float
    stop_loss: float
    tp1: float
    tp2: float
    confidence: float
    factors: List[Dict] = field(default_factory=list)


class BaseStrategy(ABC):
    """
    Abstract base for trading strategy plugins.

    Subclass and implement `detect()`. The strategy engine auto-discovers
    all BaseStrategy subclasses in the plugins/ directory.

    Attributes:
        name: Unique strategy identifier (must match class name convention)
        strategy_type: Maps to bot's StrategyType enum
        config: Default parameters (overridable per-instance)
    """

    name: str = ""
    strategy_type: StrategyType = StrategyType.SWEEP
    config: StrategyConfig = StrategyConfig()

    def __init__(self, **overrides):
        """Initialize with optional parameter overrides."""
        if overrides:
            for key, value in overrides.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

    @abstractmethod
    def detect(
        self,
        features: Features,
        candles: List[OHLCV],
        regime: MarketRegime,
    ) -> Optional[SignalResult]:
        """
        Detect a trading signal.

        Args:
            features: Computed technical features
            candles: Recent OHLCV candles
            regime: Current market regime with strategy weights

        Returns:
            SignalResult if a valid signal is found, None otherwise.
        """
        ...

    def calculate_confidence(
        self,
        trend_match: float,
        volume_spike: float,
        structure_quality: float,
        liquidity_depth: float,
        session_score: float,
    ) -> float:
        """Standard confidence calculation used by all strategies."""
        return max(0.0, min(1.0, (
            trend_match * 0.25 +
            volume_spike * 0.20 +
            structure_quality * 0.15 +
            liquidity_depth * 0.20 +
            session_score * 0.20
        )))
