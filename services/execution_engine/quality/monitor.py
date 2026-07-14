"""
Quality-of-Execution monitoring.

Tracks slippage, latency, fill rate, cancel rate.
Provides summary metrics for the execution log.
"""

from typing import List

from core.models import ExecutionRecord


class QualityMonitor:
    """Monitors execution quality across the lifetime of the engine."""

    def __init__(self):
        self._records: List[ExecutionRecord] = []

    def record(self, record: ExecutionRecord):
        self._records.append(record)

    @property
    def total(self) -> int:
        return len(self._records)

    def summary(self) -> dict:
        """Compute quality metrics from all records."""
        if not self._records:
            return self._empty()

        slippages = [r.slippage for r in self._records]
        latencies = [r.latency for r in self._records]
        cancels = sum(1 for r in self._records if r.cancelled)
        partials = sum(1 for r in self._records if r.partial_fill)
        n = len(self._records)
        ref = self._records[0].expected_price if n > 0 else 1

        return {
            "avg_slippage": round(sum(slippages) / n, 8),
            "avg_slippage_pct": round(sum(slippages) / n / ref * 100, 5) if ref > 0 else 0,
            "avg_latency_ms": round(sum(latencies) / n, 2),
            "fill_rate": round((n - cancels) / n, 4) if n > 0 else 1.0,
            "cancel_rate": round(cancels / n, 4) if n > 0 else 0.0,
            "partial_rate": round(partials / n, 4) if n > 0 else 0.0,
            "total_executions": n,
        }

    @staticmethod
    def _empty() -> dict:
        return {
            "avg_slippage": 0, "avg_slippage_pct": 0, "avg_latency_ms": 0,
            "fill_rate": 1.0, "cancel_rate": 0, "partial_rate": 0,
            "total_executions": 0,
        }
