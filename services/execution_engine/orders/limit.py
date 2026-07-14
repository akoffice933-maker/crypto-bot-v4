"""
Limit order execution via CCXT.

Handles: placement, fill polling, timeout cancellation.
"""

import asyncio
import time
from typing import Optional

import structlog

from core.exchange.adapter import ExchangeAdapter, ExchangeOrder
from core.models import ExecutionRecord, RiskDecision, Signal

logger = structlog.get_logger(__name__)


class LimitOrderExecutor:
    """Executes limit orders with timeout and fill monitoring."""

    MAX_SLIPPAGE = 0.0005
    LIMIT_TIMEOUT = 60

    def __init__(self, exchange: ExchangeAdapter):
        self._exchange = exchange

    async def place(
        self,
        signal: Signal,
        risk_decision: RiskDecision,
        ccxt_symbol: str,
        side: str,
    ) -> Optional[ExecutionRecord]:
        """Place a limit order. Returns ExecutionRecord on fill, None on timeout/fail."""
        start = time.time()

        for attempt in range(3):
            try:
                order = self._exchange.create_limit_order(
                    symbol=ccxt_symbol,
                    side=side,
                    amount=round(risk_decision.position_size, 6),
                    price=round(signal.entry_limit, 2),
                )
                break
            except Exception as e:
                if attempt == 2:
                    raise
                logger.warning("limit_order_retry", attempt=attempt + 1, error=str(e))
                await asyncio.sleep(2 ** attempt)

        await asyncio.sleep(1.0)
        updated = self._exchange.fetch_order(order.id, ccxt_symbol)

        if updated.status == "closed":
            actual_price = updated.price or signal.entry_limit
        elif updated.status in ("canceled", "expired", "rejected"):
            logger.warning("order_not_filled", status=updated.status, id=order.id)
            return None
        else:
            actual_price = await self._wait_fill(order.id, ccxt_symbol)

        if actual_price <= 0:
            return None

        elapsed = (time.time() - start) * 1000
        slippage = abs(actual_price - signal.entry_limit)

        if signal.entry_limit > 0 and slippage / signal.entry_limit > self.MAX_SLIPPAGE:
            logger.warning("high_slippage", pair=signal.pair,
                         slippage_pct=round(slippage / signal.entry_limit * 100, 4))

        return ExecutionRecord(
            pair=signal.pair,
            expected_price=signal.entry_limit,
            actual_price=actual_price,
            slippage=slippage,
            latency=elapsed,
        )

    async def _wait_fill(self, order_id: str, symbol: str) -> float:
        """Poll until filled or timeout. Returns price or 0."""
        deadline = time.time() + self.LIMIT_TIMEOUT
        while time.time() < deadline:
            try:
                order = self._exchange.fetch_order(order_id, symbol)
                if order.status == "closed":
                    return order.price or 0
                if order.status in ("canceled", "expired", "rejected"):
                    return 0
            except Exception:
                pass
            await asyncio.sleep(2.0)

        try:
            self._exchange.cancel_order(order_id, symbol)
        except Exception:
            pass
        return 0
