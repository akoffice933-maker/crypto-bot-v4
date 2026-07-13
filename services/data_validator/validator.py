"""
Crypto Bot v4.4 — Data Validator
Validates incoming market data for quality issues before trading.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

import structlog

from core.models import OHLCV, HealthStatus

logger = structlog.get_logger(__name__)


class DataValidator:
    """
    Validates market data quality per the specification:
    - Gap detection (>5% missing → stop trading)
    - Duplicate detection
    - Invalid volume / negative price rejection
    - Timestamp jump detection
    - TF synchronization checks
    """

    # Validation thresholds
    MAX_GAP_PCT = 5.0          # Maximum % of missing candles before stopping
    MAX_TIME_JUMP_MINUTES = 5   # Maximum allowed gap in minutes
    MIN_TICK_VOLUME = 1.0      # Minimum volume (ticks)

    def __init__(self):
        self._critical_errors: List[dict] = []
        self._non_critical_errors: List[dict] = []
        self._last_validation: Optional[datetime] = None

    def validate_candles(
        self, candles: List[OHLCV], expected_timeframe: str
    ) -> Tuple[bool, List[dict], List[dict]]:
        """
        Validate a batch of candles.
        Returns (is_healthy, critical_errors, non_critical_errors).
        """
        critical = []
        non_critical = []

        if not candles:
            return True, [], []

        # 1. Sort by timestamp
        sorted_candles = sorted(candles, key=lambda c: c.timestamp)

        # 2. Check for negative prices
        for c in sorted_candles:
            if c.open < 0 or c.high < 0 or c.low < 0 or c.close < 0:
                critical.append({
                    "type": "negative_price",
                    "timestamp": c.timestamp,
                    "pair": c.pair,
                    "message": f"Negative price detected: O={c.open} H={c.high} L={c.low} C={c.close}",
                })

        # 3. Check for duplicates
        seen = set()
        duplicates = []
        for c in sorted_candles:
            key = (c.timestamp, c.pair, c.timeframe)
            if key in seen:
                duplicates.append(c)
                non_critical.append({
                    "type": "duplicate",
                    "timestamp": c.timestamp,
                    "pair": c.pair,
                    "message": "Duplicate candle detected",
                })
            seen.add(key)

        # 4. Check for invalid volume
        for c in sorted_candles:
            if c.volume < self.MIN_TICK_VOLUME:
                non_critical.append({
                    "type": "low_volume",
                    "timestamp": c.timestamp,
                    "pair": c.pair,
                    "message": f"Volume {c.volume} below minimum {self.MIN_TICK_VOLUME}",
                })

        # 5. Check for time gaps
        expected_delta = self._get_timeframe_delta(expected_timeframe)
        total_expected = 0
        total_missing = 0

        for i in range(1, len(sorted_candles)):
            gap = (sorted_candles[i].timestamp - sorted_candles[i-1].timestamp).total_seconds()
            expected_seconds = expected_delta.total_seconds()

            total_expected += 1
            if gap > expected_seconds * 1.5:  # 50% tolerance
                missing_candles = int(gap / expected_seconds) - 1
                total_missing += missing_candles

                if gap / 60 > self.MAX_TIME_JUMP_MINUTES:
                    non_critical.append({
                        "type": "time_jump",
                        "timestamp": sorted_candles[i].timestamp,
                        "pair": sorted_candles[i].pair,
                        "message": f"Time jump of {gap/60:.1f} minutes ({missing_candles} missing candles)",
                    })

        # 6. Gap percentage check
        if total_expected > 0:
            gap_pct = (total_missing / total_expected) * 100
            if gap_pct > self.MAX_GAP_PCT:
                critical.append({
                    "type": "excessive_gaps",
                    "pair": sorted_candles[0].pair,
                    "timeframe": expected_timeframe,
                    "gap_pct": round(gap_pct, 2),
                    "missing": total_missing,
                    "expected": total_expected,
                    "message": f"Missing {gap_pct:.1f}% candles exceeds {self.MAX_GAP_PCT}% threshold",
                })

        # 7. Store for monitoring
        self._critical_errors.extend(critical)
        self._non_critical_errors.extend(non_critical)
        self._last_validation = datetime.now(timezone.utc)

        is_healthy = len(critical) == 0

        if critical:
            logger.error("data_validation_critical", errors=critical)
        if non_critical:
            logger.warning("data_validation_non_critical", errors=non_critical)

        return is_healthy, critical, non_critical

    def validate_timeframe_sync(
        self,
        candles_dict: dict[str, List[OHLCV]],  # {tf: candles}
    ) -> List[dict]:
        """
        Check that different timeframes are synchronized.
        E.g., 1h candles should align with 4h boundaries.
        """
        issues = []
        timeframes = list(candles_dict.keys())

        for i, tf_a in enumerate(timeframes):
            for tf_b in timeframes[i+1:]:
                # Check if higher TF boundaries align with lower TF
                delta_a = self._get_timeframe_delta(tf_a)
                delta_b = self._get_timeframe_delta(tf_b)
                larger = tf_a if delta_a >= delta_b else tf_b
                smaller = tf_b if delta_a >= delta_b else tf_a

                if candles_dict.get(larger) and candles_dict.get(smaller):
                    larger_ts = {c.timestamp for c in candles_dict[larger]}
                    smaller_ts = {c.timestamp for c in candles_dict[smaller]}

                    for ts in larger_ts:
                        if ts not in smaller_ts:
                            issues.append({
                                "type": "tf_sync",
                                "larger_tf": larger,
                                "smaller_tf": smaller,
                                "timestamp": ts,
                                "message": f"Timestamp {ts} in {larger} not found in {smaller}",
                            })

        if issues:
            logger.warning("tf_sync_issues", issues=issues)
        return issues

    def _get_timeframe_delta(self, timeframe: str) -> timedelta:
        """Convert timeframe string to timedelta."""
        mapping = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
        }
        return mapping.get(timeframe, timedelta(hours=1))

    @property
    def health_status(self) -> HealthStatus:
        """Return current health status based on stored errors."""
        if self._critical_errors:
            return HealthStatus.CRITICAL
        if self._non_critical_errors:
            return HealthStatus.WARNING
        return HealthStatus.HEALTHY

    def clear_errors(self):
        """Clear stored errors after they've been handled."""
        self._critical_errors.clear()
        self._non_critical_errors.clear()

    def get_error_summary(self) -> dict:
        """Get a summary of validation errors."""
        return {
            "critical_count": len(self._critical_errors),
            "non_critical_count": len(self._non_critical_errors),
            "last_validation": self._last_validation.isoformat() if self._last_validation else None,
            "status": self.health_status.value,
        }
