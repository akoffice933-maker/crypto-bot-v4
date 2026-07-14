"""
Liquidity Bounce strategy plugin.

Detects: price touches a level without breaking and bounces off with volume.
"""

from typing import Optional

from core.models import Direction, Features, MarketRegime, OHLCV, Regime
from services.strategy_engine.plugins.base import BaseStrategy, SignalResult, StrategyConfig


class BounceStrategy(BaseStrategy):
    """Liquidity Bounce: touch + bounce + volume = entry."""

    name = "bounce"
    strategy_type = Regime.RANGE_LOW_VOL  # type: ignore[assignment]
    config = StrategyConfig(wick_ratio=1.5, volume_multiplier=1.10, tolerance=0.0018, min_rr=1.5)

    def detect(self, features, candles, regime) -> Optional[SignalResult]:
        cfg = self.config
        levels_above = features.liquidity_levels_above
        levels_below = features.liquidity_levels_below

        if len(candles) < 3:
            return None

        last = candles[-1]
        prev = candles[-2]
        current_price = last.close
        wick_ratio = features.wick_ratio
        volume_ratio = features.volume_ratio

        # LONG Bounce
        for level in levels_below:
            if (current_price - level) / current_price > cfg.tolerance * 2:
                continue
            touched = prev.low <= level * (1 + cfg.tolerance) and prev.low >= level * (1 - cfg.tolerance)
            bounced = last.close > last.open and last.close > prev.close
            good_wick = cfg.wick_ratio <= wick_ratio <= cfg.wick_ratio + 0.5
            good_vol = volume_ratio >= cfg.volume_multiplier

            if touched and bounced and good_wick and good_vol:
                entry = current_price
                stop = level * (1 - cfg.tolerance * 1.5)
                risk = entry - stop
                tp1 = entry + risk * cfg.min_rr
                tp2 = entry + risk * (cfg.min_rr + 0.5)

                for res in levels_above:
                    if res < tp2 and res > entry:
                        tp2 = res * 0.995
                        break

                conf = self.calculate_confidence(
                    trend_match=1.0 if regime.regime in (Regime.RANGE_HIGH_VOL, Regime.RANGE_LOW_VOL) else 0.5,
                    volume_spike=min(1.0, volume_ratio / cfg.volume_multiplier),
                    structure_quality=min(1.0, (wick_ratio - cfg.wick_ratio) / 0.5),
                    liquidity_depth=len(levels_below) / 5.0,
                    session_score=0.8,
                )
                if conf >= 0.5:
                    return SignalResult(
                        direction=Direction.LONG, entry_market=entry,
                        entry_limit=level * 1.001, stop_loss=stop,
                        tp1=tp1, tp2=tp2, confidence=round(conf, 4),
                        factors=[{"type": "bounce_long", "level": level}],
                    )

        # SHORT Bounce
        for level in levels_above:
            if (level - current_price) / current_price > cfg.tolerance * 2:
                continue
            touched = prev.high >= level * (1 - cfg.tolerance) and prev.high <= level * (1 + cfg.tolerance)
            bounced = last.close < last.open and last.close < prev.close
            good_wick = cfg.wick_ratio <= wick_ratio <= cfg.wick_ratio + 0.5
            good_vol = volume_ratio >= cfg.volume_multiplier

            if touched and bounced and good_wick and good_vol:
                entry = current_price
                stop = level * (1 + cfg.tolerance * 1.5)
                risk = stop - entry
                tp1 = entry - risk * cfg.min_rr
                tp2 = entry - risk * (cfg.min_rr + 0.5)

                for sup in levels_below:
                    if sup > tp2 and sup < entry:
                        tp2 = sup * 1.005
                        break

                conf = self.calculate_confidence(
                    trend_match=1.0 if regime.regime in (Regime.RANGE_HIGH_VOL, Regime.RANGE_LOW_VOL) else 0.5,
                    volume_spike=min(1.0, volume_ratio / cfg.volume_multiplier),
                    structure_quality=min(1.0, (wick_ratio - cfg.wick_ratio) / 0.5),
                    liquidity_depth=len(levels_above) / 5.0,
                    session_score=0.8,
                )
                if conf >= 0.5:
                    return SignalResult(
                        direction=Direction.SHORT, entry_market=entry,
                        entry_limit=level * 0.999, stop_loss=stop,
                        tp1=tp1, tp2=tp2, confidence=round(conf, 4),
                        factors=[{"type": "bounce_short", "level": level}],
                    )

        return None
