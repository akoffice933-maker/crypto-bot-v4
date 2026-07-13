"""
Crypto Bot v4.4 — Health Monitor
Monitors system health, tracks engineering metrics, and triggers
appropriate actions (log / warn / stop trading).
"""

import time
import psutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import structlog

from core.models import HealthStatus

logger = structlog.get_logger(__name__)


@dataclass
class HealthSnapshot:
    """Single health check snapshot."""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    data_latency_ms: float = 0.0
    feature_calc_time_ms: float = 0.0
    cpu_pct: float = 0.0
    memory_mb: float = 0.0
    api_errors_per_min: int = 0
    api_retry_pct: float = 0.0
    order_placement_time_ms: float = 0.0
    websocket_connected: bool = True
    status: HealthStatus = HealthStatus.HEALTHY


class HealthMonitor:
    """
    Tracks engineering metrics and system health.
    Performs checks every N seconds and maintains health history.
    """

    # Thresholds from specification
    THRESHOLDS = {
        "data_latency_ms": 500,
        "feature_calc_time_ms": 100,
        "cpu_pct": 80.0,
        "memory_mb": 2048,
        "api_errors_per_min": 5,
        "api_retry_pct": 10.0,
        "order_placement_time_ms": 1000,
    }

    HISTORY_SIZE = 1440  # Keep 24h of 1-min snapshots

    def __init__(self, check_interval_sec: float = 5.0):
        self.check_interval = check_interval_sec
        self._history: List[HealthSnapshot] = []
        self._api_errors: List[datetime] = []  # timestamps of recent errors
        self._api_calls: int = 0
        self._api_retries: int = 0
        self._running = False

    def record_api_call(self, success: bool, retry: bool = False):
        """Record an API call outcome."""
        self._api_calls += 1
        if retry:
            self._api_retries += 1
        if not success:
            self._api_errors.append(datetime.utcnow())

    def record_data_latency(self, latency_ms: float):
        """Record data arrival latency."""
        self._last_data_latency = latency_ms

    def record_feature_calc_time(self, calc_ms: float):
        """Record feature calculation duration."""
        self._last_feature_calc = calc_ms

    def record_order_placement(self, time_ms: float):
        """Record order placement round-trip time."""
        self._last_order_time = time_ms

    def set_websocket_status(self, connected: bool):
        """Update WebSocket connection status."""
        self._ws_connected = connected

    def check(self) -> HealthSnapshot:
        """
        Perform a full health check and return a snapshot.
        Determines overall health status based on thresholds.
        """
        now = datetime.utcnow()

        # Clean old API errors (> 1 minute)
        self._api_errors = [t for t in self._api_errors if now - t < timedelta(minutes=1)]

        # Collect metrics
        cpu_pct = psutil.cpu_percent(interval=0.1)
        memory_info = psutil.Process().memory_info()
        memory_mb = memory_info.rss / (1024 * 1024)

        api_errors = len(self._api_errors)
        retry_pct = (self._api_retries / self._api_calls * 100) if self._api_calls > 0 else 0

        snapshot = HealthSnapshot(
            timestamp=now,
            data_latency_ms=getattr(self, "_last_data_latency", 0),
            feature_calc_time_ms=getattr(self, "_last_feature_calc", 0),
            cpu_pct=cpu_pct,
            memory_mb=memory_mb,
            api_errors_per_min=api_errors,
            api_retry_pct=retry_pct,
            order_placement_time_ms=getattr(self, "_last_order_time", 0),
            websocket_connected=getattr(self, "_ws_connected", True),
        )

        # Determine status
        critical = False
        warning = False

        checks = {
            "data_latency_ms": snapshot.data_latency_ms > self.THRESHOLDS["data_latency_ms"],
            "feature_calc_time_ms": snapshot.feature_calc_time_ms > self.THRESHOLDS["feature_calc_time_ms"],
            "cpu_pct": snapshot.cpu_pct > self.THRESHOLDS["cpu_pct"],
            "memory_mb": snapshot.memory_mb > self.THRESHOLDS["memory_mb"],
            "api_errors_per_min": snapshot.api_errors_per_min > self.THRESHOLDS["api_errors_per_min"],
            "api_retry_pct": snapshot.api_retry_pct > self.THRESHOLDS["api_retry_pct"],
            "order_placement_time_ms": snapshot.order_placement_time_ms > self.THRESHOLDS["order_placement_time_ms"],
        }

        if not snapshot.websocket_connected:
            critical = True
            logger.critical("websocket_disconnected")

        if any(checks.values()):
            warning = True
            failed = [k for k, v in checks.items() if v]
            logger.warning("health_check_warning", failed_checks=failed)

        if critical:
            snapshot.status = HealthStatus.CRITICAL
        elif warning:
            snapshot.status = HealthStatus.WARNING
        else:
            snapshot.status = HealthStatus.HEALTHY

        # Store history
        self._history.append(snapshot)
        if len(self._history) > self.HISTORY_SIZE:
            self._history = self._history[-self.HISTORY_SIZE:]

        return snapshot

    def get_status(self) -> dict:
        """Get current health status summary."""
        if not self._history:
            return {"status": "unknown", "last_check": None}

        latest = self._history[-1]
        return {
            "status": latest.status.value,
            "last_check": latest.timestamp.isoformat(),
            "data_latency_ms": latest.data_latency_ms,
            "feature_calc_time_ms": latest.feature_calc_time_ms,
            "cpu_pct": latest.cpu_pct,
            "memory_mb": latest.memory_mb,
            "api_errors_per_min": latest.api_errors_per_min,
            "api_retry_pct": latest.api_retry_pct,
            "order_placement_time_ms": latest.order_placement_time_ms,
            "websocket_connected": latest.websocket_connected,
        }

    def should_stop_trading(self) -> bool:
        """Check if trading should be stopped based on health."""
        if not self._history:
            return False
        return self._history[-1].status == HealthStatus.CRITICAL

    def get_uptime_metrics(self, hours: int = 24) -> dict:
        """Get health metrics over a time window."""
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=hours)
        relevant = [s for s in self._history if s.timestamp >= cutoff]

        if not relevant:
            return {"hours": hours, "snapshots": 0}

        healthy = sum(1 for s in relevant if s.status == HealthStatus.HEALTHY)
        warning = sum(1 for s in relevant if s.status == HealthStatus.WARNING)
        critical = sum(1 for s in relevant if s.status == HealthStatus.CRITICAL)
        total = len(relevant)

        return {
            "hours": hours,
            "snapshots": total,
            "availability_pct": round(healthy / total * 100, 2) if total > 0 else 0,
            "healthy_pct": round(healthy / total * 100, 2) if total > 0 else 0,
            "warning_pct": round(warning / total * 100, 2) if total > 0 else 0,
            "critical_pct": round(critical / total * 100, 2) if total > 0 else 0,
        }
