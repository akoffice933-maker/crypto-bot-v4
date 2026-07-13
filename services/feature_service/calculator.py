"""
Crypto Bot v4.4 — Feature Service
Calculates technical features: ADX, ATR%, Bollinger Bands, Volume MA,
Liquidity Levels, CVD, Squeeze detection.

Performance target: <100ms for 4 pairs across all timeframes.
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from core.models import Features, OHLCV

logger = structlog.get_logger(__name__)


class FeatureCalculator:
    """
    Computes all technical features required by the trading system.
    Uses vectorized NumPy operations for performance.
    """

    def __init__(self, pairs: List[str], timeframes: List[str]):
        self.pairs = pairs
        self.timeframes = timeframes
        self._feature_cache: Dict[str, Features] = {}  # key: pair:tf:ts

    @staticmethod
    def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        """Compute ADX (Average Directional Index)."""
        n = len(close)
        if n < period + 1:
            return 0.0

        # True Range
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )
        atr = np.zeros(n - 1)
        atr[period - 1] = tr[:period].mean()
        for i in range(period, n - 1):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        # Directional Movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)

        plus_di = np.zeros(n - 1)
        minus_di = np.zeros(n - 1)
        valid = atr > 0

        # Smoothed +DI / -DI
        for i in range(period, n - 1):
            plus_di[i] = (plus_di[i - 1] * (period - 1) + (plus_dm[i] / atr[i] if valid[i] else 0) * 100) / period
            minus_di[i] = (minus_di[i - 1] * (period - 1) + (minus_dm[i] / atr[i] if valid[i] else 0) * 100) / period

        # ADX
        dx = np.zeros(n - 1)
        sum_di = plus_di + minus_di
        mask = sum_di > 0
        dx[mask] = np.abs(plus_di[mask] - minus_di[mask]) / sum_di[mask] * 100

        adx = np.zeros(n - 1)
        adx[period - 1] = dx[:period].mean()
        for i in range(period, n - 1):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return float(adx[-1]) if adx[-1] > 0 else 0.0

    @staticmethod
    def compute_atr_pct(
        high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14
    ) -> Tuple[float, float, float]:
        """Compute ATR as percentage of price, its percentile, and raw ATR."""
        n = len(close)
        if n < period + 1:
            return 0.0, 0.0, 0.0

        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )
        atr = np.zeros(n - 1)
        atr[period - 1] = tr[:period].mean()
        for i in range(period, n - 1):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

        current_atr = atr[-1]
        current_close = close[-1]
        atr_pct = (current_atr / current_close * 100) if current_close > 0 else 0.0

        # Percentile of current ATR% in historical ATR% values
        atr_pct_series = np.zeros_like(atr)
        valid_mask = close[1:] > 0
        atr_pct_series[valid_mask] = atr[valid_mask] / close[1:][valid_mask] * 100
        percentile = float(np.percentile(atr_pct_series[atr_pct_series > 0], 80))

        return atr_pct, percentile, current_atr

    @staticmethod
    def compute_bollinger_bands(
        close: np.ndarray, period: int = 20, std_mult: float = 2.0
    ) -> Tuple[float, float, float, float, bool]:
        """Compute Bollinger Bands and Squeeze detection."""
        n = len(close)
        if n < period:
            return 0.0, 0.0, 0.0, 0.0, False

        close_series = close[-period:]
        middle = float(close_series.mean())
        std = float(close_series.std())
        upper = middle + std_mult * std
        lower = middle - std_mult * std
        width = (upper - lower) / middle * 100 if middle > 0 else 0.0

        # Squeeze detection: BB inside Keltner Channels (simplified)
        # Keltner Channel uses ATR
        typical = (close[-period:] + close[-period:] + close[-period:]) / 3  # simplified
        kc_width = std * 1.5  # approximation
        squeeze = width < kc_width

        return upper, lower, middle, width, squeeze

    @staticmethod
    def compute_volume_ma(volume: np.ndarray, periods: List[int] = None) -> Dict[int, float]:
        """Compute volume moving averages."""
        if periods is None:
            periods = [20, 50]
        result = {}
        for period in periods:
            if len(volume) >= period:
                result[period] = float(volume[-period:].mean())
            else:
                result[period] = float(volume.mean()) if len(volume) > 0 else 0.0
        return result

    @staticmethod
    def compute_volume_ratio(volume: np.ndarray, period: int = 20) -> float:
        """Compute current volume relative to its moving average."""
        if len(volume) < period:
            return 1.0
        ma = volume[-period:].mean()
        if ma == 0:
            return 1.0
        return float(volume[-1] / ma)

    @staticmethod
    def find_liquidity_levels(
        high: np.ndarray, low: np.ndarray, lookback: int = 50
    ) -> Tuple[List[float], List[float]]:
        """
        Find equal highs (resistance) and equal lows (support) — liquidity levels.
        Uses a simple swing-point detection approach.
        """
        n = len(high)
        if n < lookback:
            lookback = n

        recent_high = high[-lookback:]
        recent_low = low[-lookback:]

        # Find local maxima (resistance)
        resistance_levels = []
        for i in range(1, len(recent_high) - 1):
            if recent_high[i] >= recent_high[i - 1] and recent_high[i] >= recent_high[i + 1]:
                resistance_levels.append(float(recent_high[i]))

        # Find local minima (support)
        support_levels = []
        for i in range(1, len(recent_low) - 1):
            if recent_low[i] <= recent_low[i - 1] and recent_low[i] <= recent_low[i + 1]:
                support_levels.append(float(recent_low[i]))

        # Cluster nearby levels (within 0.5%)
        def cluster_levels(levels: List[float], tolerance_pct: float = 0.005) -> List[float]:
            if not levels:
                return []
            sorted_levels = sorted(levels)
            clusters = []
            current_cluster = [sorted_levels[0]]
            for lvl in sorted_levels[1:]:
                if (lvl - current_cluster[-1]) / current_cluster[-1] < tolerance_pct:
                    current_cluster.append(lvl)
                else:
                    clusters.append(sum(current_cluster) / len(current_cluster))
                    current_cluster = [lvl]
            clusters.append(sum(current_cluster) / len(current_cluster))
            return sorted(clusters)

        return cluster_levels(resistance_levels), cluster_levels(support_levels)

    @staticmethod
    def compute_cvd(
        close: np.ndarray, volume: np.ndarray, lookback: int = 50
    ) -> Tuple[float, float]:
        """
        Approximate Cumulative Volume Delta.
        Uses close-to-close direction as a proxy for buy/sell volume split.
        """
        n = len(close)
        if n < 2:
            return 0.0, 0.0

        # Estimate delta: if close > previous close, volume is "buy"; if lower, "sell"
        deltas = []
        for i in range(max(1, n - lookback), n):
            if close[i] > close[i - 1]:
                deltas.append(volume[i] if i < len(volume) else 0)
            else:
                deltas.append(-volume[i] if i < len(volume) else 0)

        cvd = float(sum(deltas)) if deltas else 0.0
        # CVD divergence: compare recent CVD to older
        mid = len(deltas) // 2
        recent_cvd = sum(deltas[mid:]) if mid < len(deltas) else 0.0
        older_cvd = sum(deltas[:mid]) if mid > 0 else 0.0

        divergence = recent_cvd - older_cvd
        return cvd, divergence

    @staticmethod
    def compute_wick_ratio(open_p: float, high: float, low: float, close: float) -> float:
        """Compute the wick-to-body ratio for a candle."""
        body = abs(close - open_p)
        upper_wick = high - max(open_p, close)
        lower_wick = min(open_p, close) - low

        if body == 0:
            return max(upper_wick, lower_wick) / 0.0001 if max(upper_wick, lower_wick) > 0 else 1.0

        # Return the larger wick ratio
        return max(upper_wick, lower_wick) / body

    def compute_all_features(
        self, candles: List[OHLCV], pair: str, timeframe: str
    ) -> Features:
        """
        Compute all features for a given set of candles.
        Returns a Features dataclass.
        """
        start_time = time.perf_counter()

        if not candles:
            return Features(timestamp=datetime.utcnow(), pair=pair, timeframe=timeframe)

        # Convert to numpy arrays
        high = np.array([c.high for c in candles])
        low = np.array([c.low for c in candles])
        close = np.array([c.close for c in candles])
        open_arr = np.array([c.open for c in candles])
        volume = np.array([c.volume for c in candles])
        last_candle = candles[-1]

        features = Features(
            timestamp=last_candle.timestamp,
            pair=pair,
            timeframe=timeframe,
        )

        # ADX
        features.adx_14 = self.compute_adx(high, low, close, period=14)
        features.adx_21 = self.compute_adx(high, low, close, period=21)

        # ATR%
        atr_pct_14, _, _ = self.compute_atr_pct(high, low, close, period=14)
        atr_pct_21, atr_percentile, _ = self.compute_atr_pct(high, low, close, period=21)
        features.atr_pct_14 = atr_pct_14
        features.atr_pct_21 = atr_pct_21
        features.atr_percentile = atr_percentile

        # Bollinger Bands
        bb_upper, bb_lower, bb_middle, bb_width, squeeze = self.compute_bollinger_bands(close)
        features.bb_upper = bb_upper
        features.bb_lower = bb_lower
        features.bb_middle = bb_middle
        features.bb_width = bb_width
        features.squeeze_active = squeeze

        # Volume MAs
        vol_mas = self.compute_volume_ma(volume, [20, 50])
        features.volume_ma_20 = vol_mas.get(20, 0.0)
        features.volume_ma_50 = vol_mas.get(50, 0.0)
        features.volume_ratio = self.compute_volume_ratio(volume, 20)

        # Liquidity Levels
        resistance, support = self.find_liquidity_levels(high, low)
        features.liquidity_levels_above = resistance
        features.liquidity_levels_below = support

        # CVD
        cvd, _ = self.compute_cvd(close, volume)
        features.cvd = cvd

        # Wick Ratio
        features.wick_ratio = self.compute_wick_ratio(
            last_candle.open, last_candle.high, last_candle.low, last_candle.close
        )

        elapsed = (time.perf_counter() - start_time) * 1000
        key = f"{pair}:{timeframe}:{last_candle.timestamp}"
        self._feature_cache[key] = features

        logger.debug("feature_calculation_done", pair=pair, tf=timeframe, elapsed_ms=round(elapsed, 2))
        return features

    def compute_for_all(
        self, candles_by_pair_tf: Dict[str, Dict[str, List[OHLCV]]]
    ) -> Dict[str, Features]:
        """
        Compute features for all pairs and timeframes.
        candles_by_pair_tf: {pair: {tf: [candles]}}
        Returns: {"pair:tf": Features}
        """
        result = {}
        for pair, tf_candles in candles_by_pair_tf.items():
            for tf, candles in tf_candles.items():
                key = f"{pair}:{tf}"
                result[key] = self.compute_all_features(candles, pair, tf)
        return result

    def get_latest_features(self, pair: str, timeframe: str) -> Optional[Features]:
        """Get the most recently computed features for a pair/timeframe."""
        # Find the most recent cache key matching
        matches = [
            (ts, f) for k, f in self._feature_cache.items()
            if k.startswith(f"{pair}:{timeframe}:")
        ]
        if matches:
            return max(matches, key=lambda m: m[0])[1]
        return None
