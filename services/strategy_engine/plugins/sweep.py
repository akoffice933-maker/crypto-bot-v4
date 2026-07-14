"""
Liquidity Sweep strategy plugin.

Detects: price breaks a liquidity level, wicks through, and reclaims.
"""

from typing import List, Optional

from core.models import Direction, Features, MarketRegime, OHLCV, Regime
from services.strategy_engine.plugins.base import BaseStrategy, SignalResult, StrategyConfig


class SweepStrategy(BaseStrategy):
    """Liquidity Sweep: break + wick + reclaim = entry."""

    name = "sweep"
    strategy_type = Regime.TREND_HIGH_VOL  # type: ignore[assignment]
    config = StrategyConfig(wick_ratio=1.8, volume_multiplier=1.25, tolerance=0.0018, min_rr=2.0)

    def detect(
        self, features, candles, regime
    ) -> Optional[SignalResult]:
        cfg = self.config
        levels_above = features.liquidity_levels_above
        levels_below = features.liquidity_levels_below

        if len(candles) < 5:
            return None

        last = candles[-1]
        prev = candles[-2]
        current_price = last.close
        wick_ratio = features.wick_ratio
        volume_ratio = features.volume_ratio

        # LONG Sweep
        for level in levels_below:
            if abs(current_price - level) / current_price > cfg.tolerance * 3:
                continue
            good_wick = cfg.wick_ratio <= wick_ratio <= cfg.wick_ratio + 0.7
            good_vol = volume_ratio >= cfg.volume_multiplier
            prev_below = prev.low < level * (1 - cfg.tolerance)
            close_above = last.close > level

            if prev_below and close_above and good_wick and good_vol:
                entry = current_price
                stop = level * (1 - cfg.tolerance * 2)
                risk = entry - stop
                tp1 = entry + risk * cfg.min_rr
                tp2 = entry + risk * (cfg.min_rr + 1.0)

                for res in levels_above:
                    if res < tp2 and res > entry:
                        tp2 = res * 0.995
                        break

                conf = self.calculate_confidence(
                    trend_match=1.0 if regime.regime in (Regime.TREND_HIGH_VOL, Regime.TREND_LOW_VOL) else 0.5,
                    volume_spike=min(1.0, volume_ratio / cfg.volume_multiplier),
                    structure_quality=min(1.0, (wick_ratio - cfg.wick_ratio) / 1.0),
                    liquidity_depth=len(levels_below) / 5.0,
                    session_score=0.7,
                )
                if conf >= 0.5:
                    return SignalResult(
                        direction=Direction.LONG, entry_market=entry,
                        entry_limit=level * 1.0005, stop_loss=stop,
                        tp1=tp1, tp2=tp2, confidence=round(conf, 4),
                        factors=[{"type": "sweep_long", "level": level}],
                    )

        # SHORT Sweep
        for level in levels_above:
            if abs(current_price - level) / current_price > cfg.tolerance * 3:
                continue
            good_wick = cfg.wick_ratio <= wick_ratio <= cfg.wick_ratio + 0.7
            good_vol = volume_ratio >= cfg.volume_multiplier
            prev_above = prev.high > level * (1 + cfg.tolerance)
            close_below = last.close < level

            if prev_above and close_below and good_wick and good_vol:
                entry = current_price
                stop = level * (1 + cfg.tolerance * 2)
                risk = stop - entry
                tp1 = entry - risk * cfg.min_rr
                tp2 = entry - risk * (cfg.min_rr + 1.0)

                for sup in levels_below:
                    if sup > tp2 and sup < entry:
                        tp2 = sup * 1.005
                        break

                conf = self.calculate_confidence(
                    trend_match=1.0 if regime.regime in (Regime.TREND_HIGH_VOL, Regime.TREND_LOW_VOL) else 0.5,
                    volume_spike=min(1.0, volume_ratio / cfg.volume_multiplier),
                    structure_quality=min(1.0, (wick_ratio - cfg.wick_ratio) / 1.0),
                    liquidity_depth=len(levels_above) / 5.0,
                    session_score=0.7,
                )
                if conf >= 0.5:
                    return SignalResult(
                        direction=Direction.SHORT, entry_market=entry,
                        entry_limit=level * 0.9995, stop_loss=stop,
                        tp1=tp1, tp2=tp2, confidence=round(conf, 4),
                        factors=[{"type": "sweep_short", "level": level}],
                    )

        return None
