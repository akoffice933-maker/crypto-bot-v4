"""
Retry logic with exponential backoff and circuit breaker.

Protects against cascading API failures.
"""

import time
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)


class CircuitBreaker:
    """Opens after max_failures, resets after reset_sec."""

    def __init__(self, max_failures: int = 5, reset_sec: float = 60.0):
        self.max_failures = max_failures
        self.reset_sec = reset_sec
        self.failures: int = 0
        self.last_failure: float = 0.0
        self._open: bool = False

    def fail(self):
        self.failures += 1
        self.last_failure = time.time()
        if self.failures >= self.max_failures:
            self._open = True
            logger.critical("circuit_breaker_open", failures=self.failures)

    def success(self):
        self.failures = 0
        self._open = False

    @property
    def is_open(self) -> bool:
        if not self._open:
            return False
        if time.time() - self.last_failure > self.reset_sec:
            self._open = False
            self.failures = 0
            logger.info("circuit_breaker_reset")
            return False
        return True

    @property
    def can_proceed(self) -> bool:
        return not self.is_open


class RetryPolicy:
    """Exponential backoff retry with circuit breaker."""

    def __init__(self, circuit_breaker: CircuitBreaker, max_attempts: int = 3):
        self._cb = circuit_breaker
        self.max_attempts = max_attempts

    async def call(self, fn: Callable, *args, **kwargs) -> Any:
        """Call fn with retries. Raises last error if all attempts fail."""
        if self._cb.is_open:
            raise RuntimeError("Circuit breaker open — trading halted")

        last_error = None
        for attempt in range(self.max_attempts):
            try:
                result = fn(*args, **kwargs)
                self._cb.success()
                return result
            except Exception as e:
                last_error = e
                logger.warning("retry_attempt", attempt=attempt + 1, error=str(e))
                if attempt < self.max_attempts - 1:
                    await self._sleep(2 ** attempt)
                else:
                    self._cb.fail()

        raise last_error

    async def _sleep(self, seconds: float):
        import asyncio
        await asyncio.sleep(seconds)
