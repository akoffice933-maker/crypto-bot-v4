"""
Volatility Breakout strategy plugin.

Detects: squeeze resolves with volume expansion = momentum entry.
"""

from typing import Optional

from core.models import Direction, Features, MarketRegime, OHLCV, Regime
from services.strategy_engine.plugins.base import BaseStrategy, SignalResult, StrategyConfig


class BreakoutStrategy(BaseStrategy):
    """Volatility Breakout: squeeze + volume + direction = entry."""

    name = "breakout"
    strategy_type = Regime.BREAKOUT  # type: ignore[assignment]
    config = StrategyConfig(sl_atr_mult=1.5, tp_min=0.02, tp_max=0.04)

    def detect(self, features, candles, regime) -> Optional[SignalResult]:
        cfg = self.config

        if not features.squeeze_active:
            return None
        if len(candles) < 5:
            return None

        last = candles[-1]
        current_price = last.close
        volume_ratio = features.volume_ratio

        if volume_ratio < 1.25:
            return None

        if current_price > features.bb_upper:
            direction = Direction.LONG
        elif current_price < features.bb_lower:
            direction = Direction.SHORT
        else:
            return None

        atr = features.atr_pct_14 / 100 * current_price
        sl_distance = atr * cfg.sl_atr_mult

        if direction == Direction.LONG:
            entry = current_price
            stop = entry - sl_distance
            tp1 = entry * (1 + cfg.tp_min)
            tp2 = entry * (1 + min(cfg.tp_max, cfg.tp_min * 2))
        else:
            entry = current_price
            stop = entry + sl_distance
            tp1 = entry * (1 - cfg.tp_min)
            tp2 = entry * (1 - min(cfg.tp_max, cfg.tp_min * 2))

        conf = self.calculate_confidence(
            trend_match=1.0 if regime.regime == Regime.BREAKOUT else 0.6,
            volume_spike=min(1.0, volume_ratio / 2.0),
            structure_quality=0.8 if features.squeeze_active else 0.3,
            liquidity_depth=0.5,
            session_score=0.6,
        )
        if conf >= 0.5:
            return SignalResult(
                direction=direction, entry_market=entry,
                entry_limit=entry, stop_loss=stop,
                tp1=tp1, tp2=tp2, confidence=round(conf, 4),
                factors=[{"type": "breakout", "squeeze": True}],
            )

        return None
