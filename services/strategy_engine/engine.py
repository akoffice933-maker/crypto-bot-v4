"""
Crypto Bot v4.4 — Strategy Engine
Generates trading signals for Sweep, Bounce, and Breakout strategies.

Signal Structure:
  pair, direction (LONG/SHORT), entry_market, entry_limit,
  stop_loss, tp1, tp2, strategy, confidence, regime, factors, timestamp
"""

import math
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import structlog

from core.models import (
    Direction, Features, MarketRegime, OHLCV, Regime,
    Signal, StrategyType,
)

logger = structlog.get_logger(__name__)


class StrategyEngine:
    """
    Generates trading signals from features and market data.
    Implements three strategies: Liquidity Sweep, Liquidity Bounce, Volatility Breakout.
    """

    # Strategy default parameters
    SWEEP_CONFIG = {
        "wick_ratio_min": 1.8,
        "wick_ratio_max": 2.5,
        "volume_multiplier": 1.25,
        "tolerance": 0.0018,
        "min_rr": 2.0,
    }

    BOUNCE_CONFIG = {
        "wick_ratio_min": 1.5,
        "wick_ratio_max": 2.0,
        "volume_multiplier": 1.10,
        "tolerance": 0.0018,
        "min_rr": 1.5,
    }

    BREAKOUT_CONFIG = {
        "sl_atr_mult": 1.5,
        "tp_min": 0.02,   # 2% minimum take profit
        "tp_max": 0.04,   # 4% maximum take profit
    }

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize with optional config overrides.

        Args:
            config: Dict with keys 'sweep', 'bounce', 'breakout' containing param overrides.
        """
        if config:
            if "sweep" in config:
                self.SWEEP_CONFIG.update(config["sweep"])
            if "bounce" in config:
                self.BOUNCE_CONFIG.update(config["bounce"])
            if "breakout" in config:
                self.BREAKOUT_CONFIG.update(config["breakout"])

        self._last_signals: List[Signal] = []

    def generate_signals(
        self,
        features: Features,
        regime: MarketRegime,
        candles: List[OHLCV],
        pair: str,
    ) -> List[Signal]:
        """
        Generate all trading signals for a given pair.

        Args:
            features: Computed technical features
            regime: Current market regime
            candles: Recent OHLCV candles
            pair: Trading pair symbol

        Returns:
            List of valid Signal objects sorted by confidence descending.
        """
        signals = []
        current_price = candles[-1].close if candles else 0

        if current_price <= 0:
            return signals

        # Generate signals for each strategy
        sweep_signal = self._detect_sweep(features, candles, pair, regime)
        if sweep_signal:
            signals.append(sweep_signal)

        bounce_signal = self._detect_bounce(features, candles, pair, regime)
        if bounce_signal:
            signals.append(bounce_signal)

        breakout_signal = self._detect_breakout(features, candles, pair, regime)
        if breakout_signal:
            signals.append(breakout_signal)

        # Sort by confidence * strategy_weight desc
        signals.sort(key=lambda s: s.confidence * regime.strategy_weights.get(s.strategy, 0), reverse=True)

        self._last_signals = signals
        return signals

    def _detect_sweep(
        self, features: Features, candles: List[OHLCV], pair: str, regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Liquidity Sweep: price breaks a level, returns back through it with a wick + volume.
        Entry when price reclaims the level after the sweep.
        """
        cfg = self.SWEEP_CONFIG
        levels_above = features.liquidity_levels_above
        levels_below = features.liquidity_levels_below

        if len(candles) < 5:
            return None

        last = candles[-1]
        prev = candles[-2]
        current_price = last.close
        wick_ratio = features.wick_ratio
        volume_ratio = features.volume_ratio

        # ---- LONG Sweep ----
        for level in levels_below:
            level_distance = abs(current_price - level) / current_price
            if level_distance > cfg["tolerance"] * 3:
                continue

            # Check for sweep pattern: price wicked below level and recovered
            prev_low_below = prev.low < level * (1 - cfg["tolerance"])
            current_close_above = last.close > level
            good_wick = cfg["wick_ratio_min"] <= wick_ratio <= cfg["wick_ratio_max"]
            good_volume = volume_ratio >= cfg["volume_multiplier"]

            if prev_low_below and current_close_above and good_wick and good_volume:
                entry = current_price
                stop = level * (1 - cfg["tolerance"] * 2)  # Below the swept level
                risk = entry - stop
                tp1 = entry + risk * cfg["min_rr"]
                tp2 = entry + risk * (cfg["min_rr"] + 1.0)

                # Check if levels above block TP
                for resistance in levels_above:
                    if resistance < tp2 and resistance > entry:
                        tp2 = resistance * 0.995  # Adjust to just below resistance
                        break

                confidence = self._calculate_confidence(
                    trend_match=1.0 if regime.regime in (Regime.TREND_HIGH_VOL, Regime.TREND_LOW_VOL) else 0.5,
                    volume_spike=min(1.0, volume_ratio / cfg["volume_multiplier"]),
                    structure_quality=min(1.0, (wick_ratio - cfg["wick_ratio_min"]) / 1.0),
                    liquidity_depth=len(levels_below) / 5.0,
                    session_score=0.7,  # Simplified
                )

                if confidence >= 0.5:
                    return Signal(
                        pair=pair,
                        direction=Direction.LONG,
                        entry_market=current_price,
                        entry_limit=level * 1.0005,  # Just above level
                        stop_loss=stop,
                        tp1=tp1,
                        tp2=tp2,
                        strategy=StrategyType.SWEEP,
                        confidence=round(confidence, 4),
                        regime=regime.regime.value,
                        factors=[{"type": "sweep_long", "level": level, "wick_ratio": wick_ratio}],
                        timestamp=datetime.utcnow(),
                    )

        # ---- SHORT Sweep ----
        for level in levels_above:
            level_distance = abs(current_price - level) / current_price
            if level_distance > cfg["tolerance"] * 3:
                continue

            prev_high_above = prev.high > level * (1 + cfg["tolerance"])
            current_close_below = last.close < level
            good_wick = cfg["wick_ratio_min"] <= wick_ratio <= cfg["wick_ratio_max"]
            good_volume = volume_ratio >= cfg["volume_multiplier"]

            if prev_high_above and current_close_below and good_wick and good_volume:
                entry = current_price
                stop = level * (1 + cfg["tolerance"] * 2)
                risk = stop - entry
                tp1 = entry - risk * cfg["min_rr"]
                tp2 = entry - risk * (cfg["min_rr"] + 1.0)

                for support in levels_below:
                    if support > tp2 and support < entry:
                        tp2 = support * 1.005
                        break

                confidence = self._calculate_confidence(
                    trend_match=1.0 if regime.regime in (Regime.TREND_HIGH_VOL, Regime.TREND_LOW_VOL) else 0.5,
                    volume_spike=min(1.0, volume_ratio / cfg["volume_multiplier"]),
                    structure_quality=min(1.0, (wick_ratio - cfg["wick_ratio_min"]) / 1.0),
                    liquidity_depth=len(levels_above) / 5.0,
                    session_score=0.7,
                )

                if confidence >= 0.5:
                    return Signal(
                        pair=pair,
                        direction=Direction.SHORT,
                        entry_market=current_price,
                        entry_limit=level * 0.9995,
                        stop_loss=stop,
                        tp1=tp1,
                        tp2=tp2,
                        strategy=StrategyType.SWEEP,
                        confidence=round(confidence, 4),
                        regime=regime.regime.value,
                        factors=[{"type": "sweep_short", "level": level, "wick_ratio": wick_ratio}],
                        timestamp=datetime.utcnow(),
                    )

        return None

    def _detect_bounce(
        self, features: Features, candles: List[OHLCV], pair: str, regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Liquidity Bounce: price touches a level without breaking it and bounces off.
        Entry on confirmation of the bounce.
        """
        cfg = self.BOUNCE_CONFIG
        levels_above = features.liquidity_levels_above
        levels_below = features.liquidity_levels_below

        if len(candles) < 3:
            return None

        last = candles[-1]
        prev = candles[-2]
        current_price = last.close
        wick_ratio = features.wick_ratio
        volume_ratio = features.volume_ratio

        # ---- LONG Bounce ----
        for level in levels_below:
            level_distance = (current_price - level) / current_price
            if level_distance > cfg["tolerance"] * 2:
                continue

            # Touched level from above, bounced up
            touched_level = prev.low <= level * (1 + cfg["tolerance"]) and prev.low >= level * (1 - cfg["tolerance"])
            bounced_up = last.close > last.open and last.close > prev.close
            good_wick = cfg["wick_ratio_min"] <= wick_ratio <= cfg["wick_ratio_max"]
            good_volume = volume_ratio >= cfg["volume_multiplier"]

            if touched_level and bounced_up and good_wick and good_volume:
                entry = current_price
                stop = level * (1 - cfg["tolerance"] * 1.5)
                risk = entry - stop
                tp1 = entry + risk * cfg["min_rr"]
                tp2 = entry + risk * (cfg["min_rr"] + 0.5)

                for resistance in levels_above:
                    if resistance < tp2 and resistance > entry:
                        tp2 = resistance * 0.995
                        break

                confidence = self._calculate_confidence(
                    trend_match=1.0 if regime.regime in (Regime.RANGE_HIGH_VOL, Regime.RANGE_LOW_VOL) else 0.5,
                    volume_spike=min(1.0, volume_ratio / cfg["volume_multiplier"]),
                    structure_quality=min(1.0, (wick_ratio - cfg["wick_ratio_min"]) / 0.5),
                    liquidity_depth=len(levels_below) / 5.0,
                    session_score=0.8,
                )

                if confidence >= 0.5:
                    return Signal(
                        pair=pair,
                        direction=Direction.LONG,
                        entry_market=current_price,
                        entry_limit=level * 1.001,
                        stop_loss=stop,
                        tp1=tp1,
                        tp2=tp2,
                        strategy=StrategyType.BOUNCE,
                        confidence=round(confidence, 4),
                        regime=regime.regime.value,
                        factors=[{"type": "bounce_long", "level": level, "wick_ratio": wick_ratio}],
                        timestamp=datetime.utcnow(),
                    )

        # ---- SHORT Bounce ----
        for level in levels_above:
            level_distance = (level - current_price) / current_price
            if level_distance > cfg["tolerance"] * 2:
                continue

            touched_level = prev.high >= level * (1 - cfg["tolerance"]) and prev.high <= level * (1 + cfg["tolerance"])
            bounced_down = last.close < last.open and last.close < prev.close
            good_wick = cfg["wick_ratio_min"] <= wick_ratio <= cfg["wick_ratio_max"]
            good_volume = volume_ratio >= cfg["volume_multiplier"]

            if touched_level and bounced_down and good_wick and good_volume:
                entry = current_price
                stop = level * (1 + cfg["tolerance"] * 1.5)
                risk = stop - entry
                tp1 = entry - risk * cfg["min_rr"]
                tp2 = entry - risk * (cfg["min_rr"] + 0.5)

                for support in levels_below:
                    if support > tp2 and support < entry:
                        tp2 = support * 1.005
                        break

                confidence = self._calculate_confidence(
                    trend_match=1.0 if regime.regime in (Regime.RANGE_HIGH_VOL, Regime.RANGE_LOW_VOL) else 0.5,
                    volume_spike=min(1.0, volume_ratio / cfg["volume_multiplier"]),
                    structure_quality=min(1.0, (wick_ratio - cfg["wick_ratio_min"]) / 0.5),
                    liquidity_depth=len(levels_above) / 5.0,
                    session_score=0.8,
                )

                if confidence >= 0.5:
                    return Signal(
                        pair=pair,
                        direction=Direction.SHORT,
                        entry_market=current_price,
                        entry_limit=level * 0.999,
                        stop_loss=stop,
                        tp1=tp1,
                        tp2=tp2,
                        strategy=StrategyType.BOUNCE,
                        confidence=round(confidence, 4),
                        regime=regime.regime.value,
                        factors=[{"type": "bounce_short", "level": level, "wick_ratio": wick_ratio}],
                        timestamp=datetime.utcnow(),
                    )

        return None

    def _detect_breakout(
        self, features: Features, candles: List[OHLCV], pair: str, regime: MarketRegime
    ) -> Optional[Signal]:
        """
        Volatility Breakout: price exits a squeeze with volume expansion.
        """
        cfg = self.BREAKOUT_CONFIG

        if not features.squeeze_active:
            return None

        if len(candles) < 5:
            return None

        last = candles[-1]
        current_price = last.close
        volume_ratio = features.volume_ratio

        # Need volume confirmation for breakout
        if volume_ratio < 1.25:
            return None

        # Determine direction from BB position
        if current_price > features.bb_upper:
            direction = Direction.LONG
        elif current_price < features.bb_lower:
            direction = Direction.SHORT
        else:
            return None

        atr = features.atr_pct_14 / 100 * current_price  # Convert ATR% to absolute
        sl_distance = atr * cfg["sl_atr_mult"]

        if direction == Direction.LONG:
            entry = current_price
            stop = entry - sl_distance
            tp1 = entry + entry * cfg["tp_min"]
            tp2 = entry + entry * min(cfg["tp_max"], cfg["tp_min"] * 2)
        else:
            entry = current_price
            stop = entry + sl_distance
            tp1 = entry - entry * cfg["tp_min"]
            tp2 = entry - entry * min(cfg["tp_max"], cfg["tp_min"] * 2)

        confidence = self._calculate_confidence(
            trend_match=1.0 if regime.regime == Regime.BREAKOUT else 0.6,
            volume_spike=min(1.0, volume_ratio / 2.0),
            structure_quality=0.8 if features.squeeze_active else 0.3,
            liquidity_depth=0.5,
            session_score=0.6,
        )

        if confidence >= 0.5:
            return Signal(
                pair=pair,
                direction=direction,
                entry_market=current_price,
                entry_limit=current_price,  # Breakout uses market entry
                stop_loss=stop,
                tp1=tp1,
                tp2=tp2,
                strategy=StrategyType.BREAKOUT,
                confidence=round(confidence, 4),
                regime=regime.regime.value,
                factors=[{"type": "breakout", "squeeze": True, "volume_ratio": volume_ratio}],
                timestamp=datetime.utcnow(),
            )

        return None

    def _calculate_confidence(
        self,
        trend_match: float,
        volume_spike: float,
        structure_quality: float,
        liquidity_depth: float,
        session_score: float,
    ) -> float:
        """
        Calculate calibrated signal confidence using weighted factors.

        CONFIDENCE = trend_match*0.25 + volume_spike*0.20 +
                     structure_quality*0.15 + liquidity_depth*0.20 +
                     session_score*0.20

        Target: confidence should approximate actual winrate.
        """
        confidence = (
            trend_match * 0.25 +
            volume_spike * 0.20 +
            structure_quality * 0.15 +
            liquidity_depth * 0.20 +
            session_score * 0.20
        )
        return max(0.0, min(1.0, confidence))

    @property
    def last_signals(self) -> List[Signal]:
        return self._last_signals
