"""
Crypto Bot v4.4 — Feature Service
Calculates technical features: ADX, ATR%, Bollinger Bands, Volume MA,
Liquidity Levels, CVD, Squeeze detection.

Performance target: <100ms for 4 pairs across all timeframes.
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import structlog

from core.models import Features, OHLCV

logger = structlog.get_logger(__name__)


def _ewma(arr: np.ndarray, period: int) -> np.ndarray:
    """
    Vectorized exponential weighted moving average.
    Equivalent to pandas.Series.ewm(alpha=1/period, adjust=False).mean()
    but without pandas dependency for speed.
    """
    alpha = 1.0 / period
    result = np.empty_like(arr)
    result[0] = arr[0]
    for i in range(1, len(arr)):
        result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
    return result


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
        """
        Compute ADX (Average Directional Index) — fully vectorized.
        Uses Wilder's smoothing (EMA with alpha=1/period).
        """
        n = len(close)
        if n < period + 1:
            return 0.0

        n_m1 = n - 1

        # True Range
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )

        # Directional Movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        # Wilder's smoothing via EWMA
        atr = _ewma(tr, period)
        plus_di = np.zeros(n_m1)
        minus_di = np.zeros(n_m1)

        valid = atr > 1e-12
        plus_di[valid] = _ewma(plus_dm[valid], period) / atr[valid] * 100
        minus_di[valid] = _ewma(minus_dm[valid], period) / atr[valid] * 100

        # DX = |+DI - -DI| / (+DI + -DI) * 100
        sum_di = plus_di + minus_di
        dx = np.zeros(n_m1)
        mask = sum_di > 1e-12
        dx[mask] = np.abs(plus_di[mask] - minus_di[mask]) / sum_di[mask] * 100

        # ADX = smoothed DX
        adx = _ewma(dx, period)

        return float(adx[-1])

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
        atr = _ewma(tr, period)
        current_atr = atr[-1]
        current_close = close[-1]
        atr_pct = (current_atr / current_close * 100) if current_close > 0 else 0.0

        # Percentile of current ATR% in historical ATR% values
        atr_pct_series = np.zeros_like(atr)
        valid_mask = close[1:] > 0
        atr_pct_series[valid_mask] = atr[valid_mask] / close[1:][valid_mask] * 100
        percentile = float(np.percentile(atr_pct_series[atr_pct_series > 0], 80)) if np.any(atr_pct_series > 0) else 0.0

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
        std = float(close_series.std(ddof=1))
        upper = middle + std_mult * std
        lower = middle - std_mult * std
        width = (upper - lower) / middle * 100 if middle > 0 else 0.0

        # Squeeze: BB width < 1.5 × std (Keltner approximation)
        squeeze = width < std * 1.5 / middle * 100 if middle > 0 else False

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
        if ma < 1e-12:
            return 1.0
        return float(volume[-1] / ma)

    @staticmethod
    def find_liquidity_levels(
        high: np.ndarray, low: np.ndarray, lookback: int = 50
    ) -> Tuple[List[float], List[float]]:
        """Find equal highs (resistance) and equal lows (support)."""
        n = len(high)
        if n < lookback:
            lookback = n

        recent_high = high[-lookback:]
        recent_low = low[-lookback:]

        # Local maxima/minima detection
        resistance_levels = []
        for i in range(1, len(recent_high) - 1):
            if recent_high[i] >= recent_high[i - 1] and recent_high[i] >= recent_high[i + 1]:
                resistance_levels.append(float(recent_high[i]))

        support_levels = []
        for i in range(1, len(recent_low) - 1):
            if recent_low[i] <= recent_low[i - 1] and recent_low[i] <= recent_low[i + 1]:
                support_levels.append(float(recent_low[i]))

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
        """Approximate Cumulative Volume Delta."""
        n = len(close)
        if n < 2:
            return 0.0, 0.0

        start_idx = max(1, n - lookback)
        deltas = []
        for i in range(start_idx, n):
            vol = volume[i] if i < len(volume) else 0
            if close[i] > close[i - 1]:
                deltas.append(vol)
            else:
                deltas.append(-vol)

        cvd = float(sum(deltas)) if deltas else 0.0
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

        if body < 1e-12:
            return max(upper_wick, lower_wick) / 1e-6 if max(upper_wick, lower_wick) > 0 else 1.0

        return max(upper_wick, lower_wick) / body

    def compute_all_features(
        self, candles: List[OHLCV], pair: str, timeframe: str
    ) -> Features:
        """Compute all features for a given set of candles."""
        start_time = time.perf_counter()

        if not candles:
            return Features(timestamp=datetime.now(timezone.utc), pair=pair, timeframe=timeframe)

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
        """Compute features for all pairs and timeframes."""
        result = {}
        for pair, tf_candles in candles_by_pair_tf.items():
            for tf, candles in tf_candles.items():
                if not candles:
                    continue
                key = f"{pair}:{tf}"
                result[key] = self.compute_all_features(candles, pair, tf)
        return result

    def get_latest_features(self, pair: str, timeframe: str) -> Optional[Features]:
        """Get the most recently computed features for a pair/timeframe."""
        matches = [
            (ts, f) for k, f in self._feature_cache.items()
            if k.startswith(f"{pair}:{timeframe}:")
        ]
        if matches:
            return max(matches, key=lambda m: m[0])[1]
        return None
