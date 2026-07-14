"""
Market order execution (emergency fallback).

Used when limit orders fail to fill within timeout.
Includes adverse price movement checks.
"""

import time
from datetime import datetime, timezone
from typing import Optional

import structlog

from core.exchange.adapter import ExchangeAdapter
from core.models import ExecutionRecord, RiskDecision, Signal

logger = structlog.get_logger(__name__)


class MarketOrderExecutor:
    """Emergency market order executor with price movement guard."""

    MAX_PRICE_MOVE = 0.002  # 0.2% max adverse move

    def __init__(self, exchange: ExchangeAdapter):
        self._exchange = exchange

    async def place(
        self,
        signal: Signal,
        risk_decision: RiskDecision,
        ccxt_symbol: str,
        side: str,
    ) -> Optional[ExecutionRecord]:
        """Place a market order (emergency fallback)."""
        start = time.time()
        try:
            order = self._exchange.create_market_order(
                symbol=ccxt_symbol,
                side=side,
                amount=round(risk_decision.position_size, 6),
            )
            actual_price = order.price or signal.entry_market
        except Exception as e:
            logger.critical("emergency_market_failed", pair=signal.pair, error=str(e))
            return None

        price_move = (
            abs(actual_price - signal.entry_market) / signal.entry_market
            if signal.entry_market > 0 else 0
        )
        if price_move > self.MAX_PRICE_MOVE:
            logger.warning("emergency_price_moved_too_far",
                         pair=signal.pair, move_pct=round(price_move * 100, 4))

        elapsed = (time.time() - start) * 1000
        return ExecutionRecord(
            timestamp=datetime.now(timezone.utc),
            pair=signal.pair,
            expected_price=signal.entry_market,
            actual_price=actual_price,
            slippage=abs(actual_price - signal.entry_market),
            latency=elapsed,
        )
